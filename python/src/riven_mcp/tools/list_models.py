"""Tool: list_models — List available models with pricing.

Calls the Riven API /models endpoint and returns a formatted catalog
of all available models with their pricing information.
"""

from __future__ import annotations

import logging

from mcp.server import MCPServer

from ..client import RivenAPIError, get_client
from ._helpers import tool_handler

logger = logging.getLogger(__name__)


async def _list_models_impl() -> str:
    """Fetch and format the full model catalog from the Riven API."""
    client = get_client()

    try:
        data = await client.get("/models")
    except RivenAPIError as exc:
        return f"Failed to fetch models: {exc.detail}"

    models = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(models, list):
        return f"Unexpected response format: {data}"

    lines: list[str] = [f"# Available Models ({len(models)} total)\n"]

    for model in models:
        mid = model.get("id", "unknown")
        mname = model.get("name", model.get("display_name", mid))
        owner = model.get("owned_by", "unknown")
        ctx = model.get("context_length", model.get("max_context", "N/A"))

        # Pricing (API returns per-1M-token rates)
        pricing = model.get("pricing") or {}
        input_per_1m = pricing.get("prompt_usd_per_1m", 0)
        output_per_1m = pricing.get("completion_usd_per_1m", 0)
        # Convert to per-1K for display
        input_price = _format_per_1k(input_per_1m)
        output_price = _format_per_1k(output_per_1m)

        lines.append(
            f"- **{mid}** ({mname})\n"
            f"  - Provider: {owner}\n"
            f"  - Context: {ctx} tokens\n"
            f"  - Pricing: ${input_price}/1K input, ${output_price}/1K output"
        )

    return "\n".join(lines)


def _format_per_1k(per_1m: float | int | str | None) -> str:
    """Convert per-1M-token price to per-1K-tokens display."""
    if per_1m is None:
        return "N/A"
    try:
        return f"{float(per_1m) / 1000:.6f}"
    except (TypeError, ValueError):
        return str(per_1m)


def register(server: MCPServer) -> None:
    """Register the list_models tool on the MCP server."""

    @server.tool()
    @tool_handler("list_models")
    async def list_models() -> str:
        """List all available AI models on the Riven platform with pricing.

        Returns a formatted catalog of 75+ models from OpenAI, Anthropic,
        Google, Cerebras, Fireworks, and on-prem GLM, including per-token
        pricing and context window sizes.

        Use this to discover available models before making chat completion
        requests or comparing models.
        """
        return await _list_models_impl()
