"""Prompt: Migration planner (OpenAI to Riven).

Helps users plan a migration from direct OpenAI API usage to the Riven
platform, covering model mappings, code changes, and cost comparisons.
"""

from __future__ import annotations

import logging

from mcp.server import MCPServer

logger = logging.getLogger(__name__)


def register(server: MCPServer) -> None:
    """Register the migration planner prompt on the MCP server."""

    @server.prompt()
    def migration_planner(
        current_models: str,
        monthly_volume: str = "1000000",
        priority: str = "cost",
    ) -> str:
        """Plan a migration from OpenAI to the Riven AI platform.

        Args:
            current_models: Comma-separated OpenAI model IDs currently in use (e.g. "gpt-4,gpt-3.5-turbo,gpt-4o").
            monthly_volume: Approximate monthly token volume (e.g. "1000000").
            priority: Migration priority: "cost" (minimize spend), "latency" (minimize latency), "quality" (maintain quality), "all" (balanced).
        """
        models = [m.strip() for m in current_models.split(",") if m.strip()]
        models_list = ", ".join(models) if models else "none specified"

        return f"""You are a migration planner helping a user move from OpenAI's API to the Riven AI platform. Riven is OpenAI-compatible, so code changes are minimal — the main work is model mapping and cost optimization.

## Current Setup

- **OpenAI models in use:** {models_list}
- **Monthly token volume:** {monthly_volume:,}
- **Migration priority:** {priority}

## Instructions

1. Call `list_models` to get the full Riven model catalog.
2. For each OpenAI model the user currently uses, identify the best Riven equivalent:
   - Check if the same model is available on Riven (many OpenAI models are).
   - If not, find the closest alternative by capability and context length.
3. Call `compare_models` comparing the OpenAI models with their Riven equivalents.
4. Call `get_model_pricing` for each recommended Riven model.
5. Calculate cost comparison: OpenAI direct vs Riven for the same monthly volume.

## Migration Plan Sections

### 1. Model Mapping Table

For each current OpenAI model, provide:

| OpenAI Model | Riven Equivalent | Same Model? | Context Match | Capability Match |
|---|---|---|---|---|
| [model] | [riven model] | Yes/No | [comparison] | [comparison] |

### 2. Code Changes

Since Riven is OpenAI-compatible, the only change needed is the base URL and API key:

**Before (OpenAI):**
```python
from openai import OpenAI
client = OpenAI(api_key="sk-...")
```

**After (Riven):**
```python
from openai import OpenAI
client = OpenAI(
    base_url="https://api.rivenai.io/v1",
    api_key="riv_live_..."
)
```

Note any model ID changes needed in existing code.

### 3. Cost Comparison

| Model | OpenAI $/1M tokens | Riven $/1M tokens | Savings % |
|---|---|---|---|
| [model] | [price] | [price] | [X]% |

- **Current monthly cost (OpenAI):** $[amount]
- **Projected monthly cost (Riven):** $[amount]
- **Monthly savings:** $[amount] ([X]%)

### 4. Additional Benefits

- **Intelligent routing:** Riven can auto-select cheaper models for simple requests.
- **On-prem option:** GLM-5.2 on A100 for privacy-sensitive workloads.
- **Unified billing:** Single Stripe invoice across all providers.
- **Fallback resilience:** Automatic model fallback if a provider goes down.

### 5. Migration Checklist

- [ ] Generate Riven API key at dashboard.rivenai.io
- [ ] Update base_url in OpenAI client configuration
- [ ] Update API key in environment/secrets
- [ ] Replace any hardcoded OpenAI model IDs with Riven equivalents
- [ ] Test with a small batch of requests
- [ ] Set up billing alerts in Riven dashboard
- [ ] Monitor usage via `get_usage` tool
- [ ] Consider enabling intelligent routing for cost savings
- [ ] Update any rate-limit assumptions (Riven: 100 req/min standard plan)

### 6. Risk Assessment

- **Model availability:** Confirm all needed models are available on Riven.
- **Latency differences:** Test response times — Riven adds minimal overhead.
- **Feature parity:** Verify any OpenAI-specific features (e.g., Assistants API) have equivalents.
"""
