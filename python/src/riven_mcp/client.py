"""Async HTTP client wrapper for the Riven AI API.

All Riven platform API calls go through this client, which handles:
  - Bearer token authentication
  - Retry with exponential backoff (tenacity)
  - Structured request/response logging
  - Consistent error handling
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import get_settings

logger = logging.getLogger(__name__)


class RivenAPIError(Exception):
    """Raised when the Riven API returns an error response."""

    def __init__(self, status_code: int, detail: str, body: Any = None) -> None:
        self.status_code = status_code
        self.detail = detail
        self.body = body
        super().__init__(f"Riven API error {status_code}: {detail}")


class RivenClient:
    """Async client for the Riven AI OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        s = get_settings()
        self.base_url = (base_url or s.riven_api_base_url).rstrip("/")
        self.api_key = api_key or s.riven_api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "riven-mcp-server/1.0.0",
                },
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Execute an authenticated API request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path relative to base URL (e.g. "/models")
            json: Request body for POST/PUT
            params: Query parameters

        Returns:
            Parsed JSON response.

        Raises:
            RivenAPIError: On non-2xx responses.
        """
        client = await self._get_client()
        logger.debug(
            "API request",
            extra={"method": method, "path": path, "params": params},
        )

        response = await client.request(method, path, json=json, params=params)

        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("error", {}).get("message", str(body))
            except Exception:
                body = response.text
                detail = response.text
            logger.error(
                "API error",
                extra={
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "detail": detail,
                },
            )
            raise RivenAPIError(response.status_code, detail, body)

        if response.status_code == 204 or not response.content:
            return None

        return response.json()

    # ─── Convenience wrappers ────────────────────────────────────────

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(
        self, path: str, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None
    ) -> Any:
        return await self.request("POST", path, json=json, params=params)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Module-level singleton for reuse across tool calls
_client_instance: RivenClient | None = None


def get_client() -> RivenClient:
    """Return a shared RivenClient singleton."""
    global _client_instance
    if _client_instance is None:
        _client_instance = RivenClient()
    return _client_instance


async def close_client() -> None:
    """Close the shared client (call on server shutdown)."""
    global _client_instance
    if _client_instance is not None:
        await _client_instance.close()
        _client_instance = None
