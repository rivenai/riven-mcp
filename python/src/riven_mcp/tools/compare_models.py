"""Tool: compare_models — Compare models by price, latency, and capability.

Fetches the model catalog and produces a comparison table for the
specified models across multiple dimensions.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from ..client import RivenAPIError, get_client
from ._helpers import tool_handler

logger = logging.getLogger(__name__)


async def _compare_models_impl(
    models: list[str],
    criteria: list[str],
) -> str:
    """Fetch model data and build a comparison table."""
    client = get_client()

    try:
        data = await client.get("/models")
    except RivenAPIError as exc:
        return f"Failed to fetch models: {exc.detail}"

    all_models = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(all_models, list):
        return f"Unexpected response: {data}"

    # Build lookup by model ID
    model_map: dict[str, dict[str, Any]] = {}
    for m in all_models:
        mid = m.get("id", "")
        if mid:
            model_map[mid] = m

    # Validate requested models
    not_found = [m for m in models if m not in model_map]
    if not_found:
        available = ", ".join(sorted(model_map.keys())[:20])
        return (
            f"Models not found: {', '.join(not_found)}\n\n"
            f"Some available models: {available}..."
        )

    # Build comparison
    lines: list[str] = [f"# Model Comparison ({len(models)} models)\n"]

    # Header
    valid_criteria = [c for c in criteria if c in ("price", "latency", "capability", "context")]
    if not valid_criteria:
        valid_criteria = ["price", "latency", "capability", "context"]

    header_cells = ["Model"]
    for c in valid_criteria:
        header_cells.append(c.replace("_", " ").title())
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("|" + "|".join(["---"] * len(header_cells)) + "|")

    # Rows
    cheapest = None
    cheapest_cost = float("inf")
    largest_ctx = None
    largest_ctx_size = 0

    for mid in models:
        m = model_map[mid]
        row_cells = [mid]

        for c in valid_criteria:
            if c == "price":
                pricing = m.get("pricing", {})
                in_p = _to_float(pricing.get("input", 0)) * 1000
                out_p = _to_float(pricing.get("output", 0)) * 1000
                row_cells.append(f"${in_p:.4f}/${out_p:.4f} per 1K")
                total = in_p + out_p
                if total < cheapest_cost:
                    cheapest_cost = total
                    cheapest = mid
            elif c == "latency":
                lat = m.get("latency_ms", m.get("avg_latency_ms", "N/A"))
                row_cells.append(f"{lat}ms" if isinstance(lat, (int, float)) else str(lat))
            elif c == "capability":
                caps = m.get("capabilities", [])
                if isinstance(caps, list):
                    row_cells.append(", ".join(caps) if caps else "standard")
                elif isinstance(caps, dict):
                    active = [k for k, v in caps.items() if v]
                    row_cells.append(", ".join(active) if active else "standard")
                else:
                    row_cells.append(str(caps))
            elif c == "context":
                ctx = m.get("context_length", m.get("max_context", "N/A"))
                if isinstance(ctx, int) and ctx > largest_ctx_size:
                    largest_ctx_size = ctx
                    largest_ctx = mid
                row_cells.append(f"{ctx:,}" if isinstance(ctx, int) else str(ctx))

        lines.append("| " + " | ".join(row_cells) + " |")

    # Recommendations
    lines.append("\n## Recommendations\n")
    if cheapest:
        lines.append(f"- **Cheapest**: {cheapest} (${cheapest_cost:.4f}/1K total)")
    if largest_ctx:
        lines.append(f"- **Largest context**: {largest_ctx} ({largest_ctx_size:,} tokens)")

    return "\n".join(lines)


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def register(server: MCPServer) -> None:
    """Register the compare_models tool on the MCP server."""

    @server.tool()
    @tool_handler("compare_models")
    async def compare_models(
        models: list[str],
        criteria: list[str] | None = None,
    ) -> str:
        """Compare AI models by price, latency, context window, and capabilities.

        Args:
            models: List of model IDs to compare (e.g. ["gpt-4o", "claude-3.5-sonnet"]).
            criteria: Dimensions to compare: "price", "latency", "capability", "context".
                      Default: all four.

        Returns:
            A Markdown comparison table with per-model pricing, latency,
            context window, and supported capabilities, plus recommendations.
        """
        return await _compare_models_impl(
            models=models,
            criteria=criteria or ["price", "latency", "capability", "context"],
        )
