"""Prompt: Cost optimization analyzer.

Analyzes current usage patterns and recommends cost-saving strategies
across the Riven platform.
"""

from __future__ import annotations

import logging

from mcp.server import MCPServer

logger = logging.getLogger(__name__)


def register(server: MCPServer) -> None:
    """Register the cost optimization analyzer prompt on the MCP server."""

    @server.prompt()
    def cost_optimization_analyzer(
        timeframe: str = "30",
        target_reduction_percent: str = "20",
    ) -> str:
        """Analyzer for reducing AI costs on the Riven platform.

        Args:
            timeframe: Number of days of usage history to analyze (e.g. "30").
            target_reduction_percent: Target cost reduction percentage (e.g. "20").
        """
        return f"""You are a cost optimization analyst for the Riven AI platform. Your goal is to identify cost-saving opportunities.

## Objective

Analyze usage data from the last {timeframe} days and recommend strategies to reduce costs by {target_reduction_percent}%.

## Instructions

1. Call `get_usage` with no date filter to get current period usage.
2. Call `get_usage` with `start_date` set to {timeframe} days ago and `group_by="model"` to see per-model costs.
3. Call `get_usage` with the same date range and `group_by="day"` to identify usage patterns.
4. Call `get_billing` with `detail="balance"` to check current balance and monthly spend.
5. For the top 3 most expensive models, call `get_model_pricing` to get detailed pricing.
6. Call `compare_models` comparing expensive models with cheaper alternatives.

## Analysis Framework

Evaluate these cost-saving strategies:

### 1. Model Right-Sizing
- Are expensive models used for tasks that cheaper models could handle?
- Compare per-request costs of the current model vs alternatives.

### 2. Caching Opportunities
- Are there repeated identical requests that could be cached?
- Riven supports cached input pricing for some models.

### 3. Routing Optimization
- Would Riven's intelligent routing (`route_request`) reduce costs?
- Compare current model selections vs "cheapest" routing strategy.

### 4. Token Optimization
- Are prompts unnecessarily long? Could system prompts be shortened?
- Are max_tokens settings too high?

### 5. Provider Migration
- Could on-prem GLM-5.2 replace cloud models for some workloads?
- Are there open-source alternatives on Fireworks that are cheaper?

## Output Format

### Current Spend Summary
- Total spend ({timeframe} days): $[amount]
- Top 3 most expensive models: [list with costs]

### Recommendations (to achieve {target_reduction_percent}% reduction)
For each recommendation:
- **Strategy:** [name]
- **Action:** [specific action]
- **Estimated savings:** $[amount]/month
- **Risk/impact:** [assessment]

### Projected Savings
- Total estimated monthly savings: $[amount]
- Percentage reduction: [X]%
"""
