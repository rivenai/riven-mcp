"""Tool: get_model_pricing — Get detailed pricing for a specific model.

Fetches comprehensive pricing information for a single model, including
per-token rates, context window pricing tiers, and bulk discount rates.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from ..client import RivenAPIError, get_client
from ._helpers import tool_handler

logger = logging.getLogger(__name__)


async def _get_model_pricing_impl(model: str) -> str:
    """Fetch detailed pricing for a specific model."""
    client = get_client()

    # Try the dedicated pricing endpoint first
    try:
        data = await client.get(f"/pricing/{model}")
    except RivenAPIError as exc:
        if exc.status_code == 404:
            # Fall back to filtering the models endpoint
            try:
                models_data = await client.get("/models")
                all_models = models_data.get("data", models_data) if isinstance(models_data, dict) else models_data
                model_entry = None
                for m in all_models if isinstance(all_models, list) else []:
                    if m.get("id") == model:
                        model_entry = m
                        break
                if model_entry:
                    data = model_entry
                else:
                    return f"Model '{model}' not found in catalog."
            except RivenAPIError as exc2:
                return f"Failed to fetch pricing: {exc2.detail}"
        else:
            return f"Failed to fetch pricing: {exc.detail}"

    # Format pricing details
    mid = data.get("id", model)
    name = data.get("name", mid)
    provider = data.get("owned_by", data.get("provider", "unknown"))
    context = data.get("context_length", data.get("max_context", "N/A"))

    pricing = data.get("pricing", data.get("price", {}))

    # Per-token prices (Riven uses per-token billing)
    input_per_token = _to_float(pricing.get("input", pricing.get("prompt", 0)))
    output_per_token = _to_float(pricing.get("output", pricing.get("completion", 0)))

    # Per-1K and per-1M conversions
    input_per_1k = input_per_token * 1000
    output_per_1k = output_per_token * 1000
    input_per_1m = input_per_token * 1_000_000
    output_per_1m = output_per_token * 1_000_000

    lines: list[str] = [
        f"# Pricing: {mid}\n",
        f"- Display name: {name}",
        f"- Provider: {provider}",
        f"- Context window: {context:,} tokens" if isinstance(context, int) else f"- Context window: {context}",
        "",
        "## Per-Token Pricing\n",
        f"- Input: ${input_per_token:.10f}/token",
        f"- Output: ${output_per_token:.10f}/token",
        "",
        "## Per-1K Tokens\n",
        f"- Input: ${input_per_1k:.6f}/1K",
        f"- Output: ${output_per_1k:.6f}/1K",
        "",
        "## Per-1M Tokens\n",
        f"- Input: ${input_per_1m:.4f}/1M",
        f"- Output: ${output_per_1m:.4f}/1M",
    ]

    # Bulk discounts
    discounts = data.get("bulk_discounts", pricing.get("tiers", []))
    if discounts:
        lines.append("\n## Volume Discounts\n")
        for tier in discounts:
            threshold = tier.get("min_tokens", tier.get("threshold", "N/A"))
            discount = tier.get("discount_percent", tier.get("discount", "N/A"))
            lines.append(f"- {threshold:,}+ tokens: {discount}% off" if isinstance(threshold, int) else f"- {threshold}: {discount}% off")

    # Cached input pricing (if different)
    cached = pricing.get("cached_input", data.get("cached_input_pricing"))
    if cached is not None:
        cached_per_1m = _to_float(cached) * 1_000_000
        lines.append(f"\n## Cached Input\n- ${cached_per_1m:.4f}/1M (discounted)")

    # Cost examples
    lines.append("\n## Example Costs\n")
    for label, in_tok, out_tok in [
        ("Short chat (100 in / 100 out)", 100, 100),
        ("Medium chat (1K in / 500 out)", 1000, 500),
        ("Long context (10K in / 2K out)", 10000, 2000),
        ("Very long (100K in / 4K out)", 100000, 4000),
    ]:
        cost = (in_tok * input_per_token) + (out_tok * output_per_token)
        lines.append(f"- {label}: ${cost:.4f}")

    return "\n".join(lines)


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def register(server: MCPServer) -> None:
    """Register the get_model_pricing tool on the MCP server."""

    @server.tool()
    @tool_handler("get_model_pricing")
    async def get_model_pricing(model: str) -> str:
        """Get detailed pricing information for a specific AI model.

        Returns per-token, per-1K, and per-1M token pricing for both
        input and output, plus volume discounts, cached input rates,
        and example cost calculations for common usage patterns.

        Args:
            model: Model ID (e.g. "gpt-4o", "claude-3.5-sonnet", "glm-5.2").
                   Use list_models to discover available model IDs.

        Returns:
            A detailed pricing breakdown with multiple rate formats and
            example cost calculations.
        """
        return await _get_model_pricing_impl(model=model)
