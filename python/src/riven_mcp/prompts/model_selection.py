"""Prompt: Model selection advisor.

Helps users choose the right model for their use case based on
requirements like cost, latency, context length, and capabilities.
"""

from __future__ import annotations

import logging

from mcp.server import MCPServer

logger = logging.getLogger(__name__)


def register(server: MCPServer) -> None:
    """Register the model selection advisor prompt on the MCP server."""

    @server.prompt()
    def model_selection_advisor(
        task_description: str,
        max_budget_per_request: str = "0.50",
        max_latency_ms: str = "2000",
        required_capabilities: str = "",
        context_length_needed: str = "",
    ) -> str:
        """Advisor for selecting the optimal Riven model for a task.

        Args:
            task_description: What you want the model to do (e.g. "summarize long documents", "code generation", "vision analysis").
            max_budget_per_request: Maximum cost per request in USD (e.g. "0.50").
            max_latency_ms: Maximum acceptable latency in milliseconds (e.g. "2000").
            required_capabilities: Comma-separated capabilities needed (e.g. "vision,function_calling,json_mode").
            context_length_needed: Approximate context length needed (e.g. "128000").
        """
        caps = [c.strip() for c in required_capabilities.split(",") if c.strip()] if required_capabilities else []
        caps_str = ", ".join(caps) if caps else "none specified"

        ctx = context_length_needed if context_length_needed else "not specified"

        return f"""You are a model selection advisor for the Riven AI platform. Your job is to recommend the best AI model for a given task.

## User Requirements

- **Task:** {task_description}
- **Budget per request:** ${max_budget_per_request}
- **Max latency:** {max_latency_ms}ms
- **Required capabilities:** {caps_str}
- **Context length needed:** {ctx} tokens

## Instructions

1. First, call the `list_models` tool to get the full catalog of available models.
2. Filter models by the required capabilities and context length.
3. Call `compare_models` on the top candidates to get detailed pricing, latency, and capability comparisons.
4. Call `get_model_pricing` for the top 2-3 candidates to get detailed cost breakdowns.
5. Evaluate each candidate against the user's budget and latency constraints.

## Output Format

Provide your recommendation as:

### Recommended Model
- **Model ID:** [the recommended model]
- **Why:** [2-3 sentences explaining why this model is the best fit]

### Alternatives
- List 1-2 alternative models with brief justifications

### Cost Estimate
- Estimated cost per request: $[amount]
- Estimated cost per 1K requests: $[amount]

### Notes
- Any caveats, limitations, or configuration tips
"""
