<div align="center">

# ProContext

**Accurate, live library documentation for AI coding agents.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP 2025-11-25](https://img.shields.io/badge/MCP-2025--11--25-green.svg)](https://modelcontextprotocol.io)
[![llms.txt](https://img.shields.io/badge/llms.txt-supported-blue)](https://llmstxt.org)

</div>

ProContext is an open-source [MCP](https://modelcontextprotocol.io) server that gives AI coding agents - Claude Code, Cursor, Windsurf - accurate, up-to-date documentation for the libraries they write code with. It prevents hallucinated APIs by serving real documentation on demand from a curated, pre-validated registry.

---

## Quick Start

**Recommended** - once published to PyPI:

```bash
uvx procontext
```

> Not yet on PyPI. Use the method below until then.

**In the meantime** - clone and run:

```bash
git clone https://github.com/procontexthq/procontext.git
cd procontext && uv sync
```

Add to your MCP client config:

```json
{
  "mcpServers": {
    "procontext": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/procontext", "procontext"]
    }
  }
}
```

---

## How It Works

ProContext exposes three MCP tools that work as a pipeline. The agent drives the navigation - no server-side search, no intent guessing.

**Step 1 - Resolve the library**

```
resolve_library({ "query": "langchain>=0.2" })

→ {
    "library_id": "langchain",
    "name": "LangChain",
    "docs_url": "https://docs.langchain.com",
    "matched_via": "package_name",
    "relevance": 1.0
  }
```

**Step 2 - Fetch the table of contents**

```
get_library_docs({ "library_id": "langchain" })

→ {
    "content": "# LangChain\n\n## Concepts\n- [Chat Models](https://...)\n- [Tools](https://...)\n...",
    "cached": false,
    "stale": false
  }
```

**Step 3 - Read a specific page**

```
read_page({ "url": "https://docs.langchain.com/docs/concepts/chat_models.md", "limit": 200 })

→ {
    "headings": "1: # Chat Models\n45: ## Streaming\n89: ## Tool Calling\n...",
    "total_lines": 312,
    "content": "# Chat Models\n\nChat models are..."
  }
```

The agent reads the TOC, identifies the pages it needs, and reads them directly - jumping to relevant sections via the heading map. ProContext fetches from known, pre-validated sources and caches the results for subsequent calls.

---

## The Problem

AI coding agents hallucinate API details because their training data ages. A library ships a breaking change; the agent's weights don't reflect it; the generated code doesn't work.

Existing approaches each have a ceiling:

| Approach               | Examples       | Accuracy | Limitation                                                                 |
| ---------------------- | -------------- | -------- | -------------------------------------------------------------------------- |
| **Server-side search** | Context7       | 65–75%   | Server must interpret vague user intent; requires expensive query model    |
| **Agent-side RAG**     | Custom setups  | 90%+     | Agent must discover and validate sources itself; brittle at scale          |
| **ProContext**         | _This project_ | **90%+** | Agent navigates pre-validated, always-fresh sources; no discovery overhead |

ProContext's approach: build a curated registry of known-good documentation sources at build time, then serve them on demand at runtime. The agent's LLM already knows what it's looking for - ProContext just gets it there reliably.

---

## Features

**Registry-first resolution**
Library lookups complete in under 10ms from an in-memory index built at startup. Fuzzy matching handles typos and pip-style specifiers (`langchain>=0.1`, `langchain[openai]`).

**llms.txt native**
Purpose-built for the [llms.txt standard](https://llmstxt.org) - the AI-optimized documentation format. Fetches tables of contents and individual pages on demand.

**Efficient cache with stale-while-revalidate**
First query: under 5 seconds (fetch + parse + cache). Repeat queries: under 100ms from SQLite. When cache expires, stale content is returned immediately while a background refresh runs - the agent never waits.

**SSRF protection**
The server only fetches from a domain allowlist derived from the registry at startup. Private IP ranges are blocked unconditionally, including on redirect hops.

**HTTP transport**
Implements MCP Streamable HTTP (spec 2025-11-25) for shared or remote deployments. `MCPSecurityMiddleware` enforces origin validation (DNS rebinding protection), optional bearer key authentication, and protocol version checks.

**Cross-platform**
Config, cache, and data paths resolve automatically on Windows, macOS, and Linux via `platformdirs` - no manual path configuration.

---

## Installation

**Requirements**: Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/procontexthq/procontext.git
cd procontext
uv sync
```

### stdio mode (default)

Your MCP client (Claude Code, Cursor, Windsurf) spawns and manages the server process automatically - you don't need to run anything manually. The command below is only needed if you want to test the server directly, for example to verify your setup:

```bash
uv run procontext
```

### HTTP mode

For shared or remote deployments. Runs a persistent HTTP server on `/mcp`.

Copy the example config, set `transport: http`, and run:

```bash
cp procontext.example.yaml procontext.yaml
```

```yaml
# procontext.yaml
server:
  transport: http
  host: "127.0.0.1"
  port: 8080
  auth_enabled: false # set true to require a bearer key
cache:
  ttl_hours: 24
```

```bash
uv run procontext
```

Alternatively, settings can be passed directly as environment variables using the `PROCONTEXT__` prefix:

```bash
PROCONTEXT__SERVER__TRANSPORT=http \
PROCONTEXT__SERVER__HOST=127.0.0.1 \
PROCONTEXT__SERVER__PORT=8080 \
uv run procontext
```

---

## Integrations

### Claude Code

Add to `.claude/mcp_config.json` (project-level) or `~/.claude/mcp_config.json` (global):

```json
{
  "mcpServers": {
    "procontext": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/procontext", "procontext"]
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "procontext": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/procontext", "procontext"]
    }
  }
}
```

### Codex / Cursor / Antigravity / Windsurf

Add to your MCP settings:

```json
{
  "mcpServers": {
    "procontext": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/procontext", "procontext"]
    }
  }
}
```

### HTTP mode (shared deployments)

Point your MCP client at the server URL:

```json
{
  "mcpServers": {
    "procontext": {
      "url": "http://your-server:8080/mcp"
    }
  }
}
```

---

## Platform Support

All filesystem paths resolve automatically - no manual configuration needed.

| Platform | Config & data directory                    |
| -------- | ------------------------------------------ |
| Linux    | `~/.local/share/procontext`                |
| macOS    | `~/Library/Application Support/procontext` |
| Windows  | `%LOCALAPPDATA%\procontext`                |

---

## Documentation

Design decisions, architecture, and API reference are in [`docs/specs/`](docs/specs/).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, development workflow, coding conventions, and how to submit a pull request.

---

## License

GPL-3.0 - see [LICENSE](LICENSE) for details.

The GPL ensures that ProContext and any derivatives remain free and open-source.

---

<div align="center">

**Built with ❤️ for AI coding agents**

[Specifications](docs/specs/) · [Issues](../../issues) · [Discussions](../../discussions) · [MCP](https://modelcontextprotocol.io) · [llms.txt](https://llmstxt.org)

</div>
