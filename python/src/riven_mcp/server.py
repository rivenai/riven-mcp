"""Main MCP server for Riven AI.

Exposes Riven's platform capabilities — model catalog, chat completions,
intelligent routing, billing, and on-prem health — as MCP tools, resources,
and prompts for AI agents.

Usage:
    # stdio transport (default — for Claude Desktop, Cursor, etc.)
    python -m riven_mcp.server

    # HTTP / SSE transport (for remote deployment)
    MCP_TRANSPORT=http MCP_PORT=8080 python -m riven_mcp.server

    # Via console script
    riven-mcp
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server import MCPServer

from .config import ensure_audit_dir, get_settings
from .security import get_audit_logger, setup_logging


# ─── Lifecycle ──────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[None]:
    """Manage startup and shutdown of the MCP server."""
    s = get_settings()
    setup_logging()
    ensure_audit_dir()

    audit = get_audit_logger()
    audit.log(
        event="server_start",
        client_id="system",
        tool="lifecycle",
        arguments={"transport": s.mcp_transport, "host": s.mcp_host, "port": s.mcp_port},
    )

    try:
        yield
    finally:
        # Close the shared Riven API client
        from .client import close_client

        await close_client()
        audit.log(
            event="server_stop",
            client_id="system",
            tool="lifecycle",
        )


# ─── Server Factory ──────────────────────────────────────────────────────


def create_server() -> MCPServer:
    """Create and configure the MCP server with all tools, resources, and prompts."""
    s = get_settings()

    server = MCPServer(
        name="riven-mcp-server",
        instructions=(
            "Riven AI MCP Server — provides access to 75+ AI models with "
            "transparent per-token pricing, intelligent routing, billing, "
            "and on-prem model health monitoring.\n\n"
            "Tools: list_models, chat_completion, get_usage, compare_models, "
            "route_request, get_billing, submit_indexnow, check_model_health, "
            "get_model_pricing\n\n"
            "Resources: model catalog, pricing sheet, API docs, service status\n\n"
            "Prompts: model selection advisor, cost optimization analyzer, "
            "migration planner"
        ),
    )

    # Register all tools, resources, and prompts from their modules.
    # Each module imports the shared `server` instance and registers decorators
    # at import time.
    _register_components(server)

    return server


def _register_components(server: MCPServer) -> None:
    """Import all component modules so their decorators register on the server."""
    # Tools (import order doesn't matter; decorators register on import)
    from .tools.list_models import register as _r1  # noqa: F401
    from .tools.chat_completion import register as _r2  # noqa: F401
    from .tools.get_usage import register as _r3  # noqa: F401
    from .tools.compare_models import register as _r4  # noqa: F401
    from .tools.route_request import register as _r5  # noqa: F401
    from .tools.get_billing import register as _r6  # noqa: F401
    from .tools.submit_indexnow import register as _r7  # noqa: F401
    from .tools.check_model_health import register as _r8  # noqa: F401
    from .tools.get_model_pricing import register as _r9  # noqa: F401

    # Resources
    from .resources.model_catalog import register as _rr1  # noqa: F401
    from .resources.pricing_sheet import register as _rr2  # noqa: F401
    from .resources.api_docs import register as _rr3  # noqa: F401
    from .resources.service_status import register as _rr4  # noqa: F401

    # Prompts
    from .prompts.model_selection import register as _rp1  # noqa: F401
    from .prompts.cost_optimization import register as _rp2  # noqa: F401
    from .prompts.migration_planner import register as _rp3  # noqa: F401


# ─── Entry Points ────────────────────────────────────────────────────────


def main() -> None:
    """Console entry point — start the MCP server."""
    s = get_settings()

    server = create_server()

    if s.mcp_transport == "http":
        # Streamable HTTP transport (includes SSE for streaming responses)
        server.run(
            transport="http",
            host=s.mcp_host,
            port=s.mcp_port,
        )
    else:
        # stdio transport (default — for local MCP clients)
        server.run(transport="stdio")


def main_async() -> None:
    """Async entry point for programmatic use."""
    server = create_server()
    asyncio.run(server.run_async(transport="stdio"))


if __name__ == "__main__":
    sys.exit(main())
