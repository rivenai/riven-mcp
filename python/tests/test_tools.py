"""Tests for Riven MCP Server tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("riven_mcp.config.get_settings") as mock:
        settings = MagicMock()
        settings.riven_api_base_url = "https://api.rivenai.io/v1"
        settings.riven_api_key = "test_key"
        settings.mcp_transport = "stdio"
        settings.mcp_host = "0.0.0.0"
        settings.mcp_port = 8080
        settings.rate_limit_max_requests = 100
        settings.rate_limit_window_seconds = 60
        settings.cost_guardrail_per_request_usd = 5.0
        settings.cost_guardrail_daily_usd = 100.0
        settings.indexnow_api_key = "test-key"
        settings.indexnow_hosts = ["rivenai.io"]
        settings.onprem_health_url = "http://localhost:8000/health"
        settings.log_level = "DEBUG"
        settings.log_json = False
        settings.audit_log_path = ""
        settings.auth_keys = []
        settings.indexnow_host = "rivenai.io"
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_client():
    """Mock Riven API client."""
    with patch("riven_mcp.tools.list_models.get_client") as mock:
        client = AsyncMock()
        client.get = AsyncMock()
        mock.return_value = client
        yield client


class TestListModels:
    """Tests for the list_models tool."""

    @pytest.mark.asyncio
    async def test_list_models_success(self, mock_settings, mock_client):
        from riven_mcp.tools.list_models import _list_models_impl

        mock_client.get.return_value = {
            "data": [
                {
                    "id": "gpt-4o",
                    "name": "GPT-4o",
                    "owned_by": "openai",
                    "context_length": 128000,
                    "pricing": {"input": 0.000005, "output": 0.000015},
                },
                {
                    "id": "glm-5.2",
                    "name": "GLM-5.2",
                    "owned_by": "onprem",
                    "context_length": 32768,
                    "pricing": {"input": 0.000001, "output": 0.000002},
                },
            ]
        }

        result = await _list_models_impl()

        assert "gpt-4o" in result
        assert "glm-5.2" in result
        assert "2 total" in result
        assert "openai" in result
        assert "onprem" in result

    @pytest.mark.asyncio
    async def test_list_models_api_error(self, mock_settings, mock_client):
        from riven_mcp.client import RivenAPIError
        from riven_mcp.tools.list_models import _list_models_impl

        mock_client.get.side_effect = RivenAPIError(500, "Internal error")

        result = await _list_models_impl()
        assert "Failed to fetch models" in result


class TestGetModelPricing:
    """Tests for the get_model_pricing tool."""

    @pytest.mark.asyncio
    async def test_get_pricing_success(self, mock_settings):
        with patch("riven_mcp.tools.get_model_pricing.get_client") as mock:
            client = AsyncMock()
            client.get = AsyncMock(return_value={
                "id": "gpt-4o",
                "name": "GPT-4o",
                "owned_by": "openai",
                "context_length": 128000,
                "pricing": {"input": 0.000005, "output": 0.000015},
            })
            mock.return_value = client

            from riven_mcp.tools.get_model_pricing import _get_model_pricing_impl

            result = await _get_model_pricing_impl("gpt-4o")

            assert "gpt-4o" in result
            assert "Per-Token Pricing" in result
            assert "Per-1K Tokens" in result
            assert "Per-1M Tokens" in result
            assert "Example Costs" in result


class TestCompareModels:
    """Tests for the compare_models tool."""

    @pytest.mark.asyncio
    async def test_compare_models_success(self, mock_settings):
        with patch("riven_mcp.tools.compare_models.get_client") as mock:
            client = AsyncMock()
            client.get = AsyncMock(return_value={
                "data": [
                    {
                        "id": "gpt-4o",
                        "name": "GPT-4o",
                        "owned_by": "openai",
                        "context_length": 128000,
                        "pricing": {"input": 0.000005, "output": 0.000015},
                        "latency_ms": 800,
                        "capabilities": ["vision", "function_calling"],
                    },
                    {
                        "id": "glm-5.2",
                        "name": "GLM-5.2",
                        "owned_by": "onprem",
                        "context_length": 32768,
                        "pricing": {"input": 0.000001, "output": 0.000002},
                        "latency_ms": 200,
                        "capabilities": ["function_calling"],
                    },
                ]
            })
            mock.return_value = client

            from riven_mcp.tools.compare_models import _compare_models_impl

            result = await _compare_models_impl(
                models=["gpt-4o", "glm-5.2"],
                criteria=["price", "latency", "capability", "context"],
            )

            assert "gpt-4o" in result
            assert "glm-5.2" in result
            assert "Cheapest" in result
            assert "Largest context" in result

    @pytest.mark.asyncio
    async def test_compare_models_not_found(self, mock_settings):
        with patch("riven_mcp.tools.compare_models.get_client") as mock:
            client = AsyncMock()
            client.get = AsyncMock(return_value={"data": [{"id": "gpt-4o"}]})
            mock.return_value = client

            from riven_mcp.tools.compare_models import _compare_models_impl

            result = await _compare_models_impl(
                models=["nonexistent-model"],
                criteria=["price"],
            )

            assert "not found" in result.lower()


class TestSecurity:
    """Tests for security components."""

    def test_rate_limiter_allows_under_limit(self):
        from riven_mcp.security import RateLimiter

        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for i in range(5):
            assert limiter.check("client-1") is True
        assert limiter.check("client-1") is False

    def test_rate_limiter_separate_clients(self):
        from riven_mcp.security import RateLimiter

        limiter = RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.check("client-a") is True
        assert limiter.check("client-a") is True
        assert limiter.check("client-a") is False
        assert limiter.check("client-b") is True

    def test_cost_guardrail_per_request(self):
        from riven_mcp.security import CostGuardrail

        guardrail = CostGuardrail(per_request_limit=5.0, daily_limit=100.0)
        allowed, _ = guardrail.check_request("client-1", 3.0)
        assert allowed is True

        allowed, reason = guardrail.check_request("client-1", 10.0)
        assert allowed is False
        assert "per-request" in reason.lower()

    def test_cost_guardrail_daily_limit(self):
        from riven_mcp.security import CostGuardrail

        guardrail = CostGuardrail(per_request_limit=50.0, daily_limit=10.0)
        guardrail.record_spend("client-1", 8.0)

        allowed, reason = guardrail.check_request("client-1", 5.0)
        assert allowed is False
        assert "daily" in reason.lower()

    def test_audit_logger_sanitizes_secrets(self):
        from riven_mcp.security import _sanitize_args

        sanitized = _sanitize_args({
            "api_key": "secret123",
            "messages": [{"role": "user", "content": "hi"}],
            "model": "gpt-4o",
        })

        assert sanitized["api_key"] == "[REDACTED]"
        assert "1 messages" in sanitized["messages"]
        assert sanitized["model"] == "gpt-4o"


class TestSubmitIndexnow:
    """Tests for the submit_indexnow tool."""

    @pytest.mark.asyncio
    async def test_no_api_key(self, mock_settings):
        mock_settings.indexnow_api_key = ""
        from riven_mcp.tools.submit_indexnow import _submit_indexnow_impl

        result = await _submit_indexnow_impl(
            urls=["https://rivenai.io/blog/post"],
            host=None,
        )
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_invalid_host(self, mock_settings):
        from riven_mcp.tools.submit_indexnow import _submit_indexnow_impl

        result = await _submit_indexnow_impl(
            urls=["https://example.com/page"],
            host="rivenai.io",
        )
        assert "must belong to host" in result.lower()
