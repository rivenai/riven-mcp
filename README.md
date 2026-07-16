# riven-mcp

Official [Model Context Protocol](https://modelcontextprotocol.io) (MCP)
server for [Riven](https://docs.rivenai.io). It exposes Riven's chat,
research, council, and usage capabilities as MCP tools over stdio, so any
MCP-compatible client — Claude Desktop, Cursor, or your own agent — can call
Riven directly.

## Tools

| Tool | Description |
|---|---|
| `riven_chat` | Send a single prompt to a Riven chat model and return the completion text. |
| `riven_research` | Create a Computer research task, run it, poll until done, and return a summary of the thread. |
| `riven_council` | Create a Computer council task (multiple models answer the same prompt) and return the verdict and transcript. |
| `riven_usage` | Return current usage statistics for the authenticated account. |

## Install

```bash
npm install -g @rivenai/riven-mcp
```

Or run it directly without a global install using `npx` (see configuration
examples below).

## Configuration

The server reads its configuration from environment variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `RIVEN_API_KEY` | Yes | — | Your Riven API key (starts with `rvn_`). |
| `RIVEN_API_BASE` | No | `https://api.rivenai.io/v1` | Override the chat completions API base URL. |
| `RIVEN_COMPUTER_BASE` | No | `https://computer.rivenai.io` | Override the Computer (agentic tasks) API base URL. |

## Usage with Claude Desktop

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "riven": {
      "command": "npx",
      "args": ["-y", "@rivenai/riven-mcp"],
      "env": {
        "RIVEN_API_KEY": "rvn_your_key_here"
      }
    }
  }
}
```

## Usage with Cursor

Add to your Cursor MCP config (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "riven": {
      "command": "npx",
      "args": ["-y", "@rivenai/riven-mcp"],
      "env": {
        "RIVEN_API_KEY": "rvn_your_key_here"
      }
    }
  }
}
```

## Usage with any MCP client

Any client that can spawn a stdio MCP server works the same way — set the
command to `npx -y @rivenai/riven-mcp` (or the installed binary `riven-mcp`)
and provide `RIVEN_API_KEY` in the child process environment:

```json
{
  "mcpServers": {
    "riven": {
      "command": "riven-mcp",
      "env": {
        "RIVEN_API_KEY": "rvn_your_key_here"
      }
    }
  }
}
```

## Building from source

```bash
git clone https://github.com/rivenai/riven-mcp
cd riven-mcp
npm install
npm run build
RIVEN_API_KEY=rvn_your_key_here node dist/index.js
```

## Notes on long-running tools

`riven_research` and `riven_council` create a Computer task, start it, and
poll its thread until the task reaches a terminal state or a timeout elapses
(default 120 seconds, configurable per call via `timeout_seconds`). If the
timeout is reached first, the tool returns the current transcript along with
the task's in-progress status rather than failing, since the underlying task
keeps running server-side.

## License

MIT © 2026 RivenAI. See [LICENSE](./LICENSE).

Full API reference: [docs.rivenai.io](https://docs.rivenai.io)
