# Pro-Context: Implementation Guide

> **Document**: 03-implementation-guide.md
> **Status**: Draft v2
> **Last Updated**: 2026-02-23
> **Depends on**: 01-functional-spec.md, 02-technical-spec.md

---

## Table of Contents

- [1. Project Structure](#1-project-structure)
  - [1.1 Source Layout](#11-source-layout)
  - [1.2 Module Responsibilities](#12-module-responsibilities)
- [2. Dependencies](#2-dependencies)
- [3. Coding Conventions](#3-coding-conventions)
  - [3.1 General Rules](#31-general-rules)
  - [3.2 Protocol Interfaces](#32-protocol-interfaces)
  - [3.3 AppState and Dependency Injection](#33-appstate-and-dependency-injection)
  - [3.4 Error Handling](#34-error-handling)
  - [3.5 Logging](#35-logging)
- [4. Implementation Phases](#4-implementation-phases)
  - [Phase 0: Foundation](#phase-0-foundation)
  - [Phase 1: Registry & Resolution](#phase-1-registry--resolution)
  - [Phase 2: Fetcher & Cache](#phase-2-fetcher--cache)
  - [Phase 3: Page Reading & Parser](#phase-3-page-reading--parser)
  - [Phase 4: HTTP Transport](#phase-4-http-transport)
  - [Phase 5: Registry Updates & Polish](#phase-5-registry-updates--polish)
- [5. Testing Strategy](#5-testing-strategy)
- [6. CI/CD](#6-cicd)
  - [Commit Message Convention](#commit-message-convention)
  - [ci.yml — Test Pipeline](#ciyml--test-pipeline)
  - [release.yml — Release Pipeline](#releaseyml--release-pipeline)
- [7. Local Development Setup](#7-local-development-setup)

---

## 1. Project Structure

### 1.1 Source Layout

```
pro-context/
├── pyproject.toml
├── CHANGELOG.md                      # Keep a Changelog format; updated on every release
├── pro-context.example.yaml          # Example config (committed); copy to pro-context.yaml for local use
├── src/
│   └── pro_context/
│       ├── __init__.py               # __version__ only
│       ├── py.typed                  # PEP 561 marker — declares this package is typed
│       ├── server.py                 # FastMCP instance, lifespan, tool registration, entrypoint
│       ├── state.py                  # AppState dataclass
│       ├── config.py                 # Settings via pydantic-settings + YAML
│       ├── errors.py                 # ErrorCode, ProContextError
│       ├── protocols.py              # CacheProtocol, FetcherProtocol (typing.Protocol)
│       ├── models/
│       │   ├── __init__.py           # Re-exports all public models
│       │   ├── registry.py           # RegistryEntry, RegistryPackages, LibraryMatch
│       │   ├── cache.py              # TocCacheEntry, PageCacheEntry
│       │   └── tools.py              # Heading, all tool I/O models
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── resolve_library.py    # Business logic for resolve-library
│       │   ├── get_library_docs.py   # Business logic for get-library-docs
│       │   └── read_page.py          # Business logic for read-page
│       ├── registry.py               # Registry loading, index building, update check
│       ├── resolver.py               # 5-step resolution algorithm, fuzzy matching
│       ├── fetcher.py                # HTTP client, SSRF validation, redirect handling
│       ├── cache.py                  # SQLite cache: toc_cache + page_cache, stale-while-revalidate
│       ├── parser.py                 # Heading parser, anchor generation, line number tracking
│       ├── transport.py              # MCPSecurityMiddleware for HTTP mode
│       └── data/
│           └── known-libraries.json  # Bundled registry snapshot (updated at release time)
├── tests/
│   ├── conftest.py                   # Top-level fixtures shared across all tests
│   ├── unit/
│   │   ├── conftest.py               # Unit-specific fixtures (no I/O)
│   │   ├── test_resolver.py          # resolve-library: normalisation, all 5 steps, edge cases
│   │   ├── test_fetcher.py           # SSRF validation, redirect handling, error cases
│   │   ├── test_cache.py             # Cache read/write, TTL expiry, stale-while-revalidate
│   │   └── test_parser.py            # Heading detection, code block suppression, section extraction
│   └── integration/
│       ├── conftest.py               # Integration-specific fixtures (full AppState, mocked HTTP)
│       └── test_tools.py             # Full tool call pipeline: input → output shape
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
└── .gitignore
```

### 1.2 Module Responsibilities

The structure enforces a strict layering. Violations (e.g., a tool importing from `cache.py` directly) indicate a missing abstraction.

| Layer | Modules | Rule |
|-------|---------|------|
| **Entrypoint** | `server.py` | Registers tools, wires `AppState`, starts transport. No business logic. |
| **Tools** | `tools/*.py` | One file per tool. Receives `AppState`, returns output dict. Raises `ProContextError`. |
| **Services** | `resolver.py`, `fetcher.py`, `cache.py`, `parser.py` | Pure business logic. No MCP imports. Typed against protocols, not concrete classes. |
| **Infrastructure** | `registry.py`, `config.py`, `transport.py` | Setup and wiring. Run once at startup. |
| **Shared** | `models/`, `errors.py`, `protocols.py`, `state.py` | No dependencies on other layers. Imported freely. |

**Adding a new tool**: Create `tools/new_tool.py`, register it in `server.py`. No other files change.

**Swapping the cache backend**: Provide a new class implementing `CacheProtocol`, inject it into `AppState`. No tool code changes.

---

## 2. Dependencies

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pro_context"]

[project]
name = "pro-context"
version = "0.1.0"
description = "MCP server for accurate, up-to-date library documentation"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "GPL-3.0" }

dependencies = [
    "mcp>=1.26.0,<2.0.0",                   # FastMCP — official MCP Python SDK
    "httpx>=0.28.0,<1.0.0",                  # Async HTTP client
    "aiosqlite>=0.19.0,<1.0.0",              # Async SQLite
    "pydantic>=2.5.0,<3.0.0",               # Data validation
    "pydantic-settings>=2.2.0,<3.0.0",      # YAML config + env var overrides
    "pyyaml>=6.0.1,<7.0.0",                 # YAML parser (required by pydantic-settings)
    "rapidfuzz>=3.6.0,<4.0.0",              # Levenshtein fuzzy matching
    "structlog>=24.1.0,<26.0.0",            # Structured logging
    "uvicorn>=0.34.0,<1.0.0",               # ASGI server for HTTP transport
]

[project.scripts]
pro-context = "pro_context.server:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=1.0.0",
    "pytest-mock>=3.12.0",
    "respx>=0.21.0",                            # httpx request mocking
    "ruff>=0.11.0",
    "pyright>=1.1.400",                         # Type checking (also run in CI)
]

[tool.pytest.ini_options]
asyncio_mode = "auto"          # All async test functions run without explicit decorator
testpaths = ["tests"]          # Explicit — avoids discovery surprises when run from subdirs

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "TCH"]

[tool.ruff.lint.flake8-type-checking]
runtime-evaluated-base-classes = ["pydantic.BaseModel", "pydantic_settings.BaseSettings"]

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "standard"
include = ["src"]
```

**`[build-system]`**: Required to build a wheel with `pip wheel .` or `uvx`. Without it, the package cannot be packaged or distributed. `hatchling` is the default backend for projects created with `uv init`.

**`py.typed`**: An empty file at `src/pro_context/py.typed`. Its presence tells pyright and mypy that this package ships type annotations and they should be honoured. Without it, type checkers silently ignore the package's types when it is imported.

**`pyright` in dev extras**: Keeps the type checker version pinned and consistent between local dev and CI.

**`testpaths`**: Prevents pytest from discovering tests in unexpected locations (e.g., inside `src/`) when run from the project root.

**Version pinning**: Minor version upper bounds (`<2.0.0`) on all dependencies. Tighten to patch bounds only if a dependency has a documented history of breaking minor releases.

**Version floors**: Since this is a new project with no legacy consumers, version floors should track reasonably close to the latest stable release at the time of writing. There is no reason to support old versions that nobody is using yet. Review and bump floors at the start of each implementation phase — stale floors accumulate silently and can mask behavioural differences between the version you test against and the version the floor permits.

**Dependency footprint**: Pro-Context has 9 runtime dependencies. Each is justified by a capability that would require significantly more code to replicate correctly (async HTTP with SSRF-safe redirect control, async SQLite, fuzzy string matching, structured logging, validated settings). Zero-dependency is a virtue but not at the cost of correctness or maintainability. Before adding any new runtime dependency, verify that the same capability cannot be covered by an existing dependency or the Python standard library.

**License compatibility**: All runtime dependencies are compatible with GPL-3.0. Verified at last review (2026-02-24):

| Package | License | Notes |
|---------|---------|-------|
| `mcp` | MIT | Official MCP Python SDK by Anthropic |
| `httpx` | BSD-3-Clause | |
| `aiosqlite` | MIT | |
| `pydantic` | MIT | |
| `pydantic-settings` | MIT | |
| `pyyaml` | MIT | |
| `rapidfuzz` | MIT | |
| `structlog` | MIT OR Apache-2.0 | Dual-licensed; either is compatible with GPL-3.0 |
| `uvicorn` | BSD-3-Clause | |

Re-verify this table whenever a dependency is added or its major version is bumped. MIT and BSD-3-Clause are permissive and always compatible with GPL-3.0. Apache-2.0 is compatible with GPL-3.0 (but not GPL-2.0 — not a concern here).

---

## 3. Coding Conventions

### 3.1 General Rules

**Async throughout.** Every I/O operation (SQLite, HTTP) is async. Tool handlers are `async def`. The only synchronous code is in-memory computation (index lookups, string normalisation, heading parsing).

**Type hints on every function signature.** Return types included. Use `X | None` union syntax (Python 3.10+), not `Optional[X]`.

```python
# Correct
async def get_toc(self, library_id: str) -> TocCacheEntry | None: ...

# Incorrect
async def get_toc(self, library_id: str) -> Optional[TocCacheEntry]: ...
```

**Pydantic at all external boundaries.** Tool inputs are validated via Pydantic models before any processing. Registry JSON is parsed into `RegistryEntry` models on load. Never pass raw dicts between modules — use typed models.

**Bundled data via `importlib.resources`.** Do not use `__file__`-relative paths to locate `known-libraries.json`. They break inside zip archives and editable installs.

```python
# Correct
from importlib.resources import files
import json

def load_bundled_registry() -> list[dict]:
    text = files("pro_context.data").joinpath("known-libraries.json").read_text(encoding="utf-8")
    return json.loads(text)

# Incorrect
import os
path = os.path.join(os.path.dirname(__file__), "data", "known-libraries.json")
```

### 3.2 Protocol Interfaces

Swappable components (`Cache`, `Fetcher`) are typed against `typing.Protocol` interfaces defined in `protocols.py`. Tool handlers and `AppState` reference the protocol, not the concrete class. This has two benefits:

1. **Tests** can use lightweight in-memory implementations without instantiating SQLite or real HTTP clients.
2. **Future backends** (Redis cache, enterprise auth-aware fetcher) can be swapped by injecting a different implementation — no tool code changes.

```python
# protocols.py
from typing import Protocol
from pro_context.models import TocCacheEntry, PageCacheEntry

class CacheProtocol(Protocol):
    async def get_toc(self, library_id: str) -> TocCacheEntry | None: ...
    async def set_toc(self, library_id: str, url: str, content: str, ttl_hours: int) -> None: ...
    async def get_page(self, url_hash: str) -> PageCacheEntry | None: ...
    async def set_page(self, url: str, url_hash: str, content: str, ttl_hours: int) -> None: ...
    async def cleanup_expired(self) -> None: ...

class FetcherProtocol(Protocol):
    async def fetch(self, url: str, allowlist: frozenset[str]) -> str: ...
```

The concrete `Cache` (SQLite) and `Fetcher` (httpx) classes implement these protocols implicitly — no `class Cache(CacheProtocol)` inheritance needed. Python's structural subtyping handles it.

### 3.3 AppState and Dependency Injection

All shared state lives in `AppState` (`state.py`), instantiated once at startup and injected into every tool call. This makes tests straightforward — pass a test `AppState` with mock implementations.

```python
# state.py
from dataclasses import dataclass
from pro_context.config import Settings
from pro_context.registry import RegistryIndexes
from pro_context.protocols import CacheProtocol, FetcherProtocol
import httpx

@dataclass
class AppState:
    settings: Settings
    indexes: RegistryIndexes
    registry_version: str
    http_client: httpx.AsyncClient
    cache: CacheProtocol       # Typed as protocol, not concrete Cache
    fetcher: FetcherProtocol   # Typed as protocol, not concrete Fetcher
    allowlist: frozenset[str]
```

`AppState` is passed into the server via FastMCP's lifespan context and flows into tool handlers through the MCP `Context` object:

```python
# server.py
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context

@asynccontextmanager
async def lifespan(server: FastMCP):
    state = await _create_app_state()
    yield state                    # Available as ctx.request_context.lifespan_context
    await state.http_client.aclose()

mcp = FastMCP("pro-context", lifespan=lifespan)

@mcp.tool()
async def resolve_library(query: str, ctx: Context) -> dict:
    state: AppState = ctx.request_context.lifespan_context
    return await tools.resolve_library.handle(query, state)
```

Tool modules receive `AppState` as a plain argument. They have no knowledge of FastMCP or the MCP protocol.

```python
# tools/resolve_library.py
async def handle(query: str, state: AppState) -> dict:
    ...
```

### 3.4 Error Handling

**Raise `ProContextError`, never return error dicts.** Tool handlers raise `ProContextError`. `server.py` catches it and serialises it into the MCP error response. Business logic modules never return `{"error": ...}` dicts.

```python
# Correct
if not entry:
    raise ProContextError(
        code=ErrorCode.LIBRARY_NOT_FOUND,
        message=f"Library '{library_id}' not found in registry.",
        suggestion="Call resolve-library to find the correct library ID.",
        recoverable=False,
    )

# Incorrect
if not entry:
    return {"error": {"code": "LIBRARY_NOT_FOUND", ...}}
```

### 3.5 Logging

**Bind log context at the start of each handler.** Use `structlog.get_logger().bind(...)` to attach the tool name and key inputs to every log line in a handler, without passing a logger argument through every function call.

```python
# tools/get_library_docs.py
import structlog

async def handle(library_id: str, state: AppState) -> dict:
    log = structlog.get_logger().bind(tool="get_library_docs", library_id=library_id)
    log.info("handler_called")
    ...
    log.info("cache_hit")
    ...
```

**Log at decision points, not at every line.** The goal is to be able to reconstruct what happened from the logs without drowning in noise. A good rule of thumb: log wherever the code makes a branching decision that would matter when debugging a production issue.

Mandatory log points:
- Server startup and shutdown (transport mode, registry version, entry count)
- Every tool call entry (tool name + key input — already provided by the bound context)
- Cache outcome: hit, stale hit, or miss (one line each; avoid logging on every cache read)
- Network fetch start and completion (URL, status code, response size)
- Any `ProContextError` raised — log before raising with `WARNING` level and the error code
- Background task outcomes: registry update (new version or already current), stale refresh (success or failure), cache cleanup (rows deleted)

Do not log:
- Inside tight loops (heading parsing, index building) — these are in-memory and fast
- Successful intermediate steps with no branching significance (e.g., "entering normalise_query", "regex matched")
- Redundant context already captured by the bound logger

**Exceptions must include `exc_info=True`.** Any `except` block that logs and continues (e.g., background tasks that swallow errors to stay alive) must pass `exc_info=True` so the full traceback is captured.

```python
# Correct — full traceback in the log
except Exception:
    log.warning("stale_refresh_failed", key=cache_key, exc_info=True)

# Incorrect — traceback is lost
except Exception as e:
    log.warning("stale_refresh_failed", key=cache_key, error=str(e))
```

`ProContextError` raised in tool handlers does not need `exc_info=True` — these are expected, handled errors. Reserve `exc_info=True` for unexpected exceptions that are caught and suppressed.

---

## 4. Implementation Phases

Each phase produces working, tested code. Later phases build on earlier ones without refactoring them.

---

### Phase 0: Foundation

**Goal**: A running MCP server that responds to the `initialize` handshake and returns a health status. No tools yet.

**Files to create**:

| File | What to implement |
|------|------------------|
| `pyproject.toml` | Full dependency list, `[build-system]`, scripts entry point |
| `src/pro_context/__init__.py` | `__version__ = "0.1.0"` |
| `src/pro_context/py.typed` | Empty file (PEP 561 marker) |
| `src/pro_context/errors.py` | `ErrorCode` (StrEnum), `ProContextError` |
| `src/pro_context/models/__init__.py` | Empty re-export stub (populated later) |
| `src/pro_context/models/registry.py` | `RegistryEntry`, `RegistryPackages` |
| `src/pro_context/config.py` | `Settings` with all fields and YAML loading |
| `src/pro_context/state.py` | `AppState` dataclass (fields populated across phases) |
| `src/pro_context/protocols.py` | `CacheProtocol`, `FetcherProtocol` stubs |
| `src/pro_context/server.py` | `FastMCP("pro-context")`, lifespan stub, `main()` entrypoint |
| `pro-context.example.yaml` | Example config with all fields and comments (committed; `pro-context.yaml` is gitignored) |

**Verification**:
```bash
uv run pro-context          # Starts, no crash, awaits stdio input
echo '{}' | uv run pro-context  # Responds without crash
```

---

### Phase 1: Registry & Resolution

**Goal**: `resolve-library` tool is fully functional. Registry loads from bundled snapshot. Fuzzy matching works.

**Files to create/update**:

| File | What to implement |
|------|------------------|
| `src/pro_context/registry.py` | `load_registry()`, `build_indexes()`, `RegistryIndexes` |
| `src/pro_context/resolver.py` | `normalise_query()`, `resolve_library()` (all 5 steps) |
| `src/pro_context/models/registry.py` | Add `LibraryMatch` |
| `src/pro_context/models/tools.py` | `ResolveLibraryInput`, `ResolveLibraryOutput` |
| `src/pro_context/models/__init__.py` | Re-export `LibraryMatch`, `ResolveLibrary*` |
| `src/pro_context/tools/__init__.py` | Empty |
| `src/pro_context/tools/resolve_library.py` | `handle(query, state) -> dict` |
| `src/pro_context/state.py` | Add `indexes`, `registry_version` fields |
| `src/pro_context/server.py` | Register `resolve_library` tool, initialise registry in lifespan |
| `src/pro_context/data/known-libraries.json` | Bundled registry snapshot (download latest from GitHub Pages) |
| `tests/unit/test_resolver.py` | See testing section |

**Key behaviours to verify**:
- `"langchain-openai"` → resolves via package name to `"langchain"`
- `"langchain[openai]>=0.3"` → normalised then resolves
- `"LangChain"` → lowercase normalised, resolves via ID
- `"langchan"` → fuzzy match to `"langchain"` with relevance < 1.0
- `"xyzzy-nonexistent"` → empty matches list, no error

---

### Phase 2: Fetcher & Cache

**Goal**: `get-library-docs` tool is fully functional. SQLite cache works with stale-while-revalidate.

**Files to create/update**:

| File | What to implement |
|------|------------------|
| `src/pro_context/fetcher.py` | `Fetcher` class: `build_http_client()`, `build_allowlist()`, `is_url_allowed()`, `fetch()`, `fetch_text()` |
| `src/pro_context/cache.py` | `Cache` class: `init_db()`, `get_toc()`, `set_toc()`, `get_page()`, `set_page()`, `cleanup_expired()` |
| `src/pro_context/protocols.py` | Fill out `CacheProtocol` and `FetcherProtocol` with full method signatures |
| `src/pro_context/models/cache.py` | `TocCacheEntry`, `PageCacheEntry` |
| `src/pro_context/models/tools.py` | Add `GetLibraryDocsInput`, `GetLibraryDocsOutput` |
| `src/pro_context/models/__init__.py` | Re-export new models |
| `src/pro_context/tools/get_library_docs.py` | `handle(library_id, state) -> dict` |
| `src/pro_context/state.py` | Add `http_client`, `cache`, `fetcher`, `allowlist` fields |
| `src/pro_context/server.py` | Register `get_library_docs` tool, initialise `Cache` and `Fetcher` in lifespan |
| `tests/unit/test_fetcher.py` | See testing section |
| `tests/unit/test_cache.py` | See testing section |

**Key behaviours to verify**:
- First call fetches from network, stores in cache, returns content
- Second call returns from cache, no network request made
- Stale entry (TTL expired) is returned immediately, background refresh triggered
- Cache read failure (`aiosqlite.Error`): treated as cache miss, falls back to network fetch, returns content with `cached: false`
- Cache write failure (`aiosqlite.Error`): fetched content still returned normally, error logged
- SSRF: private IP URL raises `URL_NOT_ALLOWED`
- SSRF: redirect to non-allowlisted domain raises `URL_NOT_ALLOWED`
- Unknown `libraryId` raises `LIBRARY_NOT_FOUND`

---

### Phase 3: Page Reading & Parser

**Goal**: `read-page` tool is fully functional. Heading parser handles code blocks, line number tracking, and anchor deduplication correctly.

**Files to create/update**:

| File | What to implement |
|------|------------------|
| `src/pro_context/parser.py` | `parse_headings()`, `_make_anchor()` |
| `src/pro_context/models/tools.py` | Add `Heading`, `ReadPageInput`, `ReadPageOutput` |
| `src/pro_context/models/__init__.py` | Re-export new models |
| `src/pro_context/tools/read_page.py` | `handle(url, state) -> dict` |
| `src/pro_context/server.py` | Register `read_page` tool |
| `tests/unit/test_parser.py` | See testing section |
| `tests/integration/test_tools.py` | End-to-end tool call tests for all three tools |

**Key behaviours to verify**:
- `#>` inside code block is not detected as heading
- `# comment` inside code block is not detected as heading
- Heading at any level (H1–H4) outside code block is detected with correct `line` number
- Repeated heading titles produce deduplicated anchors (`browser-mode`, `browser-mode-2`, `browser-mode-3`)
- Page is cached on first fetch; subsequent calls are served from cache without re-fetch

---

### Phase 4: HTTP Transport

**Goal**: Server runs in HTTP mode with bearer key authentication, Origin validation, and protocol version checking.

**Files to create/update**:

| File | What to implement |
|------|------------------|
| `src/pro_context/transport.py` | `MCPSecurityMiddleware` (bearer key auth, Origin validation, protocol version check) |
| `src/pro_context/config.py` | Add `auth_key` field to `ServerSettings` |
| `src/pro_context/server.py` | `run_http_server()`: auto-generate key if not configured, log key to stderr, attach middleware, start uvicorn |
| `tests/integration/test_tools.py` | Add HTTP mode transport tests |

**Key behaviours to verify**:
- POST to `/mcp` with valid bearer key → 200
- POST to `/mcp` with missing `Authorization` header → 401
- POST to `/mcp` with incorrect bearer key → 401
- POST to `/mcp` with valid origin → 200
- POST to `/mcp` with non-localhost origin → 403
- POST to `/mcp` with unknown `MCP-Protocol-Version` header → 400
- `transport = "http"` in config starts uvicorn, `transport = "stdio"` starts stdio mode
- No `auth_key` in config → key auto-generated at startup, logged to stderr

---

### Phase 5: Registry Updates & Polish

**Goal**: Registry updates automatically in the background. Cleanup job runs. Package is installable via `uvx`. Release pipeline is automated.

**Files to create/update**:

| File | What to implement |
|------|------------------|
| `src/pro_context/registry.py` | `check_for_registry_update()`, `save_registry_to_disk()` |
| `src/pro_context/cache.py` | `cleanup_expired()` called on startup and every 6 hours |
| `src/pro_context/server.py` | Spawn background tasks in lifespan |
| `CHANGELOG.md` | Initial entry for v0.1.0; [Keep a Changelog](https://keepachangelog.com) format |
| `.github/workflows/ci.yml` | Full CI pipeline (see Section 6) |
| `.github/workflows/release.yml` | Release pipeline: version bump, changelog update, PyPI publish (see Section 6) |
| `pyproject.toml` | Add `python-semantic-release` to dev deps, add `[tool.semantic_release]` config |

**Key behaviours to verify**:
- Registry metadata fetch happens at startup (mocked in test)
- If remote version matches local: no download
- If remote version differs: download, validate checksum, rebuild indexes
- Checksum mismatch: log warning, keep existing registry
- `uvx pro-context` installs and runs from PyPI (manual verification)
- `CHANGELOG.md` is present and follows Keep a Changelog format

---

## 5. Testing Strategy

**Framework**: `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"`).

**HTTP mocking**: `respx` for mocking `httpx` requests. Never make real network calls in tests.

**Database**: Each test that touches SQLite uses an in-memory database (`aiosqlite.connect(":memory:")`), created fresh per test via a fixture. No shared database state between tests.

**Directory split**:

- `tests/unit/` — Tests for individual internal modules (resolver, parser, fetcher, cache). No tool pipeline, no FastMCP. Run alone for fast feedback (`pytest tests/unit`).
- `tests/integration/` — Full tool pipeline tests. Uses a complete `AppState` with mocked HTTP and in-memory SQLite.

**Contract tests vs. implementation tests**:

`tests/integration/test_tools.py` contains the **contract tests** — they call tools through the full pipeline and assert on observable output shape, exactly as an MCP client would. A complete internal rewrite (e.g., swapping the cache backend, changing the resolver algorithm) must not break any integration test. These are the tests that matter for compatibility guarantees.

`tests/unit/` contains **implementation tests** — they call internal functions directly and verify algorithmic correctness (normalisation edge cases, parser rules, SSRF logic). These tests are permitted to break during refactoring, because they test the implementation, not the contract. Their purpose is fast feedback during development, not stability guarantees. Do not treat a failing unit test as a sign the public API is broken — check the integration tests for that.

**Top-level fixtures** (`tests/conftest.py`):

```python
import pytest
from pro_context.models.registry import RegistryEntry, RegistryPackages
from pro_context.registry import build_indexes

@pytest.fixture
def sample_entries() -> list[RegistryEntry]:
    return [
        RegistryEntry(
            id="langchain",
            name="LangChain",
            languages=["python"],
            packages=RegistryPackages(pypi=["langchain", "langchain-openai", "langchain-core"]),
            aliases=["lang-chain"],
            llms_txt_url="https://docs.langchain.com/llms.txt",
        ),
        RegistryEntry(
            id="pydantic",
            name="Pydantic",
            languages=["python"],
            packages=RegistryPackages(pypi=["pydantic", "pydantic-settings"]),
            aliases=[],
            llms_txt_url="https://docs.pydantic.dev/latest/llms.txt",
        ),
    ]

@pytest.fixture
def indexes(sample_entries):
    return build_indexes(sample_entries)
```

**Unit fixtures** (`tests/unit/conftest.py`):

```python
import pytest
import aiosqlite
from pro_context.cache import Cache
from pro_context.config import Settings

@pytest.fixture
def settings() -> Settings:
    return Settings()  # All defaults

@pytest.fixture
async def cache():
    async with aiosqlite.connect(":memory:") as db:
        c = Cache(db)
        await c.init_db()
        yield c
```

**Integration fixtures** (`tests/integration/conftest.py`):

```python
import pytest
import respx
import httpx
import aiosqlite
from pro_context.state import AppState
from pro_context.cache import Cache
from pro_context.fetcher import Fetcher, build_allowlist
from pro_context.config import Settings

@pytest.fixture
async def app_state(indexes, sample_entries):
    """Full AppState with mocked HTTP and in-memory SQLite."""
    async with aiosqlite.connect(":memory:") as db:
        cache = Cache(db)
        await cache.init_db()

        async with httpx.AsyncClient() as client:
            fetcher = Fetcher(client)
            allowlist = build_allowlist(sample_entries)
            state = AppState(
                settings=Settings(),
                indexes=indexes,
                registry_version="test",
                http_client=client,
                cache=cache,
                fetcher=fetcher,
                allowlist=allowlist,
            )
            yield state
```

**What each test file covers**:

`tests/unit/test_resolver.py`
- Query normalisation: extras, version specs, case, whitespace
- Step 1: exact package name match
- Step 2: exact ID match
- Step 3: alias match
- Step 4: fuzzy match (typos, score threshold)
- Step 5: no match → empty list
- Edge case: pip extras (`"langchain[openai]"`)
- Edge case: monorepo packages (`"langchain-core"` → `"langchain"`)

`tests/unit/test_fetcher.py`
- SSRF: private IPv4 ranges blocked
- SSRF: private IPv6 blocked
- SSRF: redirect to non-allowlisted domain blocked
- SSRF: redirect to private IP blocked
- Successful fetch: returns content
- 404 response: raises `PAGE_NOT_FOUND`
- Network error: raises `PAGE_FETCH_FAILED`
- Too many redirects: raises `PAGE_FETCH_FAILED`

`tests/unit/test_cache.py`
- Fresh entry: returned, `stale=False`
- Expired entry: returned with `stale=True`
- Missing entry: returns `None`
- Write then read: round-trip correctness
- Cleanup: entries beyond TTL + 7 days are deleted
- Read failure (`aiosqlite.Error` raised by DB): returns `None`, does not raise
- Write failure (`aiosqlite.Error` raised by DB): returns normally, does not raise

`tests/unit/test_parser.py`
- Heading inside fenced ` ``` ` block: not detected
- Heading inside `~~~` block: not detected
- `#>` comment in code block: not detected
- H1–H4 outside code blocks: all detected with correct level
- H5+ ignored
- Anchor generation: lowercase, slugified, special chars removed
- Anchor deduplication: `browser-mode`, `browser-mode-2`, `browser-mode-3`
- Line numbers: each heading records the correct 1-based line number from the source content

`tests/integration/test_tools.py`
- `resolve_library`: full call, correct output shape
- `get_library_docs`: cache miss path (mocked HTTP), cache hit path
- `get_library_docs`: unknown library raises `LIBRARY_NOT_FOUND`
- `read_page`: cache miss path (mocked HTTP), cache hit path
- `read_page`: URL not in allowlist raises `URL_NOT_ALLOWED`
- HTTP transport: missing bearer key → 401
- HTTP transport: incorrect bearer key → 401
- HTTP transport: valid bearer key → 200
- HTTP transport: non-localhost origin → 403
- HTTP transport: unknown protocol version → 400
- HTTP transport: no `auth_key` in config → key auto-generated, logged to stderr

**Coverage target**: 90% line coverage. Branches covering network errors and cache misses are explicitly tested via mocking — not left to chance.

---

## 6. CI/CD

### Commit Message Convention

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>[optional scope]: <description>

[optional body]

[optional footer: BREAKING CHANGE: <description>]
```

Common types: `feat` (new feature), `fix` (bug fix), `docs`, `refactor`, `test`, `chore`. Breaking changes must include `BREAKING CHANGE:` in the footer — this is what drives major version bumps and ensures the changelog correctly marks breaking changes.

### ci.yml — Test Pipeline

Runs on every push and pull request to `main`.

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Lint
        run: uv run ruff check src/ tests/

      - name: Format check
        run: uv run ruff format --check src/ tests/

      - name: Type check
        run: uv run pyright src/

      - name: Unit tests
        run: uv run pytest tests/unit/ --cov=src/pro_context --cov-report=term-missing

      - name: Integration tests
        run: uv run pytest tests/integration/ --cov=src/pro_context --cov-append --cov-report=term-missing

      - name: Coverage gate
        run: uv run pytest tests/ --cov=src/pro_context --cov-fail-under=90
```

**Unit and integration tests as separate steps**: Fails fast — a broken unit test is caught before running the slower integration suite. Combined coverage is reported at the end.

### release.yml — Release Pipeline

Runs only on pushes to `main` after the test pipeline passes. Uses `python-semantic-release` to automate version bumping, changelog generation, and PyPI publishing based on Conventional Commit history.

```yaml
# .github/workflows/release.yml
name: Release

on:
  workflow_run:
    workflows: [CI]        # Triggers only after the CI workflow completes
    types: [completed]
    branches: [main]

jobs:
  release:
    runs-on: ubuntu-latest
    if: github.event.workflow_run.conclusion == 'success'  # Skip if CI failed
    concurrency: release   # Prevents concurrent releases
    permissions:
      id-token: write      # Required for PyPI trusted publishing (OIDC) and SLSA attestation
      contents: write      # Required to push tags and update CHANGELOG.md
      attestations: write  # Required for SLSA provenance attestation

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # Full history required for semantic-release

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: uv run semantic-release publish

      - name: Attest build provenance
        uses: actions/attest-build-provenance@v1
        with:
          subject-path: dist/
```

`semantic-release publish` inspects commit history since the last tag, determines the next version (patch/minor/major), updates `CHANGELOG.md`, bumps `__version__` in `src/pro_context/__init__.py`, creates a Git tag, builds the wheel, and publishes to PyPI. If no releasable commits exist (e.g., only `docs:` or `chore:` commits), it exits without publishing.

`actions/attest-build-provenance` generates a signed SLSA provenance attestation — a cryptographic record proving which source commit produced which artifact, via which build pipeline. This is attached to the GitHub release and is verifiable via `gh attestation verify`. Enterprise consumers increasingly require provenance before adopting a dependency.

**Why `workflow_run` instead of `needs`**: `needs` only works between jobs in the same workflow file. To gate the release on a passing CI run from a separate `ci.yml`, `workflow_run` is required. The `if: conclusion == 'success'` condition ensures the release job is skipped entirely when CI fails.

`python-semantic-release` and its `[tool.semantic_release]` config in `pyproject.toml` are added in Phase 5 — the release pipeline is not needed until the project is ready to publish.

```toml
# Added to pyproject.toml in Phase 5:

[project.optional-dependencies]
dev = [
    ...
    "python-semantic-release>=9.0.0,<10.0.0",  # Changelog generation + PyPI publishing
]

[tool.semantic_release]
version_variables = ["src/pro_context/__init__.py:__version__"]
changelog_file = "CHANGELOG.md"
build_command = "uv build"
```

---

## 7. Local Development Setup

```bash
# 1. Clone and install
git clone https://github.com/tewatia/pro-context.git
cd pro-context
uv sync --extra dev

# 2. Run in stdio mode (default)
uv run pro-context

# 3. Run in HTTP mode
PRO_CONTEXT__SERVER__TRANSPORT=http uv run pro-context
# or: copy pro-context.example.yaml → pro-context.yaml, set transport: http

# 4. Run all tests
uv run pytest

# 5. Run only unit tests (fast feedback during development)
uv run pytest tests/unit

# 6. Run with coverage
uv run pytest --cov=src/pro_context --cov-report=html
open htmlcov/index.html

# 7. Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

**Development config** (copy `pro-context.example.yaml` to `pro-context.yaml` and adjust):

```yaml
server:
  transport: http
  host: "127.0.0.1"
  port: 8080

logging:
  level: DEBUG
  format: text     # Human-readable for local dev
```
