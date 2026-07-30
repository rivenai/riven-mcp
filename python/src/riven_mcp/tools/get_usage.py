"""Tool: get_usage — Query token usage and costs.

Fetches usage statistics from the Riven API, including token counts
and costs broken down by model and time period.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from ..client import RivenAPIError, get_client
from ._helpers import tool_handler

logger = logging.getLogger(__name__)


async def _get_usage_impl(
    start_date: str | None,
    end_date: str | None,
    model: str | None,
    group_by: str,
) -> str:
    """Fetch usage data from the Riven API."""
    client = get_client()

    params: dict[str, Any] = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if model:
        params["model"] = model
    params["group_by"] = group_by

    try:
        data = await client.get("/usage", params=params)
    except RivenAPIError as exc:
        return f"Failed to fetch usage: {exc.detail}"

    if not isinstance(data, dict):
        return f"Unexpected response: {data}"

    # Format output
    period = data.get("period", "N/A")
    total_tokens = data.get("total_tokens", 0)
    total_cost = data.get("total_cost", 0.0)
    total_requests = data.get("total_requests", 0)

    lines: list[str] = [
        f"# Usage Report ({period})\n",
        f"- Total requests: {total_requests:,}",
        f"- Total tokens: {total_tokens:,}",
        f"- Total cost: ${total_cost:.4f}",
    ]

    # Breakdown
    breakdown = data.get("breakdown", data.get("groups", []))
    if breakdown:
        lines.append("\n## Breakdown\n")
        for entry in breakdown:
            key = entry.get("key", entry.get("model", entry.get("date", "unknown")))
            tokens = entry.get("tokens", entry.get("total_tokens", 0))
            cost = entry.get("cost", entry.get("total_cost", 0.0))
            requests = entry.get("requests", entry.get("total_requests", 0))
            lines.append(
                f"- **{key}**: {requests:,} requests, "
                f"{tokens:,} tokens, ${cost:.4f}"
            )

    return "\n".join(lines)


def register(server: MCPServer) -> None:
    """Register the get_usage tool on the MCP server."""

    @server.tool()
    @tool_handler("get_usage")
    async def get_usage(
        start_date: str | None = None,
        end_date: str | None = None,
        model: str | None = None,
        group_by: str = "model",
    ) -> str:
        """Query token usage and cost data from the Riven platform.

        Args:
            start_date: Start date (ISO 8601, e.g. "2025-01-01"). Defaults to 30 days ago.
            end_date: End date (ISO 8601). Defaults to today.
            model: Filter to a specific model ID. If omitted, returns all models.
            group_by: How to group results: "model", "day", or "model_day".
                      Default: "model".

        Returns:
            A formatted usage report with total tokens, costs, and per-model
            or per-day breakdowns.
        """
        return await _get_usage_impl(
            start_date=start_date,
            end_date=end_date,
            model=model,
            group_by=group_by,
        )
