"""Security layer: rate limiting, audit logging, and cost guardrails.

These middleware-style utilities protect the MCP server from abuse and
provide observability for production deployments.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)


# ─── Rate Limiter ────────────────────────────────────────────────────────


@dataclass
class _RateBucket:
    """Sliding-window rate limit bucket."""

    timestamps: deque[float] = field(default_factory=deque)


class RateLimiter:
    """Sliding-window rate limiter per client identifier.

    Thread-safe. Designed for single-process MCP servers; for multi-process
    deployments, replace the in-memory store with Redis.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, _RateBucket] = defaultdict(_RateBucket)
        self._lock = Lock()

    def check(self, client_id: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[client_id]
            cutoff = now - self.window_seconds

            # Evict expired timestamps
            while bucket.timestamps and bucket.timestamps[0] < cutoff:
                bucket.timestamps.popleft()

            if len(bucket.timestamps) >= self.max_requests:
                logger.warning(
                    "Rate limit exceeded",
                    extra={
                        "client_id": client_id,
                        "count": len(bucket.timestamps),
                        "limit": self.max_requests,
                    },
                )
                return False

            bucket.timestamps.append(now)
            return True

    def remaining(self, client_id: str) -> int:
        """Return remaining requests in the current window."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[client_id]
            cutoff = now - self.window_seconds
            while bucket.timestamps and bucket.timestamps[0] < cutoff:
                bucket.timestamps.popleft()
            return max(0, self.max_requests - len(bucket.timestamps))


# ─── Cost Guardrails ──────────────────────────────────────────────────────


class CostGuardrail:
    """Per-request and per-day cost guardrails.

    Estimates the cost of a chat completion before sending it to the Riven API
    and rejects requests that exceed configured thresholds.
    """

    def __init__(self, per_request_limit: float, daily_limit: float) -> None:
        self.per_request_limit = per_request_limit
        self.daily_limit = daily_limit
        self._daily_spend: dict[str, float] = defaultdict(float)
        self._current_date: str = ""
        self._lock = Lock()

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _rollover_if_needed(self) -> None:
        """Reset daily counters if the date has changed."""
        today = self._today()
        if today != self._current_date:
            self._daily_spend.clear()
            self._current_date = today

    def check_request(
        self,
        client_id: str,
        estimated_cost: float,
    ) -> tuple[bool, str]:
        """Check if a request is within cost guardrails.

        Returns:
            (allowed, reason) — reason is empty if allowed.
        """
        with self._lock:
            self._rollover_if_needed()

            if estimated_cost > self.per_request_limit:
                return (
                    False,
                    f"Estimated cost ${estimated_cost:.4f} exceeds per-request "
                    f"limit ${self.per_request_limit:.2f}",
                )

            if self.daily_limit > 0:
                current_daily = self._daily_spend[client_id]
                if current_daily + estimated_cost > self.daily_limit:
                    return (
                        False,
                        f"Daily spend would reach ${current_daily + estimated_cost:.4f}, "
                        f"exceeding daily limit ${self.daily_limit:.2f}",
                    )

            return True, ""

    def record_spend(self, client_id: str, actual_cost: float) -> None:
        """Record actual spend after a successful request."""
        with self._lock:
            self._rollover_if_needed()
            self._daily_spend[client_id] += actual_cost

    def get_daily_spend(self, client_id: str) -> float:
        """Return total spend today for a client."""
        with self._lock:
            self._rollover_if_needed()
            return self._daily_spend[client_id]


# ─── Audit Logger ─────────────────────────────────────────────────────────


class AuditLogger:
    """Append-only audit log for all tool invocations.

    Writes structured JSON lines to a file and emits to the standard logger.
    Designed for forwarding to Loki/ELK via Docker logging drivers.
    """

    def __init__(self, log_path: str) -> None:
        self.log_path = Path(log_path) if log_path else None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def log(
        self,
        event: str,
        client_id: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
        result: Any = None,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Write a single audit record."""
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "client_id": client_id,
            "tool": tool,
            "arguments": _sanitize_args(arguments),
            "error": error,
            "duration_ms": duration_ms,
        }
        if result is not None:
            record["result_summary"] = _summarize_result(result)

        line = json.dumps(record, default=str)

        # Emit to standard logger
        if error:
            logger.warning("audit: %s", line)
        else:
            logger.info("audit: %s", line)

        # Append to file
        if self.log_path:
            with self._lock:
                with open(self.log_path, "a") as f:
                    f.write(line + "\n")


def _sanitize_args(args: dict[str, Any] | None) -> dict[str, Any]:
    """Remove sensitive values (API keys, full messages) from audit records."""
    if not args:
        return {}
    sanitized = {}
    for k, v in args.items():
        if k.lower() in ("api_key", "key", "token", "secret", "authorization"):
            sanitized[k] = "[REDACTED]"
        elif k == "messages" and isinstance(v, list):
            sanitized[k] = f"[{len(v)} messages]"
        elif k == "input" and isinstance(v, str) and len(v) > 200:
            sanitized[k] = v[:200] + "...[truncated]"
        else:
            sanitized[k] = v
    return sanitized


def _summarize_result(result: Any) -> str:
    """Create a short summary of a tool result for audit logging."""
    s = str(result)
    return s[:500] + "..." if len(s) > 500 else s


# ─── Singleton Factories ─────────────────────────────────────────────────


_rate_limiter: RateLimiter | None = None
_cost_guardrail: CostGuardrail | None = None
_audit_logger: AuditLogger | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        s = get_settings()
        _rate_limiter = RateLimiter(
            max_requests=s.rate_limit_max_requests,
            window_seconds=s.rate_limit_window_seconds,
        )
    return _rate_limiter


def get_cost_guardrail() -> CostGuardrail:
    global _cost_guardrail
    if _cost_guardrail is None:
        s = get_settings()
        _cost_guardrail = CostGuardrail(
            per_request_limit=s.cost_guardrail_per_request_usd,
            daily_limit=s.cost_guardrail_daily_usd,
        )
    return _cost_guardrail


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        s = get_settings()
        _audit_logger = AuditLogger(s.audit_log_path)
    return _audit_logger


def setup_logging() -> None:
    """Configure structured logging based on settings."""
    s = get_settings()

    if s.log_json:
        # Structured JSON logging for Docker Swarm / Loki
        import logging as _logging

        class JsonFormatter(_logging.Formatter):
            def format(self, record: _logging.LogRecord) -> str:
                log_entry: dict[str, Any] = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    log_entry["exception"] = self.formatException(record.exc_info)
                # Include extra fields
                for key, val in record.__dict__.items():
                    if key not in (
                        "name", "msg", "args", "levelname", "levelno",
                        "pathname", "filename", "module", "exc_info",
                        "exc_text", "stack_info", "lineno", "funcName",
                        "created", "msecs", "relativeCreated", "thread",
                        "threadName", "processName", "process", "taskName",
                    ):
                        log_entry[key] = str(val)
                return json.dumps(log_entry, default=str)

        handler = _logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root = _logging.getLogger()
        root.handlers = [handler]
        root.setLevel(getattr(_logging, s.log_level.upper(), _logging.INFO))
    else:
        _logging.basicConfig(
            level=getattr(_logging, s.log_level.upper(), _logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
