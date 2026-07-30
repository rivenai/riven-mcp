"""Tool: chat_completion — Send a chat completion request.

Wraps the Riven OpenAI-compatible /chat/completions endpoint, adding
cost estimation and guardrail enforcement before the request is sent.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from ..client import RivenAPIError, get_client
from ..security import get_cost_guardrail
from ._helpers import get_client_id as _get_cid, tool_handler

logger = logging.getLogger(__name__)

# Rough token-per-character heuristic for cost estimation.
# Production would use a proper tokenizer (tiktoken, etc.).
_CHARS_PER_TOKEN = 4.0


def _estimate_tokens(messages: list[dict[str, Any]], max_tokens: int) -> tuple[int, int]:
    """Estimate input and output token counts.

    Returns (estimated_input_tokens, estimated_output_tokens).
    """
    input_chars = sum(len(str(m.get("content", ""))) for m in messages)
    est_input = int(input_chars / _CHARS_PER_TOKEN)
    est_output = max_tokens
    return est_input, est_output


def _estimate_cost(
    model: str,
    est_input: int,
    est_output: int,
    pricing: dict[str, float],
) -> float:
    """Estimate cost based on token counts and per-1M-token pricing."""
    in_per_1m = pricing.get("input_per_1m", 0)
    out_per_1m = pricing.get("output_per_1m", 0)
    # Convert per-1M to per-token for multiplication
    return (est_input * in_per_1m / 1_000_000) + (est_output * out_per_1m / 1_000_000)


async def _chat_completion_impl(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None,
    max_tokens: int | None,
    stream: bool,
    top_p: float | None,
    stop: str | list[str] | None,
    **extra: Any,
) -> str:
    """Execute a chat completion request via the Riven API."""
    client = get_client()

    # Enforce max_tokens for cost estimation
    effective_max = max_tokens or 1024

    # Estimate tokens and cost
    est_input, est_output = _estimate_tokens(messages, effective_max)

    # Try to fetch pricing for this model (best-effort)
    pricing: dict[str, float] = {}
    try:
        models_data = await client.get("/models")
        models_list = models_data.get("data", []) if isinstance(models_data, dict) else models_data
        for m in models_list:
            if m.get("id") == model:
                p = m.get("pricing") or {}
                # API returns per-1M-token rates
                pricing = {
                    "input_per_1m": float(p.get("prompt_usd_per_1m", 0)),
                    "output_per_1m": float(p.get("completion_usd_per_1m", 0)),
                }
                break
    except Exception:
        logger.debug("Could not fetch pricing for cost estimation", extra={"model": model})

    est_cost = _estimate_cost(model, est_input, est_output, pricing)

    # Cost guardrail check
    guardrail = get_cost_guardrail()
    client_id = _get_cid()
    allowed, reason = guardrail.check_request(client_id, est_cost)
    if not allowed:
        return (
            f"Request blocked by cost guardrail.\n\n"
            f"Model: {model}\n"
            f"Estimated input tokens: {est_input}\n"
            f"Estimated output tokens: {est_output}\n"
            f"Estimated cost: ${est_cost:.4f}\n\n"
            f"Reason: {reason}"
        )

    # Build request body (OpenAI-compatible)
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": effective_max,
        "stream": stream,
    }
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p
    if stop is not None:
        body["stop"] = stop
    body.update(extra)

    try:
        result = await client.post("/chat/completions", json=body)
    except RivenAPIError as exc:
        return f"Chat completion failed: {exc.detail}"

    # Record actual cost
    usage = result.get("usage", {}) if isinstance(result, dict) else {}
    actual_input = usage.get("prompt_tokens", est_input)
    actual_output = usage.get("completion_tokens", est_output)
    actual_cost = _estimate_cost(model, actual_input, actual_output, pricing)
    guardrail.record_spend(client_id, actual_cost)

    # Format response
    choices = result.get("choices", [])
    if not choices:
        return f"No completion returned.\n\nFull response: {result}"

    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content", "")
    # Reasoning models (e.g. GLM-4.7) may return reasoning instead of content
    reasoning = message.get("reasoning", "")
    finish_reason = choice.get("finish_reason", "unknown")

    # If content is empty but reasoning exists, show reasoning
    if not content and reasoning:
        content = f"[Reasoning]\n{reasoning}"

    summary = (
        f"{content}\n\n"
        f"---\n"
        f"Model: {result.get('model', model)} | Finish: {finish_reason}\n"
        f"Tokens: {actual_input} in / {actual_output} out\n"
        f"Cost: ${actual_cost:.4f}"
    )
    return summary


def register(server: MCPServer) -> None:
    """Register the chat_completion tool on the MCP server."""

    @server.tool()
    @tool_handler("chat_completion")
    async def chat_completion(
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
    ) -> str:
        """Send a chat completion request to a Riven-hosted model.

        Args:
            model: Model ID (e.g. "gpt-4o", "claude-3.5-sonnet", "glm-5.2").
                   Use list_models to see all available model IDs.
            messages: Array of message objects with "role" and "content".
                      Roles: "system", "user", "assistant".
            temperature: Sampling temperature (0-2). Default: model default.
            max_tokens: Maximum tokens to generate. Default: 1024.
            stream: Whether to stream the response. Default: False.
            top_p: Nucleus sampling parameter (0-1). Default: model default.
            stop: Stop sequence(s) that halt generation.

        Returns:
            The completion text followed by usage and cost metadata.

        The Riven API is OpenAI-compatible — use standard message format:
        [{"role": "system", "content": "You are helpful."},
         {"role": "user", "content": "Hello!"}]
        """
        return await _chat_completion_impl(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            top_p=top_p,
            stop=stop,
        )
