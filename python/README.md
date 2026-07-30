# Riven MCP Server

A production-ready [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that exposes [Riven AI](https://rivenai.io)'s platform capabilities as standardized tools, resources, and prompts for AI agents.

Riven AI provides an OpenAI-compatible API with 75+ models from OpenAI, Anthropic, Google, Cerebras, Fireworks, and on-prem GLM — with transparent per-token billing, intelligent model routing, and Stripe-integrated billing.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [MCP Client Setup](#mcp-client-setup)
- [Tools](#tools)
- [Resources](#resources)
- [Prompts](#prompts)
- [Security](#security)
- [Docker Deployment](#docker-deployment)
- [Development](#development)
- [Testing](#testing)

---

## Overview

The Riven MCP Server bridges AI agents (Claude Desktop, Cursor, custom agents) to Riven's multi-model platform. Instead of hardcoding API calls, agents discover and invoke tools through the MCP protocol — listing models, sending completions, checking billing, comparing costs, and routing requests through Riven's intelligent gateway.

```
┌──────────────┐      MCP (stdio/HTTP)      ┌──────────────────┐      HTTPS      ┌─────────────────┐
│  AI Agent    │ ◄─────────────────────────► │  Riven MCP Server│ ◄──────────────► │  Riven API      │
│  (Claude,    │   tools/list, tools/call    │  (this repo)      │   Bearer auth   │  api.rivenai.io │
│   Cursor)    │   resources/read            │                   │                  │                 │
└──────────────┘   prompts/get               └──────────────────┘                  └─────────────────┘
                                                   │
                                                   ├── Rate limiting (sliding window)
                                                   ├── Cost guardrails (per-request + daily)
                                                   ├── Audit logging (JSON, file + stderr)
                                                   └── Bearer token authentication
```

## Features

| Category | Details |
|---|---|
| **Transport** | stdio (local clients) + Streamable HTTP/SSE (remote deployment) |
| **Protocol** | MCP 2024-11-05 |
| **Authentication** | Bearer token (API key) |
| **Tools** | 9 tools: list_models, chat_completion, get_usage, compare_models, route_request, get_billing, submit_indexnow, check_model_health, get_model_pricing |
| **Resources** | 4 resources: model catalog, pricing sheet, API docs, service status |
| **Prompts** | 3 templates: model selection advisor, cost optimization analyzer, migration planner |
| **Security** | Rate limiting, cost guardrails, audit logging, API key redaction |
| **Deployment** | Docker, Docker Swarm, Python package |

## Architecture

### Technology Stack

- **Language:** Python 3.11+
- **MCP SDK:** `mcp` (official Python SDK, v1.x)
- **HTTP Client:** `httpx` (async, with retry via `tenacity`)
- **Config:** `pydantic-settings` (12-factor env-based config)
- **Logging:** `structlog`-style JSON logging (Loki/ELK compatible)
- **Packaging:** `hatchling` (PEP 621 compliant)

### Project Structure

```
mcp-server/
├── pyproject.toml              # Package definition, dependencies, tool config
├── Dockerfile                  # Multi-stage build (slim runtime image)
├── docker-compose.yml          # Swarm-ready deployment with secrets
├── .env.example                # Configuration template
├── .dockerignore
├── README.md                   # This file
│
├── src/riven_mcp/
│   ├── __init__.py
│   ├── server.py               # Main MCP server — entry point, lifecycle
│   ├── config.py               # Settings (pydantic-settings, env-based)
│   ├── client.py               # Riven API async client (httpx + retry)
│   ├── security.py             # Rate limiter, cost guardrails, audit logger
│   │
│   ├── tools/                  # 9 MCP tool definitions
│   │   ├── _helpers.py         # Shared decorator: rate limit + audit + error handling
│   │   ├── list_models.py
│   │   ├── chat_completion.py
│   │   ├── get_usage.py
│   │   ├── compare_models.py
│   │   ├── route_request.py
│   │   ├── get_billing.py
│   │   ├── submit_indexnow.py
│   │   ├── check_model_health.py
│   │   └── get_model_pricing.py
│   │
│   ├── resources/              # 4 MCP resource definitions
│   │   ├── model_catalog.py    # riven://models/catalog (JSON)
│   │   ├── pricing_sheet.py    # riven://pricing/sheet (JSON)
│   │   ├── api_docs.py         # riven://docs/api (Markdown)
│   │   └── service_status.py   # riven://status/service (JSON)
│   │
│   └── prompts/                # 3 MCP prompt templates
│       ├── model_selection.py
│       ├── cost_optimization.py
│       └── migration_planner.py
│
└── tests/
    └── test_tools.py           # Unit tests for tools and security
```

## Quick Start

### Prerequisites

- Python 3.11+ (or Docker)
- A Riven AI API key — generate at [dashboard.rivenai.io/api-keys](https://dashboard.rivenai.io/api-keys)

### Option 1: Local Python

```bash
# Clone the repository
git clone https://github.com/rivenai/mcp-server.git
cd mcp-server

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install the package
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env and set RIVEN_API_KEY=riv_live_your_key_here

# Run with stdio transport (for Claude Desktop, Cursor, etc.)
python -m riven_mcp.server

# Or run with HTTP transport (for remote deployment)
MCP_TRANSPORT=http MCP_PORT=8080 python -m riven_mcp.server
```

### Option 2: Docker

```bash
# Build the image
docker build -t rivenai/mcp-server:1.0.0 .

# Run with stdio (pipe to/from an MCP client)
docker run --rm -i \
  -e RIVEN_API_KEY=riv_live_your_key \
  rivenai/mcp-server:1.0.0

# Run with HTTP transport
docker run -d --name riven-mcp \
  -p 8080:8080 \
  -e MCP_TRANSPORT=http \
  -e MCP_PORT=8080 \
  -e RIVEN_API_KEY=riv_live_your_key \
  rivenai/mcp-server:1.0.0
```

### Option 3: Docker Swarm

```bash
# Create secrets (one-time)
echo "riv_live_your_key" | docker secret create riven_api_key -
echo "your_indexnow_key" | docker secret create riven_indexnow_api_key -

# Create network (if not exists)
docker network create -d overlay riven-swarm-net

# Deploy
docker stack deploy -c docker-compose.yml riven-mcp

# Check status
docker stack services riven-mcp
docker service logs riven-mcp_riven-mcp --tail 20
```

## Configuration

All configuration is via environment variables (12-factor app). See [`.env.example`](.env.example) for the full list.

| Variable | Default | Description |
|---|---|---|
| `RIVEN_API_BASE_URL` | `https://api.rivenai.io/v1` | Riven API base URL |
| `RIVEN_API_KEY` | _(required)_ | Riven API key for backend calls |
| `MCP_TRANSPORT` | `stdio` | Transport: `stdio` or `http` |
| `MCP_HOST` | `0.0.0.0` | HTTP listen host |
| `MCP_PORT` | `8080` | HTTP listen port |
| `MCP_PROTOCOL_VERSION` | `2024-11-05` | MCP protocol version |
| `MCP_AUTH_KEYS` | _(empty)_ | Comma-separated allowed client API keys |
| `RATE_LIMIT_MAX_REQUESTS` | `100` | Max requests per window per client |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window (seconds) |
| `COST_GUARDRAIL_PER_REQUEST_USD` | `5.00` | Max estimated cost per request |
| `COST_GUARDRAIL_DAILY_USD` | `100.00` | Max daily spend per API key |
| `INDEXNOW_API_KEY` | _(empty)_ | Bing IndexNow API key |
| `INDEXNOW_HOST` | `rivenai.io` | Comma-separated IndexNow hosts |
| `ONPREM_HEALTH_URL` | `http://onprem-gpu.internal:8000/health` | On-prem GLM health endpoint |
| `LOG_LEVEL` | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_JSON` | `true` | Enable structured JSON logging |
| `AUDIT_LOG_PATH` | _(empty)_ | Audit log file path |

### Docker Secrets

For Docker Swarm, API keys can be loaded from Docker secrets by appending `_FILE` to the variable name:

```yaml
environment:
  RIVEN_API_KEY_FILE: /run/secrets/riven_api_key
  INDEXNOW_API_KEY_FILE: /run/secrets/indexnow_api_key
```

The server reads the secret file at startup and resolves the value.

## MCP Client Setup

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "riven": {
      "command": "python",
      "args": ["-m", "riven_mcp.server"],
      "env": {
        "RIVEN_API_KEY": "riv_live_your_key_here"
      }
    }
  }
}
```

Or with Docker:

```json
{
  "mcpServers": {
    "riven": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "-e", "RIVEN_API_KEY", "rivenai/mcp-server:1.0.0"],
      "env": {
        "RIVEN_API_KEY": "riv_live_your_key_here"
      }
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "riven": {
      "url": "http://localhost:8080",
      "transport": "http"
    }
  }
}
```

### Custom Agent (Python)

```python
from mcp import Client
from riven_mcp.server import create_server

async def main():
    server = create_server()
    async with Client(server) as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[t.name for t in tools]}")

        # Call a tool
        result = await client.call_tool("list_models", {})
        print(result)

import asyncio
asyncio.run(main())
```

## Tools

The server exposes 9 tools. Each tool has a JSON Schema for input validation and returns formatted text (Markdown) with structured data.

### 1. `list_models`

List all available AI models with pricing information.

```python
# No parameters — returns full catalog
result = await client.call_tool("list_models", {})
```

**Returns:** Formatted catalog of 75+ models with provider, context window, and per-1K-token pricing.

### 2. `chat_completion`

Send a chat completion request to a Riven-hosted model. OpenAI-compatible.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `model` | string | Yes | — | Model ID (e.g. `gpt-4o`, `claude-3.5-sonnet`, `glm-5.2`) |
| `messages` | array | Yes | — | Message objects with `role` and `content` |
| `temperature` | float | No | model default | Sampling temperature (0-2) |
| `max_tokens` | int | No | 1024 | Maximum tokens to generate |
| `stream` | bool | No | false | Stream the response |
| `top_p` | float | No | model default | Nucleus sampling (0-1) |
| `stop` | string/array | No | null | Stop sequence(s) |

**Cost guardrail:** Requests with estimated cost exceeding `COST_GUARDRAIL_PER_REQUEST_USD` are rejected before execution.

### 3. `get_usage`

Query token usage and cost data.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `start_date` | string | No | 30 days ago | ISO 8601 start date |
| `end_date` | string | No | today | ISO 8601 end date |
| `model` | string | No | all | Filter to a specific model |
| `group_by` | string | No | `model` | Grouping: `model`, `day`, `model_day` |

### 4. `compare_models`

Compare models by price, latency, context window, and capabilities.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `models` | array | Yes | — | Model IDs to compare |
| `criteria` | array | No | all four | Dimensions: `price`, `latency`, `capability`, `context` |

**Returns:** Markdown comparison table with recommendations (cheapest, largest context).

### 5. `route_request`

Use Riven's intelligent model routing to auto-select the best model.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `messages` | array | Yes | — | Chat messages |
| `strategy` | string | No | `balanced` | `cheapest`, `fastest`, `balanced`, `highest_quality` |
| `max_cost` | float | No | unlimited | Max cost per request (USD) |
| `max_latency_ms` | int | No | unlimited | Max latency (ms) |
| `required_capabilities` | array | No | none | Required capabilities |
| `preferred_providers` | array | No | none | Provider preference order |
| `fallback` | bool | No | true | Enable automatic fallback |

### 6. `get_billing`

Query billing information (Stripe integration).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `detail` | string | No | `balance` | `balance`, `history`, `subscription` |
| `start_date` | string | No | — | History start date |
| `end_date` | string | No | — | History end date |

### 7. `submit_indexnow`

Submit URLs to Bing IndexNow for immediate indexing.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `urls` | array | Yes | Full URLs to submit |
| `host` | string | No | Override host (defaults to `INDEXNOW_HOST`) |

### 8. `check_model_health`

Check health status of on-prem and cloud models.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `model` | string | No | all | Filter to a specific model |
| `check_type` | string | No | `all` | `onprem`, `cloud`, `all` |

**On-prem check:** Queries the internal GPU health endpoint, reporting GPU utilization, memory, model load status, and queue depth.

### 9. `get_model_pricing`

Get detailed pricing for a specific model.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `model` | string | Yes | Model ID |

**Returns:** Per-token, per-1K, and per-1M pricing for input/output, volume discounts, cached input rates, and example cost calculations.

## Resources

Resources are read-only data accessible via MCP `resources/read`.

| URI | MIME Type | Description |
|---|---|---|
| `riven://models/catalog` | application/json | Full model catalog (75+ models, providers, pricing, capabilities) |
| `riven://pricing/sheet` | application/json | Complete pricing sheet with summary stats (cheapest, average, most expensive) |
| `riven://docs/api` | text/markdown | API documentation covering all endpoints, auth, error handling, and SDK examples |
| `riven://status/service` | application/json | Live service status (API gateway, on-prem GPU, billing, IndexNow) |

## Prompts

Pre-configured prompt templates accessible via MCP `prompts/get`.

### Model Selection Advisor

Interactive advisor that lists models, compares candidates, and recommends the optimal model based on task, budget, latency, and capability requirements.

**Arguments:** `task_description`, `max_budget_per_request`, `max_latency_ms`, `required_capabilities`, `context_length_needed`

### Cost Optimization Analyzer

Analyzes usage patterns and recommends cost-saving strategies (model right-sizing, caching, routing optimization, token optimization, provider migration).

**Arguments:** `timeframe` (days), `target_reduction_percent`

### Migration Planner (OpenAI → Riven)

Plans a migration from OpenAI to Riven, including model mapping tables, code changes, cost comparisons, and a migration checklist.

**Arguments:** `current_models`, `monthly_volume`, `priority` (cost/latency/quality/all)

## Security

### Rate Limiting

Sliding-window rate limiter per client identifier. Configurable via `RATE_LIMIT_MAX_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS`. Default: 100 requests per 60 seconds per client.

For multi-process deployments, replace the in-memory store with Redis:

```python
# In security.py, replace RateLimiter with a Redis-backed implementation
# using INCR + EXPIRE commands for atomic sliding-window counting.
```

### API Key Management

- **Server-side:** The `RIVEN_API_KEY` environment variable (or Docker secret) is used for all Riven API calls. Never logged or exposed in tool responses.
- **Client-side:** `MCP_AUTH_KEYS` validates Bearer tokens from MCP clients. If empty, no client auth is enforced (suitable when behind an auth proxy).
- **Redaction:** The audit logger automatically redacts values in fields named `api_key`, `key`, `token`, `secret`, `authorization`.

### Audit Logging

All tool invocations are logged with:
- Timestamp (UTC ISO 8601)
- Client identifier
- Tool name
- Sanitized arguments (secrets redacted, long inputs truncated)
- Result summary (truncated to 500 chars)
- Error details (if any)
- Duration in milliseconds

Logs are emitted to stderr (for Docker logging drivers) and optionally to a file (`AUDIT_LOG_PATH`). JSON format is used for structured log aggregation (Loki, ELK, Datadog).

### Cost Guardrails

Two-tier cost protection:

1. **Per-request limit** (`COST_GUARDRAIL_PER_REQUEST_USD`): Estimated cost is calculated before sending each `chat_completion` request. Requests exceeding the limit are rejected with a detailed message.

2. **Daily spend limit** (`COST_GUARDRAIL_DAILY_USD`): Cumulative spend is tracked per client. When the daily limit would be exceeded, the request is rejected. Counters reset at UTC midnight.

## Docker Deployment

### Docker Swarm Integration

The `docker-compose.yml` is configured for Docker Swarm with:

- **2 replicas** with rolling updates (start-first, 10s delay)
- **Resource limits:** 512MB memory, 1 CPU per container
- **Placement constraints:** Runs on worker nodes (not managers)
- **Secrets:** API keys loaded from Docker secrets (never in images)
- **NFS volume:** Audit logs persisted to NFS share
- **Health checks:** Automatic container restart on failure
- **Log rotation:** 10MB max, 3 files

### Deploy

```bash
# Create secrets
echo "riv_live_your_key" | docker secret create riven_api_key -
echo "your_indexnow_key" | docker secret create riven_indexnow_api_key -

# Create overlay network
docker network create -d overlay riven-swarm-net

# Deploy the stack
docker stack deploy -c docker-compose.yml riven-mcp

# Verify
docker stack services riven-mcp
curl http://localhost:8080/  # health check

# Scale up
docker service scale riven-mcp_riven-mcp=4

# Update (rolling)
docker service update --image rivenai/mcp-server:1.1.0 riven-mcp_riven-mcp

# Remove
docker stack rm riven-mcp
```

### Behind a Reverse Proxy (Traefik / Nginx)

For production HTTP deployments, place behind a reverse proxy:

```yaml
# docker-compose.yml (add labels for Traefik)
deploy:
  labels:
    - traefik.enable=true
    - traefik.http.routers.riven-mcp.rule=Host(`mcp.rivenai.io`)
    - traefik.http.routers.riven-mcp.tls=true
    - traefik.http.routers.riven-mcp.tls.certresolver=letsencrypt
    - traefik.http.services.riven-mcp.loadbalancer.server.port=8080
```

## Development

### Setup

```bash
git clone https://github.com/rivenai/mcp-server.git
cd mcp-server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env
```

### Code Quality

```bash
# Lint
ruff check src/ tests/

# Type check
mypy src/

# Format
ruff format src/ tests/
```

### MCP Inspector

Test the server interactively with the MCP Inspector:

```bash
# Install MCP CLI (if not installed)
pip install mcp[cli]

# Launch inspector with stdio transport
mcp dev src/riven_mcp/server.py

# Or with the module
mcp dev -m riven_mcp.server
```

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=riven_mcp --cov-report=html

# Run specific test class
pytest tests/test_tools.py::TestListModels

# With verbose output
pytest -v
```

### Test Coverage

The test suite covers:

- **Tool implementations:** list_models, get_model_pricing, compare_models, submit_indexnow
- **Security:** rate limiter (sliding window, separate clients), cost guardrails (per-request, daily), audit log secret redaction
- **Error handling:** API errors, missing configuration, invalid inputs

Tests use `unittest.mock` to mock the Riven API client — no live API calls are made during testing.

## License

MIT — see [LICENSE](LICENSE).

## Links

- **Riven AI:** [rivenai.io](https://rivenai.io)
- **API Docs:** [docs.rivenai.io](https://docs.rivenai.io)
- **Dashboard:** [dashboard.rivenai.io](https://dashboard.rivenai.io)
- **Status:** [status.rivenai.io](https://status.rivenai.io)
- **GitHub:** [github.com/rivenai](https://github.com/rivenai)
- **MCP Specification:** [modelcontextprotocol.io](https://modelcontextprotocol.io)
