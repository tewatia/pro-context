<div align="left">

# ProContext

**Accurate, live library documentation for AI coding agents.**

[![Website][website-badge]][website-url]
[![License: MIT][license-badge]][license-url]
[![Python 3.12+][python-badge]][python-url]
[![Protocol][protocol-badge]][protocol-url]
[![Specification][spec-badge]][spec-url]

</div>

ProContext is an open-source [MCP](https://modelcontextprotocol.io) server that gives AI coding agents - Claude Code, Cursor, Codex - accurate, up-to-date documentation for the libraries they write code with. It prevents hallucinated APIs by serving real documentation on demand from a curated, pre-validated registry.

**[procontext.dev](https://procontext.dev)**

---

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [The Problem](#the-problem)
- [Features](#features)
- [Installation](#installation)
- [Integrations](#integrations)
- [Platform Support](#platform-support)
- [Registry](#registry)
- [Contributing](#contributing)
- [License](#license)

[website-badge]: https://img.shields.io/badge/website-procontext.dev-blue.svg
[website-url]: https://procontext.dev
[license-badge]: https://img.shields.io/badge/License-MIT-blue.svg
[license-url]: https://opensource.org/licenses/MIT
[python-badge]: https://img.shields.io/badge/python-3.12%2B-blue.svg
[python-url]: https://www.python.org/downloads/
[protocol-badge]: https://img.shields.io/badge/protocol-modelcontextprotocol.io-blue.svg
[protocol-url]: https://modelcontextprotocol.io
[spec-badge]: https://img.shields.io/badge/spec-spec.modelcontextprotocol.io-blue.svg
[spec-url]: https://modelcontextprotocol.io/specification/latest

---

## Quick Start

> We are not yet on PyPI. Use the installer scripts below until then.

Install ProContext:

```bash
curl -fsSL https://raw.githubusercontent.com/procontexthq/procontext/main/install.sh | bash
```

```powershell
powershell -c "irm https://raw.githubusercontent.com/procontexthq/procontext/main/install.ps1 | iex"
```

Add to your MCP client config:

```json
{
  "mcpServers": {
    "procontext": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/procontext-source", "procontext"]
    }
  }
}
```

Use the managed checkout path printed by the installer. If you prefer a manual checkout flow, see [Installation](#installation).

---

## How It Works

ProContext exposes four MCP tools. The agent drives the navigation — no server-side search, no intent guessing.

**Step 1 — Resolve the library**

```
resolve_library({ "query": "langchain>=0.2" })

→ {
    "library_id": "langchain",
    "name": "LangChain",
    "index_url": "https://python.langchain.com/llms.txt",
    "matched_via": "package_name",
    "relevance": 1.0
  }
```

**Step 2 — Read the documentation index (or any page)**

```
read_page({ "url": "https://python.langchain.com/llms.txt" })

→ {
    "outline": "1:# LangChain\n3:## Concepts\n15:## How-to Guides\n...",
    "total_lines": 45,
    "content": "# LangChain\n\n## Concepts\n- [Chat Models](https://...)\n..."
  }
```

**Step 3 — Browse the full page (or index) outline**

```
read_outline({ "url": "https://python.langchain.com/llms.txt" })

→ {
    "outline": "1:# LangChain\n3:## Concepts\n15:## How-to Guides\n...",
    "total_entries": 18,
    "has_more": false
  }
```

**Step 4 — Search within a page**

```
search_page({ "url": "https://python.langchain.com/llms.txt", "query": "streaming" })

→ {
    "matches": "7:- [Streaming](https://...): Stream model outputs...\n22:- [How to stream responses](https://...): ...",
    "has_more": false
  }
```

The agent resolves a library, reads the index or pages directly, browses full outlines when needed, and searches within pages to jump to the right section. ProContext fetches from known, pre-validated sources and caches the results for subsequent calls.

---

## The Problem

AI coding agents hallucinate API details because their training data ages. A library ships a breaking change; the agent's weights don't reflect it; the generated code doesn't work.

There are two common failure modes:

- Server-side search requires the server to guess what the agent actually means, which gets expensive and brittle when the query is vague.
- Agent-side RAG can work well, but every client has to rediscover, validate, and maintain documentation sources on its own.

ProContext takes a different approach: build a curated registry of known-good documentation sources ahead of time, then serve those sources on demand at runtime. The agent's LLM already knows what it's looking for; ProContext gets it there reliably.

---

## Features

**Registry-first resolution**
Library lookups complete in under 10ms from an in-memory index built at startup. Fuzzy matching handles typos and pip-style specifiers (`langchain>=0.1`, `langchain[openai]`).

**llms.txt native**
Purpose-built for the [llms.txt standard](https://llmstxt.org) - the AI-optimized documentation format. Fetches tables of contents and individual pages on demand.

**Efficient cache with stale fallback**
First query: under 5 seconds (fetch + parse + cache). Repeat queries: under 100ms from SQLite. When cache expires, a synchronous re-fetch updates the content transparently. If the source is unreachable, stale content is served as fallback - the agent always gets a response.

**SSRF protection**
The server only fetches from a domain allowlist derived from the registry at startup. Private IP ranges are blocked unconditionally, including on redirect hops.

**HTTP transport**
Implements MCP Streamable HTTP (spec 2025-11-25) for shared or remote deployments. `MCPSecurityMiddleware` enforces origin validation (DNS rebinding protection), optional bearer key authentication, and protocol version checks.

**Cross-platform**
Config, cache, and data paths resolve automatically on Windows, macOS, and Linux via `platformdirs` - no manual path configuration.

---

## Installation

The supported installer entrypoints are the repository-root scripts [install.sh](install.sh) and [install.ps1](install.ps1).

Quick install:

```bash
curl -fsSL https://raw.githubusercontent.com/procontexthq/procontext/main/install.sh | bash
```

```powershell
powershell -c "irm https://raw.githubusercontent.com/procontexthq/procontext/main/install.ps1 | iex"
```

The installers clone or refresh a managed checkout from GitHub, ensure `git` and `uv` are available, sync a runtime-only environment with `uv sync --no-dev`, and run the one-time `procontext setup` step unless you skip it.

Manual install is still available:

```bash
git clone https://github.com/procontexthq/procontext.git
cd procontext
uv sync --no-dev
uv run --project . procontext setup
```

Full install and troubleshooting guide: [docs/cli/installation.md](docs/cli/installation.md)

> **First-time setup**: `procontext setup` downloads and persists the library registry to your platform data directory. The server cannot start without it. If you skip this step, the server will attempt a one-time auto-setup on first run - if the network is unavailable at that point, it will exit with an actionable error.

### stdio mode (default)

Your MCP client (Claude Code, Cursor, Windsurf) spawns and manages the server process automatically - you don't need to run anything manually. The command below is only needed if you want to test the server directly, for example to verify your setup:

```bash
uv run --project /path/to/procontext procontext
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
uv run --project /path/to/procontext procontext
```

Alternatively, settings can be passed directly as environment variables using the `PROCONTEXT__` prefix:

```bash
PROCONTEXT__SERVER__TRANSPORT=http \
PROCONTEXT__SERVER__HOST=127.0.0.1 \
PROCONTEXT__SERVER__PORT=8080 \
uv run --project /path/to/procontext procontext
```

---

## Integrations

### stdio (Claude Code, Claude Desktop, Cursor, Windsurf, and others)

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

For Claude Code, you can also add it from the CLI:

```bash
claude mcp add procontext -- uv run --project /path/to/procontext procontext
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

For Claude Code:

```bash
claude mcp add --transport http procontext http://your-server:8080/mcp
```

---

## Platform Support

All filesystem paths (config, cache, data) resolve automatically via `platformdirs` - no manual configuration needed on any platform.

---

## Documentation

Design decisions, architecture, and API reference are in [`docs/specs/`](docs/specs/).

---

## Registry

The library registry is maintained in a separate repository: **[procontexthq/procontexthq.github.io](https://github.com/procontexthq/procontexthq.github.io)**

If you want to add a library or update an existing entry, open a PR there - not here. Registry PRs opened in this repository will be closed without review.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, development workflow, coding conventions, and how to submit a pull request.

---

## License

MIT - see [LICENSE](LICENSE) for details. Free to use for individuals, teams, and organizations.

A managed hosted version and enterprise self-deployable options are coming. If you're interested in early access, visit [procontext.dev](https://procontext.dev).

---

<div align="left">

**Built with ❤️ for AI coding agents**

[procontext.dev](https://procontext.dev) · [Specifications](docs/specs/) · [Issues](../../issues) · [Discussions](../../discussions) · [MCP](https://modelcontextprotocol.io) · [llms.txt](https://llmstxt.org)

</div>
