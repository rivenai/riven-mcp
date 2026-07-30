"""Tool: route_request — Use Riven's intelligent model routing.

Leverages Riven's gateway to automatically select the best model for a
given prompt based on cost, latency, and capability requirements.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from ..client import RivenAPIError, get_client
from ._helpers import tool_handler

logger = logging.getLogger(__name__)


async def _route_request_impl(
    messages: list[dict[str, Any]],
    strategy: str,
    max_cost: float | None,
    max_latency_ms: int | None,
    required_capabilities: list[str] | None,
    preferred_providers: list[str] | None,
    fallback: bool,
) -> str:
    """Use Riven's intelligent routing to select a model and generate a response."""
    client = get_client()

    body: dict[str, Any] = {
        "messages": messages,
        "routing": {
            "strategy": strategy,
            "fallback": fallback,
        },
    }
    if max_cost is not None:
        body["routing"]["max_cost_per_request"] = max_cost
    if max_latency_ms is not None:
        body["routing"]["max_latency_ms"] = max_latency_ms
    if required_capabilities:
        body["routing"]["required_capabilities"] = required_capabilities
    if preferred_providers:
        body["routing"]["preferred_providers"] = preferred_providers

    try:
        result = await client.post("/route", json=body)
    except RivenAPIError as exc:
        # Fallback: try standard chat/completions with auto-routing header
        if exc.status_code == 404:
            try:
                result = await client.post(
                    "/chat/completions",
                    json={
                        "model": "auto",
                        "messages": messages,
                        "routing_strategy": strategy,
                        "fallback": fallback,
                    },
                )
            except RivenAPIError as exc2:
                return f"Routing failed: {exc2.detail}"
        else:
            return f"Routing failed: {exc.detail}"

    # Extract routing metadata
    routing_info = result.get("routing", result.get("model_info", {}))
    selected_model = routing_info.get("selected_model", result.get("model", "unknown"))
    route_reason = routing_info.get("reason", routing_info.get("selection_reason", "N/A"))
    fallback_used = routing_info.get("fallback_used", False)
    fallback_chain = routing_info.get("fallback_chain", [])

    # Extract completion
    choices = result.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
    else:
        content = str(result)

    # Usage
    usage = result.get("usage", {})
    usage_str = ""
    if usage:
        usage_str = (
            f"\nTokens: {usage.get('prompt_tokens', '?')} in / "
            f"{usage.get('completion_tokens', '?')} out"
        )

    summary = (
        f"{content}\n\n"
        f"---\n"
        f"Routed to: {selected_model}\n"
        f"Strategy: {strategy}\n"
        f"Reason: {route_reason}\n"
        f"Fallback used: {'Yes' if fallback_used else 'No'}"
    )
    if fallback_chain:
        summary += f"\nFallback chain: {' -> '.join(fallback_chain)}"
    if usage_str:
        summary += usage_str

    return summary


def register(server: MCPServer) -> None:
    """Register the route_request tool on the MCP server."""

    @server.tool()
    @tool_handler("route_request")
    async def route_request(
        messages: list[dict[str, Any]],
        strategy: str = "balanced",
        max_cost: float | None = None,
        max_latency_ms: int | None = None,
        required_capabilities: list[str] | None = None,
        preferred_providers: list[str] | None = None,
        fallback: bool = True,
    ) -> str:
        """Use Riven's intelligent model routing to auto-select the best model.

        The Riven gateway evaluates cost, latency, and capability constraints
        to pick the optimal model for each request, with automatic fallback
        if the primary model fails.

        Args:
            messages: Chat messages in OpenAI format (role + content).
            strategy: Routing strategy: "cheapest", "fastest", "balanced",
                      "highest_quality". Default: "balanced".
            max_cost: Maximum cost per request (USD). Models exceeding this
                      are excluded from selection.
            max_latency_ms: Maximum acceptable latency in milliseconds.
            required_capabilities: Capabilities the model must support
                                   (e.g. ["vision", "function_calling", "json_mode"]).
            preferred_providers: Provider preference order (e.g. ["anthropic", "openai"]).
            fallback: If True, automatically fall back to alternative models
                      if the primary selection fails. Default: True.

        Returns:
            The completion text plus routing metadata (selected model,
            strategy, reason, fallback chain).
        """
        return await _route_request_impl(
            messages=messages,
            strategy=strategy,
            max_cost=max_cost,
            max_latency_ms=max_latency_ms,
            required_capabilities=required_capabilities,
            preferred_providers=preferred_providers,
            fallback=fallback,
        )
