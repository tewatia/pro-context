# Pro-Context

**MCP documentation server that provides AI coding agents with accurate, up-to-date documentation to prevent API hallucination.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.0-green.svg)](https://modelcontextprotocol.io)

Pro-Context is an open-source [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that will deliver accurate, fresh documentation to AI coding agents like Claude Code, Cursor, and Windsurf. It prevents hallucinated APIs by serving real documentation from Python libraries, MCP servers, GitHub projects, and any source that publishes [llms.txt](https://llmstxt.org) files.

> ⚠️ **Project Status**: Currently in **Specification/Design Phase** (Phase 0). No implementation yet — only design documents. See [Development Status](#development-status) below.

---

## The Problem

AI coding agents often hallucinate outdated or incorrect API details because:
- They're trained on old data
- Documentation changes frequently
- They lack access to current library docs

**Pro-Context solves this** by giving agents on-demand access to fresh, curated documentation.

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
- BM25 full-text search across indexed documentation
- Incremental indexing (only indexes what you actually use)

### 🔍 **Hybrid Retrieval**
- **Fast path**: Server-side BM25 search for keyword queries
- **Navigation path**: Agent-driven browsing of TOC and pages
- Agents get the best of both: speed + flexibility

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

Pro-Context will support documentation from:

| Type | Examples | How It Works |
|------|----------|--------------|
| **Python Libraries** | langchain, fastapi, pydantic | Discovered via PyPI, fetches llms.txt or GitHub README |
| **MCP Servers** | @modelcontextprotocol/server-* | Registered in curated list, fetches from llms.txt |
| **GitHub Projects** | svelte, supabase, anthropic | Direct GitHub adapter, fetches /docs/ or README |
| **Custom Docs** | Internal tools, private projects | Add via custom sources config |

**Supported formats:**
- ✅ llms.txt (AI-optimized markdown)
- ✅ GitHub README.md
- ✅ GitHub /docs/ directories
- 🚧 HTML documentation sites (future)

---

## Architecture

Pro-Context uses a **registry-first, lazy-fetch** architecture:

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
│ • Cache aggressively (SQLite + memory)         │
│ • BM25 search across indexed content           │
└─────────────────────────────────────────────────┘
```

**Key principles:**
- **Registry-only resolution**: No runtime network calls for discovery
- **On-demand content fetching**: Only fetch docs that are actually used
- **Incremental indexing**: Search index grows as agents use the server
- **Always latest**: No version-specific docs, always serves current documentation

---

## Development Status

**Current Phase**: Specification/Design (Phase 0)

We are finalizing comprehensive design specifications before implementation begins. All design decisions, architecture choices, and implementation details are documented in [`docs/specs/`](docs/specs/).

### Documentation Structure

The project has six detailed specification documents:

1. **[Competitive Analysis](docs/specs/01-competitive-analysis.md)** — Market research, accuracy benchmarks, key insights
2. **[Functional Specification](docs/specs/02-functional-spec.md)** — MCP tools, user stories, error handling, security model
3. **[Technical Specification](docs/specs/03-technical-spec.md)** — System architecture, data models, cache design, search engine
4. **[Implementation Guide](docs/specs/04-implementation-guide.md)** — Project structure, dependencies, coding conventions, testing strategy
5. **[Library Resolution](docs/specs/05-library-resolution.md)** — Registry schema, resolution algorithm, package grouping
6. **[Registry Build System](docs/specs/06-registry-build-system.md)** — Build-time discovery pipeline, validation, quality assurance

**Design status**: All specifications are in draft/review phase. Implementation will begin once specs are finalized and approved.

### Implementation Roadmap

- ✅ **Phase 0**: Specification/Design — *In Progress*
- ⬜ **Phase 1**: Foundation (MCP server skeleton, config, logging) — *Not Started*
- ⬜ **Phase 2**: Core Documentation Pipeline (adapters, cache, basic tools) — *Not Started*
- ⬜ **Phase 3**: Search & Navigation (BM25 indexing, search-docs, read-page) — *Not Started*
- ⬜ **Phase 4**: HTTP Mode & Authentication (API keys, rate limiting) — *Not Started*
- ⬜ **Phase 5**: Polish & Production Readiness (prompts, Docker, CI/CD) — *Not Started*

---

## Installation

> 🚧 **Coming Soon** — Installation instructions will be added once Phase 1 implementation begins.

The server will support both **stdio** (local) and **HTTP** (remote) modes, installable via uv or pip, and configurable for Claude Code, Cursor, Windsurf, and other MCP clients.

---

## Contributing

Contributions are welcome! Since we're in the design phase:

### How to Contribute Now

1. **Review specifications**: Read through [`docs/specs/`](docs/specs/) and provide feedback
2. **Open issues**: Report inconsistencies, suggest improvements, ask questions
3. **Discuss design decisions**: Join conversations in GitHub Discussions
4. **Report typos/errors**: Documentation improvements are always welcome

### Future Contributions

Once implementation begins (after Phase 0), we'll welcome:
- Code contributions following the implementation guide
- Additional documentation sources for the registry
- Bug reports and fixes
- Performance improvements
- Test coverage enhancements

---

## Technology Stack

**Planned stack** (as specified in design docs):

- **Language**: Python 3.12+
- **Package Manager**: uv (with pip fallback)
- **MCP SDK**: Official Python SDK
- **Database**: SQLite (via aiosqlite)
- **Search**: BM25 via SQLite FTS5
- **Logging**: structlog
- **Testing**: pytest + pytest-asyncio
- **Linting**: ruff
- **Type Checking**: mypy

---

## License

This project is licensed under the **GNU General Public License v3.0** - see the [LICENSE](LICENSE) file for details.

**Why GPL-3.0?** We want Pro-Context to remain free and open-source forever. The GPL ensures that any modifications or derivatives must also be open-source, preventing proprietary forks.

---

## Author

**Ankur Tewatia** — Senior Lead Consultant with 10+ years of experience in software engineering, currently focused on Generative AI applications.

Pro-Context was created to solve the accuracy problem in AI coding agents by providing them with reliable, up-to-date documentation access.

---

## Acknowledgments

- [Model Context Protocol (MCP)](https://modelcontextprotocol.io) by Anthropic
- [llms.txt standard](https://llmstxt.org) for AI-optimized documentation
- [llms-txt-hub](https://github.com/thedaviddias/llms-txt-hub) for curated llms.txt registry
- [top-pypi-packages](https://hugovk.github.io/top-pypi-packages/) for popularity rankings

---

## Links

- **Documentation**: [`docs/specs/`](docs/specs/)
- **Issues**: [GitHub Issues](https://github.com/tewatia/pro-context/issues)
- **Discussions**: [GitHub Discussions](https://github.com/tewatia/pro-context/discussions)
- **MCP Documentation**: [modelcontextprotocol.io](https://modelcontextprotocol.io)
- **llms.txt Standard**: [llmstxt.org](https://llmstxt.org)

---

<div align="center">

**Built with ❤️ for AI coding agents**

⭐ Star this repo if you find it useful!

</div>
