# ProContext: Implementation Guide

> **Document**: 03-implementation-guide.md
> **Status**: Draft v2
> **Last Updated**: 2026-03-08
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
- [4. Module Acceptance Criteria](#4-module-acceptance-criteria)
  - [4.1 Resolver](#41-resolver)
  - [4.2 Fetcher & Cache](#42-fetcher--cache)
  - [4.3 Parser](#43-parser)
  - [4.4 Search](#44-search)
  - [4.5 HTTP Transport](#45-http-transport)
  - [4.6 Registry Updates](#46-registry-updates)
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
procontext/
├── pyproject.toml
├── CHANGELOG.md                      # Keep a Changelog format; updated on every release
├── procontext.example.yaml          # Example config (committed); copy to procontext.yaml for local use
├── src/
│   └── procontext/
│       ├── __init__.py               # package __version__ (resolved from installed metadata)
│       ├── py.typed                  # PEP 561 marker — declares this package is typed
│       ├── mcp/                      # MCP server wiring
│       │   ├── __init__.py
│       │   ├── server.py             # FastMCP instance and tool registrations
│       │   ├── lifespan.py           # asynccontextmanager: resource creation/teardown, registry_paths()
│       │   └── startup.py            # main(), CLI entry point, registry bootstrap
│       ├── state.py                  # AppState dataclass
│       ├── config.py                 # Settings via pydantic-settings + YAML
│       ├── errors.py                 # ErrorCode, ProContextError
│       ├── protocols.py              # CacheProtocol, FetcherProtocol (typing.Protocol)
│       ├── logging_config.py         # structlog processor chain configuration
│       ├── models/
│       │   ├── __init__.py           # Re-exports all public models
│       │   ├── registry.py           # RegistryEntry, RegistryPackages, LibraryMatch
│       │   ├── cache.py              # PageCacheEntry
│       │   └── tools.py              # All tool I/O models (input validation + output serialisation)
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── resolve_library.py    # Business logic for resolve_library
│       │   ├── read_page.py          # Business logic for read_page
│       │   ├── search_page.py        # Business logic for search_page
│       │   └── _shared.py            # Shared helper: fetch_or_cached_page (cache-check → fetch → cache-write → stale-refresh)
│       ├── registry.py               # Registry loading, index building, disk persistence, update check
│       ├── resolver.py               # 5-step resolution algorithm, fuzzy matching
│       ├── fetcher.py                # HTTP client, SSRF validation, redirect handling
│       ├── cache.py                  # SQLite cache: page_cache, stale-while-revalidate
│       ├── schedulers.py             # Background coroutines: registry update scheduler, cache cleanup scheduler
│       ├── parser.py                 # Outline parser, code block suppression, line number tracking
│       ├── search.py                 # Pattern compilation (build_matcher) and line scanning (search_lines)
│       ├── transport.py              # MCPSecurityMiddleware for HTTP mode
│       └── data/
│           └── __init__.py           # Package marker (data/ has no runtime-loaded files)
├── tests/
│   ├── conftest.py                   # Top-level fixtures shared across all tests
│   ├── unit/
│   │   ├── conftest.py               # Unit-specific fixtures (no I/O)
│   │   ├── test_resolver.py          # resolve_library: normalisation, all 5 steps, edge cases
│   │   ├── test_fetcher.py           # SSRF validation, redirect handling, error cases
│   │   ├── test_cache.py             # Cache read/write, TTL expiry, stale-while-revalidate
│   │   ├── test_parser.py            # Heading detection, code block suppression, section extraction
│   │   └── test_search.py            # Pattern compilation, line scanning, smart case, pagination
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

| Layer              | Modules                                              | Rule                                                                                   |
| ------------------ | ---------------------------------------------------- | -------------------------------------------------------------------------------------- |
| **Entrypoint**     | `mcp/server.py`, `mcp/lifespan.py`, `mcp/startup.py` | Tool registrations, resource lifecycle, CLI entry. No business logic.                 |
| **Tools**          | `tools/*.py`                                         | One file per tool. Receives `AppState`, returns output dict. Raises `ProContextError`. |
| **Services**       | `resolver.py`, `fetcher.py`, `cache.py`, `parser.py`, `search.py` | Pure business logic. No MCP imports. Typed against protocols, not concrete classes.    |
| **Infrastructure** | `registry.py`, `config.py`, `transport.py`, `schedulers.py` | Setup and wiring. Run once at startup; schedulers run as long-lived background coroutines. |
| **Shared**         | `models/`, `errors.py`, `protocols.py`, `state.py`   | No dependencies on other layers. Imported freely.                                      |

**Adding a new tool**: Create `tools/new_tool.py`, register it in `mcp/server.py`. No other files change.

**Swapping the cache backend**: Provide a new class implementing `CacheProtocol`, inject it into `AppState`. No tool code changes.

---

## 2. Dependencies

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/procontext"]

[project]
name = "procontext"
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
    "platformdirs>=4.0.0,<5.0.0",           # Platform-aware config/data directories
    "structlog>=24.1.0,<26.0.0",            # Structured logging
    "uvicorn>=0.34.0,<1.0.0",               # ASGI server for HTTP transport
]

[project.scripts]
procontext = "procontext.mcp.startup:main"

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=1.0.0",
    "pytest-mock>=3.12.0",
    "pytest-cov>=7.0.0",                        # Coverage measurement and enforcement
    "respx>=0.21.0",                            # httpx request mocking
    "ruff>=0.11.0",
    "pyright>=1.1.400",                         # Type checking (also run in CI)
    "pip-audit>=2.7.0,<3.0.0",                 # Dependency vulnerability scanning
    "python-semantic-release>=9.0.0,<10.0.0",  # Changelog generation + PyPI publishing
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

**`py.typed`**: An empty file at `src/procontext/py.typed`. Its presence tells pyright and mypy that this package ships type annotations and they should be honoured. Without it, type checkers silently ignore the package's types when it is imported.

**`pyright` in dev extras**: Keeps the type checker version pinned and consistent between local dev and CI.

**`testpaths`**: Prevents pytest from discovering tests in unexpected locations (e.g., inside `src/`) when run from the project root.

**Version pinning**: Minor version upper bounds (`<2.0.0`) on all dependencies. Tighten to patch bounds only if a dependency has a documented history of breaking minor releases.

**Version floors**: Since this is a new project with no legacy consumers, version floors should track reasonably close to the latest stable release at the time of writing. There is no reason to support old versions that nobody is using yet. Review and bump floors at the start of each implementation phase — stale floors accumulate silently and can mask behavioural differences between the version you test against and the version the floor permits.

**Dependency footprint**: ProContext has 10 runtime dependencies. Each is justified by a capability that would require significantly more code to replicate correctly (async HTTP with SSRF-safe redirect control, async SQLite, fuzzy string matching, structured logging, validated settings). Zero-dependency is a virtue but not at the cost of correctness or maintainability. Before adding any new runtime dependency, verify that the same capability cannot be covered by an existing dependency or the Python standard library.

**License compatibility**: All runtime dependencies are compatible with GPL-3.0. Verified at last review (2026-02-24):

| Package             | License           | Notes                                            |
| ------------------- | ----------------- | ------------------------------------------------ |
| `mcp`               | MIT               | Official MCP Python SDK by Anthropic             |
| `httpx`             | BSD-3-Clause      |                                                  |
| `aiosqlite`         | MIT               |                                                  |
| `pydantic`          | MIT               |                                                  |
| `pydantic-settings` | MIT               |                                                  |
| `pyyaml`            | MIT               |                                                  |
| `rapidfuzz`         | MIT               |                                                  |
| `platformdirs`      | MIT               | Platform-aware config/data directories           |
| `structlog`         | MIT OR Apache-2.0 | Dual-licensed; either is compatible with GPL-3.0 |
| `uvicorn`           | BSD-3-Clause      |                                                  |

Re-verify this table whenever a dependency is added or its major version is bumped. MIT and BSD-3-Clause are permissive and always compatible with GPL-3.0. Apache-2.0 is compatible with GPL-3.0 (but not GPL-2.0 — not a concern here).

---

## 3. Coding Conventions

### 3.1 General Rules

**Async throughout.** Every I/O operation (SQLite, HTTP) is async. Tool handlers are `async def`. The only synchronous code is in-memory computation (index lookups, string normalisation, heading parsing).

**Type hints on every function signature.** Return types included. Use `X | None` union syntax (Python 3.10+), not `Optional[X]`.

```python
# Correct
async def get_page(self, url_hash: str) -> PageCacheEntry | None: ...

# Incorrect
async def get_page(self, url_hash: str) -> Optional[PageCacheEntry]: ...
```

**Pydantic at all external boundaries.** Tool inputs are validated via Pydantic models before any processing. Registry JSON is parsed into `RegistryEntry` models on load. Never pass raw dicts between modules — use typed models.

**Platform-aware data paths.** All filesystem defaults use `platformdirs` — never hardcode Unix paths like `~/.local/share/`. Registry files are resolved via `Settings.data_dir` (default `platformdirs.user_data_dir("procontext")`). Cache uses `Settings.cache.db_path` (default `platformdirs.user_data_dir("procontext")/cache.db`), and remains independently configurable.

### 3.2 Protocol Interfaces

Swappable components (`Cache`, `Fetcher`) are typed against `typing.Protocol` interfaces defined in `protocols.py`. Tool handlers and `AppState` reference the protocol, not the concrete class. This has two benefits:

1. **Tests** can use lightweight in-memory implementations without instantiating SQLite or real HTTP clients.
2. **Future backends** (Redis cache, enterprise auth-aware fetcher) can be swapped by injecting a different implementation — no tool code changes.

```python
# protocols.py
from typing import Protocol
from procontext.models import PageCacheEntry

class CacheProtocol(Protocol):
    async def get_page(self, url_hash: str) -> PageCacheEntry | None: ...
    async def set_page(
        self,
        url: str,
        url_hash: str,
        content: str,
        outline: str,
        ttl_hours: int,
        *,
        discovered_domains: frozenset[str] = frozenset(),
    ) -> None: ...
    async def load_discovered_domains(self) -> frozenset[str]: ...
    async def cleanup_if_due(self, interval_hours: int) -> None: ...
    async def cleanup_expired(self) -> None: ...

class FetcherProtocol(Protocol):
    async def fetch(self, url: str, allowlist: frozenset[str]) -> str: ...
```

The concrete `Cache` (SQLite) and `Fetcher` (httpx) classes implement these protocols implicitly — no `class Cache(CacheProtocol)` inheritance needed. Python's structural subtyping handles it.

### 3.3 AppState and Dependency Injection

All shared state lives in `AppState` (`state.py`), instantiated once at startup and injected into every tool call. This makes tests straightforward — pass a test `AppState` with mock implementations.

```python
# state.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
import httpx

if TYPE_CHECKING:
    from procontext.config import Settings
    from procontext.models.registry import RegistryIndexes
    from procontext.protocols import CacheProtocol, FetcherProtocol

@dataclass
class AppState:
    # Core
    settings: Settings

    # Registry & Resolution
    indexes: RegistryIndexes
    registry_version: str = ""
    registry_path: Path | None = None           # Path to known-libraries.json on disk
    registry_state_path: Path | None = None     # Path to registry-state.json on disk

    # Fetcher & Cache
    http_client: httpx.AsyncClient | None = None
    cache: CacheProtocol | None = None          # Typed as protocol, not concrete Cache
    fetcher: FetcherProtocol | None = None      # Typed as protocol, not concrete Fetcher
    allowlist: frozenset[str] = field(default_factory=frozenset)
```

`AppState` is passed into the server via FastMCP's lifespan context and flows into tool handlers through the MCP `Context` object:

```python
# mcp/lifespan.py + mcp/server.py
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context

@asynccontextmanager
async def lifespan(server: FastMCP):
    state = await _create_app_state()
    yield state                    # Available as ctx.request_context.lifespan_context
    await state.http_client.aclose()

mcp = FastMCP("procontext", lifespan=lifespan)

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

**Raise `ProContextError`, never return error dicts.** Tool handlers raise `ProContextError`. `mcp/server.py` catches it and serialises it into the MCP error response. Business logic modules never return `{"error": ...}` dicts.

```python
# Correct
if response.status_code == 404:
    raise ProContextError(
        code=ErrorCode.PAGE_NOT_FOUND,
        message=f"Page not found: {url}",
        suggestion="Check the URL is correct. Use resolve_library to find valid documentation URLs.",
        recoverable=False,
    )

# Incorrect
if response.status_code == 404:
    return {"error": {"code": "PAGE_NOT_FOUND", ...}}
```

### 3.5 Logging

**Bind log context at the start of each handler.** Use `structlog.get_logger().bind(...)` to attach the tool name and key inputs to every log line in a handler, without passing a logger argument through every function call.

```python
# tools/search_page.py
import structlog

async def handle(url: str, query: str, state: AppState) -> dict:
    url_hash = sha256_hex(url)
    log = structlog.get_logger().bind(tool="search_page", url_hash=url_hash)
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

## 4. Module Acceptance Criteria

Each subsection defines the expected behaviours for a module. These serve as the verification checklist for code review and testing — a module is complete when every listed behaviour has a passing test.

---

### 4.1 Resolver

**Modules**: `resolver.py`, `registry.py`, `tools/resolve_library.py`

**Expected behaviours**:

- `"langchain-openai"` → resolves via package name to `"langchain"`
- `"langchain[openai]>=0.3"` → normalised then resolves
- `"LangChain"` → lowercase normalised, resolves via ID
- `"langchan"` → fuzzy match to `"langchain"` with relevance < 1.0
- `"xyzzy-nonexistent"` → empty matches list, no error

---

### 4.2 Fetcher & Cache

**Modules**: `fetcher.py`, `cache.py`, `tools/read_page.py`, `tools/_shared.py`

**Expected behaviours**:

- First call fetches from network, stores in cache, returns content
- Second call returns from cache, no network request made
- Stale entry (TTL expired) is returned immediately, background refresh triggered
- Cache read failure (`aiosqlite.Error`): treated as cache miss, falls back to network fetch, returns content with `cached: false`
- Cache write failure (`aiosqlite.Error`): fetched content still returned normally, error logged
- SSRF: private IP URL raises `URL_NOT_ALLOWED`
- SSRF: redirect to non-allowlisted domain raises `URL_NOT_ALLOWED`
- Page is cached on first fetch; subsequent calls with different offsets are served from cache without re-fetch
- `offset` and `limit` correctly window the content
- `outline` always reflects the full page regardless of offset/limit or `view`

---

### 4.3 Parser

**Module**: `parser.py`

**Expected behaviours**:

- H1–H6 headings detected with correct 1-based line numbers
- Blockquote headings (`> ## Section`) are captured
- Fence opener/closer lines are emitted so the agent knows where code blocks start/end
- Headings inside code blocks are captured as-is (agent infers context from surrounding fence lines)
- 4-space indented lines are not treated as fence openers

---

### 4.4 Search

**Modules**: `search.py`, `tools/search_page.py`

**Expected behaviours**:

- Literal search returns correct matching lines with 1-based line numbers
- Regex search compiles and matches; invalid regex raises `INVALID_INPUT`
- Smart case: all-lowercase query → case-insensitive; mixed/upper → case-sensitive
- `whole_word: true` wraps pattern in `\b...\b`
- Pagination: `offset` skips lines, `max_results` limits output, `has_more`/`next_offset` enable continuation
- Outline is returned alongside matches for structural context
- Page fetch uses the shared `fetch_or_cached_page` helper (same cache as `read_page`)

---

### 4.5 HTTP Transport

**Modules**: `transport.py`, `mcp/startup.py`

**Expected behaviours**:

- `auth_enabled=true` + explicit `auth_key` + valid bearer key → 200
- `auth_enabled=true` + explicit `auth_key` + missing `Authorization` header → 401
- `auth_enabled=true` + explicit `auth_key` + incorrect bearer key → 401
- `auth_enabled=true` + empty `auth_key` → key auto-generated at startup and logged
- `auth_enabled=false` → auth disabled; requests without `Authorization` can proceed
- `auth_enabled=false` → startup warning is logged
- POST to `/mcp` with valid origin → 200
- POST to `/mcp` with non-loopback origin → 403
- POST to `/mcp` with unknown `MCP-Protocol-Version` header → 400
- `transport = "http"` in config starts uvicorn, `transport = "stdio"` starts stdio mode

---

### 4.6 Registry Updates

**Modules**: `registry.py`, `schedulers.py`, `mcp/lifespan.py`

**Expected behaviours**:

- Registry metadata fetch happens at startup (mocked in test)
- If remote version matches local: no download
- If remote version differs: download, validate checksum, rebuild indexes
- Checksum mismatch: log warning, keep existing registry
- Successful update persists both `known-libraries.json` and `registry-state.json`
- Local registry pair (`known-libraries.json` + `registry-state.json`) is validated at startup; missing/invalid pair triggers auto-setup (blocking network fetch); if that also fails, server exits with actionable error
- `save_registry_to_disk()` uses temp files + fsync + atomic replace (no partially written destination files)
- Simulated interrupted write leaves startup in a safe state (either previous valid pair or clean auto-setup attempt)
- HTTP mode scheduler: successful checks run every 24 hours
- HTTP mode scheduler: transient failures use exponential backoff + jitter (1 minute to 60 minutes cap)
- HTTP mode scheduler: after 8 consecutive transient failures, counter and backoff reset, cadence returns to 24 hours; next round gets a fresh set of fast-retry attempts
- HTTP mode scheduler: semantic failures (checksum/metadata/schema) do not fast-retry and return to 24-hour cadence

---

## 5. Testing Strategy

**Framework**: `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"` — all async test functions run without an explicit decorator). Async test helpers should use anyio primitives (`anyio.sleep`, `anyio.Event`, `anyio.fail_after`) rather than asyncio equivalents. See Rule 19 in `docs/coding-guidelines.md`.

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
from procontext.models.registry import RegistryEntry, RegistryPackages
from procontext.registry import build_indexes

@pytest.fixture
def sample_entries() -> list[RegistryEntry]:
    return [
        RegistryEntry(
            id="langchain",
            name="LangChain",
            description="Framework for building LLM-powered applications.",
            languages=["python"],
            packages=RegistryPackages(pypi=["langchain", "langchain-openai", "langchain-core"]),
            aliases=["lang-chain"],
            llms_txt_url="https://docs.langchain.com/llms.txt",
        ),
        RegistryEntry(
            id="pydantic",
            name="Pydantic",
            description="Data validation using Python type annotations.",
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
from procontext.cache import Cache
from procontext.config import Settings

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
from procontext.state import AppState
from procontext.cache import Cache
from procontext.fetcher import Fetcher, build_allowlist
from procontext.config import Settings

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
- Too many redirects: raises `TOO_MANY_REDIRECTS`

`tests/unit/test_cache.py`

- Fresh entry: returned, `stale=False`
- Expired entry: returned with `stale=True`
- Missing entry: returns `None`
- Write then read: round-trip correctness
- Cleanup: entries beyond TTL + 7 days are deleted
- Read failure (`aiosqlite.Error` raised by DB): returns `None`, does not raise
- Write failure (`aiosqlite.Error` raised by DB): returns normally, does not raise

`tests/unit/test_parser.py`

- H1–H6 headings detected with correct 1-based line numbers
- Blockquote headings (`> ## Section`) are captured; deeply nested (`>> ##`) are not
- Fence opener/closer lines emitted as-is
- Headings inside code blocks captured with original indentation
- 4-space indented lines not treated as fence openers
- Lines with 7+ hashes not captured
- BOM (`\ufeff`) on line 1 does not prevent heading detection

`tests/unit/test_search.py`

- Literal search: exact matches found, non-matches excluded
- Regex search: valid patterns match correctly
- Regex search: invalid pattern raises `re.error` (caught as `INVALID_INPUT` in handler)
- Smart case: all-lowercase query is case-insensitive; mixed-case query is case-sensitive
- `whole_word: true`: matches whole words only, not substrings
- Offset: lines before offset are skipped
- Pagination: `max_results` limits matches; `has_more` and `next_offset` are correct
- Edge case: no matches → empty list, `has_more=False`, `next_offset=None`
- Edge case: empty content → empty list

`tests/integration/test_tools.py`

- `resolve_library`: full call, correct output shape
- `read_page`: cache miss path (mocked HTTP), cache hit path
- `read_page`: URL not in allowlist raises `URL_NOT_ALLOWED`
- `search_page`: cache miss path (mocked HTTP), returns matches
- `search_page`: cache hit path (shared with read_page), returns matches
- `search_page`: invalid regex raises `INVALID_INPUT`
- HTTP transport: `auth_enabled=true`, explicit key, missing bearer key → 401
- HTTP transport: `auth_enabled=true`, explicit key, incorrect bearer key → 401
- HTTP transport: `auth_enabled=true`, explicit key, valid bearer key → 200
- HTTP transport: `auth_enabled=true`, empty key → key auto-generated and logged
- HTTP transport: `auth_enabled=false`, request without bearer key is allowed
- HTTP transport: `auth_enabled=false`, startup warning logged
- HTTP transport: non-loopback origin → 403
- HTTP transport: unknown protocol version → 400

**Coverage target**: 90% branch coverage (`branch = true` in `[tool.coverage.run]`). Branches covering network errors, cache misses, and config validation failures are explicitly tested via mocking — not left to chance.

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
        uses: astral-sh/setup-uv@v5

      - name: Install dependencies
        run: uv sync --dev

      - name: Lint
        run: uv run ruff check src/ tests/

      - name: Format check
        run: uv run ruff format --check src/ tests/

      - name: Type check
        run: uv run pyright src/

      - name: Tests with coverage
        run: |
          uv run pytest tests/ \
            --cov=src/procontext \
            --cov-report=term-missing \
            --cov-fail-under=90

      - name: Dependency audit
        run: uv run pip-audit
```

All steps run in sequence; a lint or type-check failure aborts the workflow before tests run, keeping the feedback loop fast.

### release.yml — Release Pipeline

Runs on manual trigger (`workflow_dispatch`) while the release process is still maturing. Maintainers should trigger it only after CI is green on `main`. Uses `python-semantic-release` to automate version bumping/tagging, then builds, attests, and publishes the artifacts.

```yaml
# .github/workflows/release.yml
name: Release

on:
  workflow_dispatch:

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      id-token: write # Required for PyPI trusted publishing (OIDC)
      contents: write # Required to push tags and update project version
      attestations: write # Required for SLSA provenance attestation

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0 # Full history required for semantic-release

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Install dependencies
        run: uv sync --dev

      - name: Bump version and push tag
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: uv run semantic-release version

      - name: Build package
        run: uv build

      - name: Attest build provenance
        uses: actions/attest-build-provenance@v1
        with:
          subject-path: dist/

      - name: Publish to PyPI
        run: uv publish --trusted-publishing always
```

`semantic-release version` inspects commit history since the last tag, determines the next version (patch/minor/major), updates the project version, creates a release commit, and pushes a Git tag. The workflow then builds the wheel/sdist with `uv build`, generates a provenance attestation for `dist/`, and publishes to PyPI with trusted publishing.

`actions/attest-build-provenance` generates a signed SLSA provenance attestation — a cryptographic record proving which source commit produced which artifact, via which build pipeline. This is attached to the GitHub release and is verifiable via `gh attestation verify`. Enterprise consumers increasingly require provenance before adopting a dependency.

`python-semantic-release` and its `[tool.semantic_release]` config in `pyproject.toml` are added once the release pipeline is needed — not required during initial development.

```toml
# Already present in pyproject.toml [dependency-groups].dev:
# "python-semantic-release>=9.0.0,<10.0.0",  # Changelog generation + PyPI publishing

[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
changelog_file = "CHANGELOG.md"
build_command = "uv build"
```

---

## 7. Local Development Setup

```bash
# 1. Clone and install
git clone https://github.com/procontexthq/procontext.git
cd procontext
uv sync --extra dev

# 2. Run in stdio mode (default)
uv run procontext

# 3. Run in HTTP mode
PROCONTEXT__SERVER__TRANSPORT=http uv run procontext
# or: copy procontext.example.yaml → procontext.yaml, set transport: http

# 4. Run all tests
uv run pytest

# 5. Run only unit tests (fast feedback during development)
uv run pytest tests/unit

# 6. Run with coverage
uv run pytest --cov=src/procontext --cov-report=html
open htmlcov/index.html

# 7. Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

**Development config** (copy `procontext.example.yaml` to `procontext.yaml` and adjust):

```yaml
server:
  transport: http
  host: "127.0.0.1"
  port: 8080

logging:
  level: DEBUG
  format: text # Human-readable for local dev
```
