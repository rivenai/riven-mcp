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
        mname = model.get("name", mid)
        owner = model.get("owned_by", "unknown")
        ctx = model.get("context_length", model.get("max_context", "N/A"))

        # Pricing (per 1K tokens, Riven returns per-token)
        pricing = model.get("pricing", {})
        input_price = _format_price(pricing.get("input", 0))
        output_price = _format_price(pricing.get("output", 0))

        lines.append(
            f"- **{mid}** ({mname})\n"
            f"  - Provider: {owner}\n"
            f"  - Context: {ctx} tokens\n"
            f"  - Pricing: ${input_price}/1K input, ${output_price}/1K output"
        )

    return "\n".join(lines)


def _format_price(per_token: float | str | None) -> str:
    """Convert per-token price to per-1K-tokens display."""
    if per_token is None:
        return "N/A"
    try:
        return f"{float(per_token) * 1000:.6f}"
    except (TypeError, ValueError):
        return str(per_token)


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
