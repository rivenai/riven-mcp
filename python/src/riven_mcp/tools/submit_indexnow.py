"""Tool: submit_indexnow — Submit URLs to Bing IndexNow.

Submits one or more URLs to Bing's IndexNow protocol for immediate
crawling and indexing. Requires an IndexNow API key registered with Bing.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from mcp.server import MCPServer

from ..config import get_settings
from ._helpers import tool_handler

logger = logging.getLogger(__name__)

INDEXNOW_ENDPOINT = "https://api.indexnow.org/IndexNow"
BING_INDEXNOW_ENDPOINT = "https://www.bing.com/indexnow"


async def _submit_indexnow_impl(urls: list[str], host: str | None) -> str:
    """Submit URLs to IndexNow."""
    s = get_settings()

    if not s.indexnow_api_key:
        return (
            "IndexNow API key not configured. Set INDEXNOW_API_KEY in environment.\n"
            "Register at https://www.bing.com/indexnow"
        )

    target_host = host or s.indexnow_hosts[0] if s.indexnow_hosts else None
    if not target_host:
        return "No host configured. Set INDEXNOW_HOST in environment."

    # Validate URLs belong to the configured host
    invalid = [u for u in urls if target_host not in u]
    if invalid:
        return (
            f"URLs must belong to host '{target_host}'. "
            f"Invalid URLs: {', '.join(invalid[:5])}"
        )

    body: dict[str, Any] = {
        "host": target_host,
        "key": s.indexnow_api_key,
        "keyLocation": f"https://{target_host}/{s.indexnow_api_key}.txt",
        "urlList": urls,
    }

    # Submit to both IndexNow and Bing directly
    results: list[str] = []

    for endpoint_name, endpoint_url in [
        ("IndexNow", INDEXNOW_ENDPOINT),
        ("Bing", BING_INDEXNOW_ENDPOINT),
    ]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                response = await http_client.post(endpoint_url, json=body)

            if response.status_code in (200, 202):
                results.append(f"- {endpoint_name}: Accepted ({response.status_code})")
            elif response.status_code == 422:
                results.append(f"- {endpoint_name}: Invalid request (422) — check API key")
            elif response.status_code == 429:
                results.append(f"- {endpoint_name}: Rate limited (429) — try later")
            else:
                results.append(
                    f"- {endpoint_name}: HTTP {response.status_code} — {response.text[:200]}"
                )
        except Exception as exc:
            results.append(f"- {endpoint_name}: Error — {exc}")

    summary = (
        f"# IndexNow Submission\n\n"
        f"Host: {target_host}\n"
        f"URLs submitted: {len(urls)}\n\n"
        f"## Results\n" + "\n".join(results) + "\n\n"
        f"## Submitted URLs\n"
        + "\n".join(f"- {u}" for u in urls)
    )
    return summary


def register(server: MCPServer) -> None:
    """Register the submit_indexnow tool on the MCP server."""

    @server.tool()
    @tool_handler("submit_indexnow")
    async def submit_indexnow(
        urls: list[str],
        host: str | None = None,
    ) -> str:
        """Submit URLs to Bing IndexNow for immediate indexing.

        IndexNow is a protocol that notifies search engines of content changes,
        enabling faster crawling and indexing. URLs must belong to a host
        you control with a registered IndexNow API key.

        Args:
            urls: List of full URLs to submit (e.g. ["https://rivenai.io/blog/new-post"]).
                   Must belong to the configured host.
            host: Override the host (defaults to INDEXNOW_HOST setting).
                  The host must have a valid IndexNow key file at
                  https://{host}/{key}.txt

        Returns:
            Submission results from IndexNow and Bing endpoints, including
            HTTP status codes and any errors.
        """
        return await _submit_indexnow_impl(urls=urls, host=host)
