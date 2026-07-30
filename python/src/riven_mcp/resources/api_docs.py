"""Resource: API documentation (Markdown).

Exposes Riven's API documentation as a read-only MCP resource at
`riven://docs/api`.
"""

from __future__ import annotations

import logging

from mcp.server import MCPServer

from ..config import get_settings

logger = logging.getLogger(__name__)


_API_DOCS = """# Riven AI API Documentation

## Overview

Riven AI provides an OpenAI-compatible API for accessing 75+ AI models from
multiple providers through a single unified endpoint. The API supports
intelligent routing, transparent per-token billing, and on-prem model serving.

**Base URL:** `https://api.rivenai.io/v1`

**Authentication:** Bearer token (API key)

```bash
Authorization: Bearer riv_live_your_api_key_here
```

## Endpoints

### Chat Completions

```http
POST /chat/completions
```

OpenAI-compatible chat completions endpoint.

**Request body:**
```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 1024,
  "stream": false,
  "top_p": 1.0,
  "stop": null
}
```

**Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "model": "gpt-4o",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "Hello! How can I help?"},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 8,
    "total_tokens": 28
  }
}
```

### Models

```http
GET /models
```

Lists all available models with pricing and capability information.

### Usage

```http
GET /usage?start_date=2025-01-01&end_date=2025-01-31&group_by=model
```

Returns token usage and cost breakdowns.

### Billing

```http
GET /billing/balance
GET /billing/history?start_date=2025-01-01&end_date=2025-01-31
GET /billing/subscription
```

### Routing

```http
POST /route
```

Intelligent model routing with fallback.

**Request body:**
```json
{
  "messages": [{"role": "user", "content": "Summarize this article..."}],
  "routing": {
    "strategy": "balanced",
    "max_cost_per_request": 0.50,
    "max_latency_ms": 2000,
    "required_capabilities": ["function_calling"],
    "preferred_providers": ["anthropic", "openai"],
    "fallback": true
  }
}
```

### Pricing

```http
GET /pricing
GET /pricing/{model_id}
```

## Model Providers

| Provider | Example Models | Notes |
|---|---|---|
| OpenAI | gpt-4o, gpt-4o-mini, o1 | Full OpenAI model lineup |
| Anthropic | claude-3.5-sonnet, claude-3-opus | Claude family |
| Google | gemini-2.0-flash, gemini-1.5-pro | Gemini models |
| Cerebras | llama-4-scout-cerebras | Ultra-low latency inference |
| Fireworks | firellama-13b, mixtral-8x22b | Open-source models |
| On-Prem (GLM) | glm-5.2 | Self-hosted on A100 GPU |

## Error Handling

All errors return JSON with an `error` object:

```json
{
  "error": {
    "message": "Invalid model ID",
    "type": "invalid_request_error",
    "code": "model_not_found"
  }
}
```

**Common status codes:**
- `400` — Bad request (invalid parameters)
- `401` — Unauthorized (invalid API key)
- `402` — Payment required (insufficient credits)
- `429` — Rate limited
- `500` — Internal server error
- `503` — Model temporarily unavailable

## Rate Limits

Rate limits vary by plan. Standard plan: 100 requests/minute.
Headers `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset` are included in all responses.

## SDK Examples

### Python
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.rivenai.io/v1",
    api_key="riv_live_your_key"
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### cURL
```bash
curl https://api.rivenai.io/v1/chat/completions \\
  -H "Authorization: Bearer riv_live_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]}'
```

## Additional Resources

- **Dashboard:** https://dashboard.rivenai.io
- **API Keys:** https://dashboard.rivenai.io/api-keys
- **Status Page:** https://status.rivenai.io
- **GitHub:** https://github.com/rivenai
"""


async def _fetch_api_docs() -> str:
    """Return the API documentation as markdown."""
    # In production, this could fetch live docs from a CMS or docs site.
    # For now, return the embedded documentation.
    return _API_DOCS


def register(server: MCPServer) -> None:
    """Register the API docs resource on the MCP server."""

    @server.resource("riven://docs/api")
    async def api_documentation() -> str:
        """Riven AI API documentation in Markdown.

        Covers all endpoints (chat completions, models, usage, billing,
        routing, pricing), authentication, model providers, error handling,
        rate limits, and SDK examples for Python and cURL.
        """
        return await _fetch_api_docs()
