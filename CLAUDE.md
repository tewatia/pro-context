# Development Guidelines

This document contains critical information about working with this codebase. Follow these guidelines precisely.

## About the Project

ProContext is an open-source MCP (Model Context Protocol) documentation server that provides AI coding agents with accurate, up-to-date library documentation to prevent hallucination of API details. Licensed under GPL-3.0.

## Project Motivation

Ankur (Author) has recently been working with Generative AI-based applications. Since this is a relatively new technology, all the libraries are relatively new as well and are updated frequently, which makes it difficult for coding agents to produce accurate code leveraging these libraries. Ankur's aim with this repo is to make coding agents more reliable by providing them with correct and up-to-date information.

## ⚠️ CRITICAL: Git Operations Policy

**NEVER commit and push changes without explicit user approval.**

You must:

1. Wait for the user to explicitly ask you to commit and push any changes made to the documentation or code.
2. If you believe a commit is necessary, you can say "I think we should commit these changes. Should I commit and push them?" and wait for the user's response.
3. NEVER ever mention a `co-authored-by` or similar aspects. In particular, never mention the tool used to create the commit message or PR.
4. **Commit by intent**. If something is a coherent unit (a feature, fix, refactor, doc update), it deserves its own commit. Avoid these two extremes
   - ❌ One giant commit/day: hard to review, hard to revert, hard to bisect.
   - ❌ A commit for every tiny edit: noise, harder to understand history.
5. Commit only the changes relevant to the current session. If there are other pending changes, ask the user whether you should commit them as well.

## Specifications

Spec documents are in `docs/specs/` — read the relevant one before making changes.
These are the authoritative design documents for this repo.
You are allowed to create new documents if the discussion warrants it.

## Overview of tech stack, architecture, coding conventions, configurations, commands and testing strategy

_Only add what Claude cannot infer from reading the code._

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

# Run the server (HTTP transport)
PROCONTEXT__SERVER__TRANSPORT=http uv run procontext

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

All filesystem defaults use `platformdirs` — never hardcode Unix paths like `~/.local/share/` or `~/.config/`. Use `platformdirs.user_config_dir("procontext")` in `config.py` and `platformdirs.user_data_dir("procontext")` for data. Registry paths derive from the data dir via `server.py:_registry_paths()`.

### Forward references and TYPE_CHECKING

All modules use `from __future__ import annotations`. Imports only needed for type annotations go inside `if TYPE_CHECKING:` blocks.

### Type checker

This project uses **pyright** (not mypy). Run `uv run pyright src/` to check. Standard mode is enforced.

### HTTP transport — MCPSecurityMiddleware

`MCPSecurityMiddleware` in `server.py` is a **pure ASGI middleware** (not `BaseHTTPMiddleware`). This is intentional: `BaseHTTPMiddleware` buffers the full response body before passing it along, which silently breaks SSE streaming. Never switch it to `BaseHTTPMiddleware`.

The middleware enforces three checks in order: bearer auth → origin validation → protocol version. The ASGI `__call__` only intercepts `scope["type"] == "http"`; `lifespan` and `websocket` scopes pass through unconditionally.

## Changelog Maintenance

`CHANGELOG.md` is maintained via the `/changelog-release` skill — use it after committing to populate `[Unreleased]`, or with a version number to finalize a release section.

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
