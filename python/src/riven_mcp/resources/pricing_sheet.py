"""Resource: Pricing sheet (JSON).

Exposes the complete pricing sheet as a read-only MCP resource at
`riven://pricing/sheet`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import MCPServer

from ..client import RivenAPIError, get_client

logger = logging.getLogger(__name__)


async def _fetch_pricing() -> str:
    """Fetch pricing data and return as structured JSON."""
    client = get_client()
    try:
        data = await client.get("/pricing")
    except RivenAPIError:
        # Fall back to deriving pricing from the models endpoint
        try:
            models_data = await client.get("/models")
            models = models_data.get("data", models_data) if isinstance(models_data, dict) else models_data
            pricing_entries = [_extract_pricing(m) for m in models] if isinstance(models, list) else []
            data = {"pricing": pricing_entries}
        except RivenAPIError as exc:
            return json.dumps({"error": exc.detail, "status_code": exc.status_code})

    pricing_list = data.get("pricing", data.get("data", [])) if isinstance(data, dict) else data

    sheet: dict[str, Any] = {
        "currency": "USD",
        "billing_unit": "per-token",
        "note": "All prices are per token. Multiply by 1000 for per-1K, 1,000,000 for per-1M.",
        "models": pricing_list,
    }

    # Add summary stats
    if isinstance(pricing_list, list) and pricing_list:
        all_costs = []
        for entry in pricing_list:
            p = entry.get("pricing", entry)
            in_cost = _to_float(p.get("input", 0))
            out_cost = _to_float(p.get("output", 0))
            all_costs.append(in_cost + out_cost)

        if all_costs:
            sheet["summary"] = {
                "cheapest_per_1k": f"${min(all_costs) * 1000:.6f}",
                "most_expensive_per_1k": f"${max(all_costs) * 1000:.6f}",
                "average_per_1k": f"${(sum(all_costs) / len(all_costs)) * 1000:.6f}",
            }

    return json.dumps(sheet, indent=2, default=str)


def _extract_pricing(model: dict[str, Any]) -> dict[str, Any]:
    """Extract pricing-relevant fields from a model entry."""
    pricing = model.get("pricing", {})
    return {
        "model_id": model.get("id", "unknown"),
        "name": model.get("name", model.get("id", "unknown")),
        "provider": model.get("owned_by", "unknown"),
        "context_window": model.get("context_length", model.get("max_context")),
        "pricing": {
            "input_per_token": pricing.get("input", 0),
            "output_per_token": pricing.get("output", 0),
            "cached_input_per_token": pricing.get("cached_input"),
        },
        "bulk_discounts": model.get("bulk_discounts", []),
    }


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def register(server: MCPServer) -> None:
    """Register the pricing sheet resource on the MCP server."""

    @server.resource("riven://pricing/sheet")
    async def pricing_sheet() -> str:
        """Complete pricing sheet for all models.

        Returns JSON with per-token input/output pricing, cached input
        rates, volume discounts, and summary statistics (cheapest,
        most expensive, average cost per 1K tokens).
        """
        return await _fetch_pricing()
