# ProContext

**MCP documentation server that provides AI coding agents with accurate, up-to-date documentation to prevent API hallucination.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.0-green.svg)](https://modelcontextprotocol.io)

ProContext is an open-source [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that will deliver accurate, fresh documentation to AI coding agents like Claude Code, Cursor, and Windsurf. It prevents hallucinated APIs by serving real documentation from Python libraries, MCP servers, GitHub projects, and any source that publishes [llms.txt](https://llmstxt.org) files.

> ⚠️ **Project Status**: **Phase 2 complete** (registry, resolution, fetcher & cache implemented). Phase 3 (page reading & parser) is next. Not yet usable — see [Development Status](#development-status) below.

---

## The Problem

AI coding agents often hallucinate outdated or incorrect API details because:

- They're trained on old data
- Documentation changes frequently
- They lack access to current library docs

**ProContext solves this** by giving agents on-demand access to fresh, curated documentation.

---

## How ProContext Differs

Existing documentation tools fall into two categories, each with limitations:

| Approach               | Examples               | Accuracy | Limitation                                                                            |
| ---------------------- | ---------------------- | -------- | ------------------------------------------------------------------------------------- |
| **Server-Side Search** | Context7, Deepcon      | 65-75%   | Server must interpret vague user intent; requires expensive query understanding model |
| **Agent-Side RAG**     | Custom implementations | 90%+     | High accuracy but brittle — agent must discover and validate sources itself           |
| **ProContext**         | _This project_         | **90%+** | Agent navigates pre-validated, always-fresh sources; no discovery overhead            |

**Key differentiators:**

- **Registry-first resolution** — <10ms library lookup from a pre-built curated registry; no runtime discovery calls
- **Pre-processed sources** — Documentation URLs are validated at build time, not discovered at query time
- **Agent-driven navigation** — The agent's LLM reads the TOC and navigates to exactly what it needs; no server-side guessing
- **llms.txt native** — Purpose-built for AI-optimized documentation format
- **Always fresh** — On-demand fetching with a 24hr cache; never serves stale docs

---

## Planned Features

### 🎯 **Curated Registry**

- Pre-validated documentation sources for 1000+ projects
- Python libraries (PyPI), MCP servers, GitHub projects, standalone tools
- Weekly automated updates to discover new documentation

### 📄 **llms.txt Support**

- Native support for the [llms.txt standard](https://llmstxt.org) (AI-optimized documentation)
- Automatic discovery across documentation platforms (Mintlify, VitePress, custom)
- Fallback to GitHub README for projects without llms.txt

### ⚡ **Fast & Efficient**

- **First query**: 2-5 seconds (fetch + parse + cache)
- **Subsequent queries**: <100ms (served from cache)
- Incremental loading: only fetches documentation that is actually used

### 🔍 **Agent-Driven Navigation**

- The agent reads the table of contents (`get_library_docs`) and navigates to specific pages (`read_page`)
- No server-side keyword search or query interpretation — the agent's LLM already knows what it's looking for
- Gives agents full control over what they read and in what order

### 🔄 **Always Fresh**

- On-demand fetching ensures documentation is never stale
- Automatic background refresh when cache expires (24hr TTL)
- Serves latest documentation regardless of package version

### 🔧 **Flexible Configuration**

- Add custom documentation sources instantly via config
- No code changes needed for private/internal docs
- stdio (local) or HTTP (remote) transport

---

## Supported Documentation Sources

ProContext will support documentation from:

| Type                 | Examples                         | How It Works                                           |
| -------------------- | -------------------------------- | ------------------------------------------------------ |
| **Python Libraries** | langchain, fastapi, pydantic     | Discovered via PyPI, fetches llms.txt or GitHub README |
| **MCP Servers**      | @modelcontextprotocol/server-\*  | Registered in curated list, fetches from llms.txt      |
| **GitHub Projects**  | svelte, supabase, anthropic      | Builder converts GitHub /docs/ or README to llms.txt   |
| **Custom Docs**      | Internal tools, private projects | Add via custom sources config                          |

**Supported formats:**

- ✅ llms.txt (AI-optimized markdown)
- ✅ GitHub README.md
- ✅ GitHub /docs/ directories
- 🚧 HTML documentation sites (future)

---

## Architecture

ProContext uses a **registry-first, lazy-fetch** architecture:

```
┌─────────────────────────────────────────────────┐
│ Build Time: Registry Construction              │
│ • Discover 1000+ projects (PyPI, GitHub, hubs) │
│ • Validate llms.txt URLs                        │
│ • Output: known-libraries.json                  │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│ Runtime: Documentation Server                   │
│ • Load registry into memory (fast lookups)     │
│ • Fetch docs on-demand when agent queries      │
│ • Cache aggressively (SQLite, 24hr TTL)        │
│ • Agent navigates TOC and pages directly       │
└─────────────────────────────────────────────────┘
```

**Key principles:**

- **Registry-only resolution**: No runtime network calls for discovery; all sources pre-validated at build time
- **On-demand content fetching**: Only fetch docs that are actually used
- **Agent-driven navigation**: Agents read the TOC and navigate pages directly — no server-side search or query interpretation
- **Always latest**: No version-specific docs, always serves current documentation

---

## Development Status

**Current Phase**: Phase 3 — Page Reading & Parser

Phases 0 through 2 are complete. The server skeleton, configuration, data models, registry loader, fuzzy resolver, `resolve_library` tool, httpx fetcher with SSRF protection, SQLite cache with stale-while-revalidate, and `get_library_docs` tool are all implemented in `src/procontext/`. Phase 3 will implement the `read_page` tool and the heading parser.

### Specification Documents (`docs/specs/`)

All design decisions are captured here before implementation begins.

1. **[Functional Specification](docs/specs/01-functional-spec.md)** — Problem statement, 3 MCP tools (`resolve_library`, `get_library_docs`, `read_page`), security model, design decisions
2. **[Technical Specification](docs/specs/02-technical-spec.md)** — System architecture, data models, resolution algorithm, SQLite cache, heading parser, transports
3. **[Implementation Guide](docs/specs/03-implementation-guide.md)** — Project structure, coding conventions, 6 implementation phases, testing strategy
4. **[API Reference](docs/specs/04-api-reference.md)** — Formal MCP API: tool schemas, wire format examples, error codes, versioning policy
5. **[Security Specification](docs/specs/05-security-spec.md)** — Threat model, trust boundaries, security controls, data handling, dependency management

### Implementation Roadmap

- ✅ **Phase 0**: Foundation — server skeleton, config, logging, errors, models, protocols, `AppState`
- ✅ **Phase 1**: Registry & Resolution — `load_registry()`, `resolve_library` tool, fuzzy matching
- ✅ **Phase 2**: Fetcher & Cache — `get_library_docs` tool, httpx fetcher with SSRF protection, SQLite cache with stale-while-revalidate
- ⬜ **Phase 3**: Page Reading & Parser — `read_page` tool, heading parser, section extraction
- ⬜ **Phase 4**: HTTP Transport — Streamable HTTP, `MCPSecurityMiddleware`, uvicorn
- ⬜ **Phase 5**: Registry Updates & Polish — background updates, cache cleanup, CI/CD, Docker, `uvx` packaging

---

## Installation

> 🚧 **Coming Soon** — Installation instructions will be added once Phase 2 (`get_library_docs`) is complete and the server can deliver end-to-end documentation responses.

The server will support both **stdio** (local) and **HTTP** (remote) modes, installable via `uvx` or pip, and configurable for Claude Code, Cursor, Windsurf, and other MCP clients.

---

## Contributing

Contributions are welcome! See **[CONTRIBUTING.md](CONTRIBUTING.md)** for setup instructions, development workflow, coding conventions, and how to submit a pull request.

---

## Technology Stack

- **Language**: Python 3.12+
- **Package Manager**: uv
- **MCP SDK**: `mcp` (FastMCP)
- **HTTP Client**: httpx (async, with SSRF protection)
- **Database**: SQLite via aiosqlite
- **Settings**: pydantic-settings (YAML + env vars)
- **Fuzzy Matching**: rapidfuzz (Phase 1)
- **Logging**: structlog (structured JSON to stderr)
- **Testing**: pytest + pytest-asyncio + respx
- **Linting**: ruff
- **Type Checking**: pyright

---

## License

This project is licensed under the **GNU General Public License v3.0** - see the [LICENSE](LICENSE) file for details.

**Why GPL-3.0?** We want ProContext to remain free and open-source forever. The GPL ensures that any modifications or derivatives must also be open-source, preventing proprietary forks.

---

## Purpose & Vision

ProContext was created to solve the accuracy problem in AI coding agents by providing them with reliable, up-to-date documentation access.

---

## Acknowledgments

- [Model Context Protocol (MCP)](https://modelcontextprotocol.io) by Anthropic
- [llms.txt standard](https://llmstxt.org) for AI-optimized documentation
- [llms-txt-hub](https://github.com/thedaviddias/llms-txt-hub) for curated llms.txt registry
- [top-pypi-packages](https://hugovk.github.io/top-pypi-packages/) for popularity rankings

---

## Links

- **Specifications**: [`docs/specs/`](docs/specs/)
- **Issues**: [GitHub Issues](https://github.com/procontexthq/procontext/issues)
- **Discussions**: [GitHub Discussions](https://github.com/procontexthq/procontext/discussions)
- **MCP Documentation**: [modelcontextprotocol.io](https://modelcontextprotocol.io)
- **llms.txt Standard**: [llmstxt.org](https://llmstxt.org)

---

<div align="center">

**Built with ❤️ for AI coding agents**

</div>
