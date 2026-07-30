"""Tool: check_model_health — Health check for on-prem models.

Checks the health status of on-prem hosted models (e.g. GLM-5.2 on A100 GPU)
by querying the internal health endpoint.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from mcp.server import MCPServer

from ..client import RivenAPIError, get_client
from ..config import get_settings
from ._helpers import tool_handler

logger = logging.getLogger(__name__)


async def _check_onprem_health() -> dict[str, Any]:
    """Check the on-prem GPU health endpoint directly."""
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.get(s.onprem_health_url)
        if response.status_code == 200:
            return response.json()
        return {
            "status": "unhealthy",
            "error": f"HTTP {response.status_code}",
            "endpoint": s.onprem_health_url,
        }
    except httpx.ConnectError:
        return {
            "status": "unreachable",
            "error": f"Cannot connect to {s.onprem_health_url}",
            "endpoint": s.onprem_health_url,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "endpoint": s.onprem_health_url,
        }


async def _check_cloud_health() -> list[dict[str, Any]]:
    """Check cloud model availability via the Riven API."""
    client = get_client()
    try:
        data = await client.get("/models")
        models = data.get("data", data) if isinstance(data, dict) else data
        results: list[dict[str, Any]] = []
        for m in models if isinstance(models, list) else []:
            mid = m.get("id", "unknown")
            status = m.get("status", m.get("availability", "available"))
            if status in ("available", "active", "online", "live", None):
                results.append({"model": mid, "status": "healthy"})
            else:
                results.append({"model": mid, "status": status})
        return results
    except RivenAPIError as exc:
        return [{"model": "api", "status": "error", "error": exc.detail}]


async def _check_model_health_impl(
    model: str | None,
    check_type: str,
) -> str:
    """Run health checks and format results."""
    lines: list[str] = ["# Model Health Check\n"]

    if check_type in ("onprem", "all"):
        lines.append("## On-Prem (GLM-5.2 / A100 GPU)\n")
        onprem = await _check_onprem_health()

        status = onprem.get("status", "unknown")
        icon = "OK" if status in ("healthy", "ok", "up", "ready") else "FAIL"
        lines.append(f"- Status: [{icon}] {status}")

        if "gpu" in onprem:
            gpu = onprem["gpu"]
            lines.append(f"- GPU: {gpu.get('name', 'A100')}")
            lines.append(f"- GPU utilization: {gpu.get('utilization', 'N/A')}%")
            lines.append(f"- GPU memory: {gpu.get('memory_used', 'N/A')}/{gpu.get('memory_total', 'N/A')} MB")

        if "model" in onprem:
            lines.append(f"- Model loaded: {onprem['model']}")
        if "uptime" in onprem:
            lines.append(f"- Uptime: {onprem['uptime']}")
        if "queue" in onprem:
            lines.append(f"- Queue depth: {onprem['queue']}")
        if "error" in onprem:
            lines.append(f"- Error: {onprem['error']}")

        lines.append("")

    if check_type in ("cloud", "all"):
        lines.append("## Cloud Models\n")
        cloud = await _check_cloud_health()

        if model:
            cloud = [c for c in cloud if c.get("model") == model or model in c.get("model", "")]

        healthy = sum(1 for c in cloud if c.get("status") in ("healthy", "available", "active", "live"))
        total = len(cloud)
        lines.append(f"- {healthy}/{total} models healthy\n")

        for entry in cloud[:20]:  # Limit output
            mid = entry.get("model", "unknown")
            st = entry.get("status", "unknown")
            icon = "OK" if st in ("healthy", "available", "active", "live") else "FAIL"
            lines.append(f"- [{icon}] {mid}: {st}")
            if "error" in entry:
                lines.append(f"  Error: {entry['error']}")

        if total > 20:
            lines.append(f"- ... and {total - 20} more")

    if check_type == "onprem" and model:
        lines.insert(2, f"(Filtered for: {model})")

    return "\n".join(lines)


def register(server: MCPServer) -> None:
    """Register the check_model_health tool on the MCP server."""

    @server.tool()
    @tool_handler("check_model_health")
    async def check_model_health(
        model: str | None = None,
        check_type: str = "all",
    ) -> str:
        """Check the health status of Riven-hosted models.

        For on-prem models (GLM-5.2 on A100 GPU), queries the internal
        health endpoint directly, reporting GPU utilization, memory,
        model load status, and queue depth.

        For cloud models, checks availability via the Riven API.

        Args:
            model: Filter results to a specific model ID. If omitted, checks all.
            check_type: What to check:
                        - "onprem": Only on-prem GPU models
                        - "cloud": Only cloud-hosted models
                        - "all": Both (default)

        Returns:
            A formatted health report with per-model status indicators,
            GPU metrics, and any error details.
        """
        return await _check_model_health_impl(model=model, check_type=check_type)
