"""Shared helpers for MCP tool implementations.

Provides a decorator wrapper that enforces rate limiting, audit logging,
and error handling consistently across all tools.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Awaitable, Callable, TypeVar

from ..config import get_settings
from ..security import get_audit_logger, get_rate_limiter

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default client ID for tools (can be overridden per-request via context)
_DEFAULT_CLIENT_ID = "mcp-default"


def get_client_id() -> str:
    """Return the current client identifier.

    In a production deployment with OAuth, this would extract the
    authenticated principal from the MCP request context.
    """
    return _DEFAULT_CLIENT_ID


def tool_handler(
    tool_name: str,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator that wraps an async tool function with security middleware.

    Applies:
      - Rate limiting (per client)
      - Audit logging (start, success/error)
      - Structured error handling

    Usage:
        @tool_handler("list_models")
        async def list_models(...) -> ...:
            ...
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            client_id = get_client_id()
            limiter = get_rate_limiter()
            audit = get_audit_logger()

            # Rate limit check
            if not limiter.check(client_id):
                remaining = limiter.remaining(client_id)
                audit.log(
                    event="rate_limited",
                    client_id=client_id,
                    tool=tool_name,
                    arguments=kwargs if kwargs else dict(zip(_arg_names(func), args)),
                    error="Rate limit exceeded",
                )
                raise PermissionError(
                    f"Rate limit exceeded for tool '{tool_name}'. "
                    f"Retry in {get_settings().rate_limit_window_seconds}s. "
                    f"Remaining: {remaining}"
                )

            start = time.monotonic()
            audit.log(
                event="tool_start",
                client_id=client_id,
                tool=tool_name,
                arguments=kwargs if kwargs else dict(zip(_arg_names(func), args)),
            )

            try:
                result = await func(*args, **kwargs)
                duration = (time.monotonic() - start) * 1000
                audit.log(
                    event="tool_success",
                    client_id=client_id,
                    tool=tool_name,
                    arguments=kwargs if kwargs else dict(zip(_arg_names(func), args)),
                    result=result,
                    duration_ms=round(duration, 2),
                )
                return result
            except Exception as exc:
                duration = (time.monotonic() - start) * 1000
                audit.log(
                    event="tool_error",
                    client_id=client_id,
                    tool=tool_name,
                    arguments=kwargs if kwargs else dict(zip(_arg_names(func), args)),
                    error=str(exc),
                    duration_ms=round(duration, 2),
                )
                raise

        return wrapper

    return decorator


def _arg_names(func: Callable[..., Any]) -> list[str]:
    """Extract argument names from a function signature."""
    import inspect

    sig = inspect.signature(func)
    return list(sig.parameters.keys())


def format_error(message: str, detail: Any = None) -> str:
    """Format an error message for tool output."""
    if detail:
        return f"Error: {message}\nDetails: {detail}"
    return f"Error: {message}"
