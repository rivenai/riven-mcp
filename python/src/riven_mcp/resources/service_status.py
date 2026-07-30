"""Resource: Service status (JSON).

Exposes live service status as a read-only MCP resource at
`riven://status/service`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx
from mcp.server import MCPServer

from ..client import RivenAPIError, get_client
from ..config import get_settings

logger = logging.getLogger(__name__)


async def _fetch_status() -> str:
    """Aggregate service status from multiple sources."""
    s = get_settings()
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    status: dict[str, object] = {
        "timestamp": now,
        "overall": "operational",
        "services": {},
    }

    # 1. API gateway health
    try:
        await client.get("/models")
        status["services"]["api_gateway"] = {"status": "operational", "latency_ms": None}
    except RivenAPIError as exc:
        status["services"]["api_gateway"] = {"status": "degraded", "error": exc.detail}
        status["overall"] = "degraded"
    except Exception as exc:
        status["services"]["api_gateway"] = {"status": "down", "error": str(exc)}
        status["overall"] = "major_outage"

    # 2. On-prem GPU health
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.get(s.onprem_health_url)
        if resp.status_code == 200:
            gpu_data = resp.json()
            status["services"]["onprem_gpu"] = {
                "status": "operational",
                "gpu": gpu_data.get("gpu", {}),
                "model": gpu_data.get("model", "glm-5.2"),
            }
        else:
            status["services"]["onprem_gpu"] = {"status": "degraded", "code": resp.status_code}
            if status["overall"] == "operational":
                status["overall"] = "degraded"
    except Exception as exc:
        status["services"]["onprem_gpu"] = {"status": "unreachable", "error": str(exc)}
        if status["overall"] == "operational":
            status["overall"] = "degraded"

    # 3. Billing service (Stripe)
    try:
        await client.get("/billing/balance")
        status["services"]["billing"] = {"status": "operational"}
    except RivenAPIError:
        status["services"]["billing"] = {"status": "degraded"}
        if status["overall"] == "operational":
            status["overall"] = "degraded"
    except Exception:
        # Don't fail overall status for billing check errors
        status["services"]["billing"] = {"status": "unknown"}

    # 4. IndexNow (passive — no health check needed)
    status["services"]["indexnow"] = {"status": "passive"}

    return json.dumps(status, indent=2, default=str)


def register(server: MCPServer) -> None:
    """Register the service status resource on the MCP server."""

    @server.resource("riven://status/service")
    async def service_status() -> str:
        """Live service status for all Riven platform components.

        Returns JSON with aggregate status and per-service health for:
        API gateway, on-prem GPU (GLM-5.2/A100), billing (Stripe), and
        IndexNow. Statuses: operational, degraded, down, unreachable.
        """
        return await _fetch_status()
