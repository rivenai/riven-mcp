"""Configuration management for the Riven MCP Server.

All settings are loaded from environment variables (12-factor app).
A singleton `settings` instance is available for import across modules.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Riven API ───────────────────────────────────────────────────
    riven_api_base_url: str = Field(
        default="https://api.rivenai.io/v1",
        description="Riven API base URL (OpenAI-compatible)",
    )
    riven_api_key: str = Field(
        default="",
        description="Server-side Riven API key for backend calls",
    )

    # ─── MCP Transport ────────────────────────────────────────────────
    mcp_transport: Literal["stdio", "http"] = Field(
        default="stdio",
        description="Transport mode: stdio or http (Streamable HTTP + SSE)",
    )
    mcp_host: str = Field(default="0.0.0.0", description="HTTP listen host")
    mcp_port: int = Field(default=8080, description="HTTP listen port")
    mcp_protocol_version: str = Field(
        default="2024-11-05",
        description="MCP protocol version advertised during handshake",
    )

    # ─── Security ────────────────────────────────────────────────────
    mcp_auth_keys: str = Field(
        default="",
        description="Comma-separated allowed MCP client API keys (empty = no auth)",
    )
    rate_limit_max_requests: int = Field(
        default=100, description="Max requests per rate-limit window"
    )
    rate_limit_window_seconds: int = Field(
        default=60, description="Rate-limit window size in seconds"
    )
    cost_guardrail_per_request_usd: float = Field(
        default=5.0, description="Max estimated cost per single request (USD)"
    )
    cost_guardrail_daily_usd: float = Field(
        default=100.0, description="Max daily spend per API key (USD, 0=unlimited)"
    )

    # ─── IndexNow ────────────────────────────────────────────────────
    indexnow_api_key: str = Field(default="", description="Bing IndexNow API key")
    indexnow_host: str = Field(
        default="rivenai.io", description="Comma-separated IndexNow hostnames"
    )

    # ─── On-Prem Health ──────────────────────────────────────────────
    onprem_health_url: str = Field(
        default="http://127.0.0.1:8000/health",
        description="On-prem GLM model health endpoint. Override with the actual GPU host URL in production.",
    )

    # ─── Logging ────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Log level")
    log_json: bool = Field(default=True, description="Enable structured JSON logging")
    audit_log_path: str = Field(
        default="", description="Audit log file path (empty = disabled)"
    )

    # ─── Derived ────────────────────────────────────────────────────
    @property
    def auth_keys(self) -> list[str]:
        """Parse comma-separated auth keys into a list."""
        if not self.mcp_auth_keys or self.mcp_auth_keys.strip() == "*":
            return []
        return [k.strip() for k in self.mcp_auth_keys.split(",") if k.strip()]

    @property
    def indexnow_hosts(self) -> list[str]:
        """Parse comma-separated IndexNow hosts."""
        return [h.strip() for h in self.indexnow_host.split(",") if h.strip()]

    @field_validator("riven_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not v:
            import warnings

            warnings.warn(
                "RIVEN_API_KEY is not set — API calls will fail. "
                "Set it in .env or environment.",
                stacklevel=2,
            )
        return v

    @model_validator(mode="after")
    def resolve_docker_secrets(self) -> "Settings":
        """Resolve _FILE environment variables (Docker secrets).

        If RIVEN_API_KEY_FILE is set, read the key from that file path
        and assign it to RIVEN_API_KEY. Same for INDEXNOW_API_KEY_FILE.
        """
        secret_mappings = [
            ("riven_api_key", "RIVEN_API_KEY_FILE"),
            ("indexnow_api_key", "INDEXNOW_API_KEY_FILE"),
        ]
        for attr, env_var in secret_mappings:
            file_path = os.environ.get(env_var)
            if file_path and Path(file_path).exists():
                value = Path(file_path).read_text().strip()
                setattr(self, attr, value)
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()


# Ensure audit log directory exists
def ensure_audit_dir() -> None:
    """Create the audit log directory if a path is configured."""
    s = get_settings()
    if s.audit_log_path:
        Path(s.audit_log_path).parent.mkdir(parents=True, exist_ok=True)
