"""Tool: get_billing — Query billing history and balance.

Fetches billing information from the Riven API, including current
balance, Stripe payment history, and subscription details.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from ..client import RivenAPIError, get_client
from ._helpers import tool_handler

logger = logging.getLogger(__name__)


async def _get_billing_impl(
    detail: str,
    start_date: str | None,
    end_date: str | None,
) -> str:
    """Fetch billing data from the Riven API."""
    client = get_client()

    if detail == "balance":
        try:
            data = await client.get("/billing/balance")
        except RivenAPIError as exc:
            return f"Failed to fetch billing balance: {exc.detail}"

        balance = data.get("balance", data.get("credits", "N/A"))
        currency = data.get("currency", "USD")
        plan = data.get("plan", data.get("subscription", "N/A"))
        usage_this_month = data.get("usage_this_month", data.get("current_usage", "N/A"))

        lines = [
            "# Billing Balance\n",
            f"- Current balance: ${balance} {currency}" if isinstance(balance, (int, float)) else f"- Current balance: {balance}",
            f"- Plan: {plan}",
        ]
        if isinstance(usage_this_month, (int, float)):
            lines.append(f"- Usage this month: ${usage_this_month:.2f}")
        else:
            lines.append(f"- Usage this month: {usage_this_month}")

        return "\n".join(lines)

    elif detail == "history":
        params: dict[str, Any] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        try:
            data = await client.get("/billing/history", params=params)
        except RivenAPIError as exc:
            return f"Failed to fetch billing history: {exc.detail}"

        invoices = data.get("invoices", data.get("data", []))
        if not invoices:
            return "No billing history found for the specified period."

        lines: list[str] = ["# Billing History\n"]
        total_spent = 0.0

        for inv in invoices:
            inv_id = inv.get("id", inv.get("invoice_id", "N/A"))
            date = inv.get("date", inv.get("created", "N/A"))
            amount = inv.get("amount", inv.get("total", 0))
            status = inv.get("status", "unknown")
            model_breakdown = inv.get("model_breakdown", {})

            if isinstance(amount, (int, float)):
                total_spent += amount
                amount_str = f"${amount:.2f}"
            else:
                amount_str = str(amount)

            lines.append(
                f"- **{inv_id}** ({date}): {amount_str} [{status}]"
            )
            if model_breakdown:
                for mdl, cost in model_breakdown.items():
                    lines.append(f"  - {mdl}: ${cost:.4f}" if isinstance(cost, (int, float)) else f"  - {mdl}: {cost}")

        lines.append(f"\n**Total: ${total_spent:.2f}**")
        return "\n".join(lines)

    else:  # subscription
        try:
            data = await client.get("/billing/subscription")
        except RivenAPIError as exc:
            return f"Failed to fetch subscription: {exc.detail}"

        plan = data.get("plan", data.get("name", "N/A"))
        status = data.get("status", "unknown")
        renewal = data.get("renewal_date", data.get("current_period_end", "N/A"))
        limits = data.get("limits", {})

        lines = [
            "# Subscription Details\n",
            f"- Plan: {plan}",
            f"- Status: {status}",
            f"- Renewal: {renewal}",
        ]
        if limits:
            lines.append("\n## Limits\n")
            for k, v in limits.items():
                lines.append(f"- {k.replace('_', ' ').title()}: {v}")

        return "\n".join(lines)


def register(server: MCPServer) -> None:
    """Register the get_billing tool on the MCP server."""

    @server.tool()
    @tool_handler("get_billing")
    async def get_billing(
        detail: str = "balance",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        """Query billing information from the Riven platform (Stripe integration).

        Args:
            detail: Type of billing data to retrieve:
                    - "balance": Current balance and monthly usage (default)
                    - "history": Payment/invoice history
                    - "subscription": Current subscription plan and limits
            start_date: Start date for history queries (ISO 8601).
            end_date: End date for history queries (ISO 8601).

        Returns:
            Formatted billing report with balance, invoices, or subscription details.
        """
        return await _get_billing_impl(
            detail=detail,
            start_date=start_date,
            end_date=end_date,
        )
