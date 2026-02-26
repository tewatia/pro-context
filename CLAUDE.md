# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About the Project

ProContext is an open-source MCP (Model Context Protocol) documentation server that provides AI coding agents with accurate, up-to-date library documentation to prevent hallucination of API details. Licensed under GPL-3.0.

## About the Author

This project is authored by Ankur Tewatia, a Senior Lead Consultant with more than a decade of experience in the software industry.

## ⚠️ CRITICAL: Git Operations Policy

**NEVER commit and push changes without explicit user approval.**

You must:

1. Wait for the user to explicitly ask you to commit and push any changes made to the documentation or code.
2. If you believe a commit is necessary, you can say "I think we should commit these changes. Should I commit and push them?" and wait for the user's response.

## Project Motivation

Ankur has recently been working with Generative AI-based applications. Since this is a relatively new technology, all the libraries are relatively new as well and are updated frequently, which makes it difficult for coding agents to produce accurate code leveraging these libraries. Ankur's aim with this repo is to make coding agents more reliable by providing them with correct and up-to-date information.

## Implementation Phases

- ✅ **Phase 0**: Foundation — `pyproject.toml`, errors, models package, protocols, config, `AppState`, server skeleton, `RegistryIndexes` stub, `tools/` package
- ✅ **Phase 1**: Registry & Resolution — `load_registry()`, `build_indexes()`, `resolve_library` tool, fuzzy matching (rapidfuzz)
- ✅ **Phase 2**: Fetcher & Cache — `get_library_docs` tool, httpx fetcher with SSRF protection, SQLite cache (aiosqlite), stale-while-revalidate
- ✅ **Phase 3**: Page Reading & Parser — `read_page` tool, heading parser, section extraction
- ⬜ **Phase 4**: HTTP Transport — Streamable HTTP (MCP spec 2025-11-25), `MCPSecurityMiddleware`, uvicorn
- ⬜ **Phase 5**: Registry Updates & Polish — background update check, cache cleanup scheduler, CI/CD, Docker, `uvx` packaging

**Current state**: Phase 3 is complete. Source code lives in `src/procontext/`. Phase 4 implementation is next.

### Active Specifications (`docs/specs/`)

These are the authoritative design documents for the current open-source version.

- `docs/specs/01-functional-spec.md` — Problem statement, 3 MCP tools (`resolve_library`, `get_library_docs`, `read_page`), 1 resource, transport modes, registry, SQLite cache, security model, design decisions
- `docs/specs/02-technical-spec.md` — System architecture, technology stack, data models (Pydantic), in-memory registry indexes, resolution algorithm, fetcher (httpx + SSRF), SQLite cache schema, heading parser, stdio + Streamable HTTP transport, registry update mechanism, configuration, logging
- `docs/specs/03-implementation-guide.md` — Project structure, pyproject.toml, coding conventions (AppState injection, ProContextError pattern, logging guidance), 6 implementation phases with per-phase file tables, testing strategy (respx + in-memory SQLite), CI/CD
- `docs/specs/04-api-reference.md` — Formal MCP API: tool definitions (JSON Schema + wire format examples), resource schema, full error code catalogue, stdio and HTTP transport reference, versioning policy
- `docs/specs/05-security-spec.md` — Threat model (6 threats with severity and mitigation status), trust boundaries, security controls summary, known limitations, data handling, dependency vulnerability management, phase-gated security testing

You are allowed to create new documents if the discussion warrants it. Update this section to link to any new documents you create.

## Overview of tech stack, architecture, coding conventions, configurations, commands and testing strategy

_Expand this section as new phases are completed. Only add what Claude cannot infer from reading the code._

| Include in this section                              | Do NOT include                                     |
| ---------------------------------------------------- | -------------------------------------------------- |
| Bash commands Claude can't guess                     | Anything Claude can figure out by reading code     |
| Code style rules that differ from defaults           | Standard language conventions Claude already knows |
| Testing instructions and preferred test runners      | Detailed API documentation (link to docs instead)  |
| Repository etiquette (branch naming, PR conventions) | Information that changes frequently                |
| Architectural decisions specific to this project     | Long explanations or tutorials                     |
| Developer environment quirks (required env vars)     | File-by-file descriptions of the codebase          |
| Common gotchas or non-obvious behaviors              | Self-evident practices like "write clean code"     |

### Commands

```bash
# Install dependencies and create virtualenv
uv sync --dev

# Run the server (stdio transport)
uv run procontext

# Lint
uv run ruff check src/

# Format
uv run ruff format src/

# Type check
uv run pyright src/

# Run tests
uv run pytest
```

### Critical: stdout vs stderr

In stdio MCP mode, **stdout is owned by the MCP JSON-RPC stream**. Any writes to stdout will corrupt the protocol. Logs must always go to stderr. `structlog.PrintLoggerFactory(file=sys.stderr)` is already configured in `server.py`. Never use `print()` without `file=sys.stderr` in server code.

### AppState injection pattern

`AppState` is created once in the FastMCP lifespan and injected into tool handlers via `ctx.request_context.lifespan_context`. Tools receive `AppState` explicitly — no global variables, no module-level singletons.

### Platform-aware paths

All filesystem defaults use `platformdirs` — never hardcode Unix paths like `~/.local/share/` or `~/.config/`. The defaults resolve to platform-appropriate locations automatically:

| Platform | Config dir | Data dir |
|----------|-----------|----------|
| Linux | `~/.config/procontext` | `~/.local/share/procontext` |
| macOS | `~/Library/Application Support/procontext` | `~/Library/Application Support/procontext` |
| Windows | `C:\Users\<user>\AppData\Local\procontext` | `C:\Users\<user>\AppData\Local\procontext` |

Config paths: `platformdirs.user_config_dir("procontext")` in `config.py`. Data paths: `platformdirs.user_data_dir("procontext")` in `config.py`. Registry paths derive from the data dir via `server.py:_registry_paths()`.

`_fsync_directory()` in `registry.py` is a no-op on Windows (`sys.platform == "win32"` guard) since Windows does not support `fsync` on directory handles.

### Forward references and TYPE_CHECKING

All modules use `from __future__ import annotations`. Imports only needed for type annotations go inside `if TYPE_CHECKING:` blocks. This allows circular-free imports and lets Phase 0 reference types from Phase 1+ modules that don't fully exist yet.

### Type checker

This project uses **pyright** (not mypy). Run `uv run pyright src/` to check. Standard mode is enforced.

## Coding Guidelines

This project follows a set of non-obvious coding guidelines specifically for public library development. These must be applied when writing or reviewing any code in this repo.

See [`docs/coding-guidelines.md`](docs/coding-guidelines.md) for the full list.

Key areas covered: API design, error handling, versioning and breaking changes, testing strategy, supply chain security, and library adoptability.

## Instructions for working with this repo

1. Your job is to act as a coding partner, not as an assistant.
2. Your key responsibility is making this repo better and useful for everyone, including Ankur and yourself.
3. Ankur appreciates honest feedback. Do not blindly agree to whatever he asks.
4. When brainstorming, actively participate and add value to the conversation rather than just answering questions.
5. You are a contributor to the project. Take ownership and actively look for ways to improve this repo.
6. Avoid making assumptions. Refer to online sources and cross-verify information. If the requirement is unclear, ask Ankur for clarification.
