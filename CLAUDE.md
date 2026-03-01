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
6. **Run all checks before pushing**
   ```bash
   uv run ruff check src/ tests/
   uv run ruff format src/ tests/
   uv run pyright src/
   uv run pytest --cov=src/procontext --cov-fail-under=90
   ```

## Specifications

Spec documents are in `docs/specs/` - read the relevant one before making changes.
These are the authoritative design documents for this repo.
You are allowed to create new documents if the discussion warrants it.

## Commands

```bash
# Install dependencies and create virtualenv
uv sync --dev

# Run the server (stdio transport)
uv run procontext

# Run the server (HTTP transport)
PROCONTEXT__SERVER__TRANSPORT=http uv run procontext

# First-time setup (download registry)
uv run procontext setup

# Lint
uv run ruff check src/

# Format
uv run ruff format src/

# Type check
uv run pyright src/

# Run tests
uv run pytest
```

## Architecture

**AppState injection** - `AppState` is created once in the FastMCP lifespan and injected into tool handlers via `ctx.request_context.lifespan_context`. Tools receive `AppState` explicitly - no global variables, no module-level singletons.

**HTTP transport - MCPSecurityMiddleware** - `MCPSecurityMiddleware` in `transport.py` is a **pure ASGI middleware** (not `BaseHTTPMiddleware`). `BaseHTTPMiddleware` buffers the full response body before passing it along, which silently breaks SSE streaming. Never switch it to `BaseHTTPMiddleware`. The middleware enforces three checks in order: bearer auth → origin validation → protocol version. The ASGI `__call__` only intercepts `scope["type"] == "http"`; `lifespan` and `websocket` scopes pass through unconditionally.

## Coding Conventions

**Forbidden imports inside functions** - no imports inside functions. THEY SHOULD BE AT THE TOP OF THE FILE.

**Logging** -

- Use structlog for all runtime logging - never the stdlib `logging` module directly, and never `print()` without `file=sys.stderr`.
- In stdio MCP mode, stdout is owned by the MCP JSON-RPC stream. Any writes to stdout will corrupt the protocol. Logs must always go to stderr. `structlog.PrintLoggerFactory(file=sys.stderr)` is already configured in `server.py`.

**Platform-aware paths** - All filesystem defaults use `platformdirs` - never hardcode Unix paths like `~/.local/share/` or `~/.config/`. Use `platformdirs.user_config_dir("procontext")` in `config.py` and `platformdirs.user_data_dir("procontext")` for data. Registry paths derive from `settings.data_dir` via `server.py:_registry_paths()`.

**Annotations and TYPE_CHECKING** -

- This project uses **pyright** (not mypy). Standard mode is enforced.
- Provide high-quality type support. Do not only add basic type hints; use meaningful generics and define structured, typed exceptions.
- All modules use `from __future__ import annotations`. Imports only needed for type annotations go inside `if TYPE_CHECKING:` blocks.

## Changelog Maintenance

`CHANGELOG.md` is maintained via the `/changelog-release` skill - use it before committing to populate `[Unreleased]`, or with a version number to finalize a release section.

## Coding Guidelines

**After making changes, you must run linting, formatting, type checks, and pytest to verify the codebase is clean and all tests pass..**

This project follows a set of non-obvious coding guidelines. These must be applied when writing or reviewing any code in this repo.

See [`docs/coding-guidelines.md`](docs/coding-guidelines.md) for the full list.

## Testing Requirements

- Framework: `uv run --frozen pytest`
- Async testing: use anyio, not asyncio
- Coverage: test edge cases and errors
- New features require tests
- Bug fixes require regression tests
- IMPORTANT: Before pushing, verify highest possible branch coverage on changed files by running
  `uv run --frozen pytest -x` (coverage is configured in `pyproject.toml` with `fail_under = 90`
  and `branch = true`). If any branch is uncovered, add a test for it before pushing.
- Avoid `anyio.sleep()` with a fixed duration to wait for async operations. Instead:
  - Use `anyio.Event` — set it in the callback/handler, `await event.wait()` in the test
  - For stream messages, use `await stream.receive()` instead of `sleep()` + `receive_nowait()`
  - Exception: `sleep()` is appropriate when testing time-based features (e.g., timeouts)
- Wrap indefinite waits (`event.wait()`, `stream.receive()`) in `anyio.fail_after(5)` to prevent hangs

## Instructions for working with this repo

1. Your job is to act as a coding partner, not as an assistant.
2. Your key responsibility is making this repo better and useful for everyone, including Ankur and yourself.
3. Ankur appreciates honest feedback. Do not blindly agree to whatever he asks.
4. When brainstorming, actively participate and add value to the conversation rather than just answering questions.
5. You are a contributor to the project. Take ownership and actively look for ways to improve this repo.
6. Avoid making assumptions. Refer to online sources and cross-verify information. If the requirement is unclear, ask Ankur for clarification.

## Updates to CLAUDE.md

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
