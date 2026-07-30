"""Resource: Model catalog (JSON).

Exposes the full model catalog as a read-only MCP resource at
`riven://models/catalog`.
"""

from __future__ import annotations

import json
import logging

from mcp.server import MCPServer

from ..client import RivenAPIError, get_client

logger = logging.getLogger(__name__)


async def _fetch_catalog() -> str:
    """Fetch the model catalog and return as JSON string."""
    client = get_client()
    try:
        data = await client.get("/models")
    except RivenAPIError as exc:
        return json.dumps({"error": exc.detail, "status_code": exc.status_code})

    models = data.get("data", data) if isinstance(data, dict) else data

    # Enrich with summary info
    catalog: dict[str, object] = {
        "total_models": len(models) if isinstance(models, list) else 0,
        "providers": _extract_providers(models),
        "models": models,
    }
    return json.dumps(catalog, indent=2, default=str)


def _extract_providers(models: list) -> list[str]:
    """Extract unique provider names."""
    if not isinstance(models, list):
        return []
    providers = set()
    for m in models:
        provider = m.get("owned_by", m.get("provider", "unknown"))
        providers.add(provider)
    return sorted(providers)


def register(server: MCPServer) -> None:
    """Register the model catalog resource on the MCP server."""

    @server.resource("riven://models/catalog")
    async def model_catalog() -> str:
        """Full model catalog with 75+ models from all providers.

        Returns JSON with model IDs, names, providers, context windows,
        capabilities, and pricing for every model on the Riven platform.
        """
        return await _fetch_catalog()
