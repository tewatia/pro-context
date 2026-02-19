# Pro-Context: Implementation Guide

> **Document**: 04-implementation-guide.md
> **Status**: Draft v2
> **Last Updated**: 2026-02-16
> **Depends on**: 03-technical-spec.md (v2)

---

## Table of Contents

- [1. Project Structure](#1-project-structure)
- [2. Dependency List](#2-dependency-list)
- [3. Coding Conventions](#3-coding-conventions)
  - [3.1 Naming](#31-naming)
  - [3.2 Error Handling Pattern](#32-error-handling-pattern)
  - [3.3 Test Pattern](#33-test-pattern)
  - [3.4 Module Pattern](#34-module-pattern)
  - [3.5 Async Pattern](#35-async-pattern)
- [4. Implementation Phases](#4-implementation-phases)
  - [Phase 1: Foundation](#phase-1-foundation)
  - [Phase 2: Core Documentation Pipeline](#phase-2-core-documentation-pipeline)
  - [Phase 3: Search & Navigation](#phase-3-search--navigation)
  - [Phase 4: HTTP Mode & Authentication](#phase-4-http-mode--authentication)
  - [Phase 5: Polish & Production Readiness](#phase-5-polish--production-readiness)
- [5. Testing Strategy](#5-testing-strategy)
  - [5.1 Test Pyramid](#51-test-pyramid)
  - [5.2 What to Test](#52-what-to-test)
  - [5.3 What NOT to Test](#53-what-not-to-test)
  - [5.4 Test Configuration](#54-test-configuration)
- [6. CI/CD and Docker Deployment](#6-cicd-and-docker-deployment)
  - [6.1 Dockerfile](#61-dockerfile)
  - [6.2 docker-compose.yml](#62-docker-composeyml)
  - [6.3 GitHub Actions CI](#63-github-actions-ci)
  - [6.4 Package.json Scripts](#64-packagejson-scripts)
- [7. Future Expansion Roadmap](#7-future-expansion-roadmap)
- [8. Quick Reference: MCP Client Configuration](#8-quick-reference-mcp-client-configuration)
- [9. Development Workflow](#9-development-workflow)

---

## 1. Project Structure

```
pro-context/
├── src/
│   └── pro_context/
│       ├── __init__.py
│       ├── __main__.py             # Entry point, server bootstrap, transport selection
│       ├── server.py               # MCP server setup, tool/resource/prompt registration
│       ├── config/
│       │   ├── __init__.py
│       │   ├── schema.py           # Pydantic config schema + defaults
│       │   └── loader.py           # Config file loading + env variable overrides
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── resolve_library.py  # resolve-library tool handler (discovery)
│       │   ├── get_library_info.py # get-library-info tool handler (TOC + metadata)
│       │   ├── get_docs.py         # get-docs tool handler (fast path, multi-library)
│       │   ├── search_docs.py      # search-docs tool handler (cross-library search)
│       │   └── read_page.py        # read-page tool handler (navigation, offset reading)
│       ├── resources/
│       │   ├── __init__.py
│       │   ├── health.py           # pro-context://health resource
│       │   └── session.py          # pro-context://session/resolved-libraries resource
│       ├── prompts/
│       │   ├── __init__.py
│       │   ├── migrate_code.py     # migrate-code prompt template
│       │   ├── debug_with_docs.py  # debug-with-docs prompt template
│       │   └── explain_api.py      # explain-api prompt template
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── types.py            # SourceAdapter ABC + RawPageContent type
│       │   ├── llms_txt.py         # llms.txt adapter implementation (Phase 1-3)
│       │   ├── github.py           # GitHub docs adapter (Phase 4+, deferred)
│       │   └── custom.py           # User-configured source adapter (Phase 4+, deferred)
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── api_keys.py         # API key creation, validation, hashing
│       │   ├── middleware.py       # HTTP auth middleware
│       │   └── admin_cli.py        # CLI entry point for key management
│       ├── cache/
│       │   ├── __init__.py
│       │   ├── memory.py           # TTL in-memory cache wrapper (cachetools)
│       │   ├── sqlite.py           # SQLite persistent cache operations (aiosqlite)
│       │   ├── page_cache.py       # Page cache with offset-based slice support
│       │   └── manager.py          # Two-tier cache orchestrator
│       ├── search/
│       │   ├── __init__.py
│       │   ├── chunker.py          # Markdown → DocChunk[] chunking logic
│       │   ├── bm25.py             # BM25 scoring algorithm
│       │   └── engine.py           # Search engine: index + query orchestration
│       ├── lib/
│       │   ├── __init__.py
│       │   ├── logger.py           # structlog setup with redaction
│       │   ├── errors.py           # ProContextError class + factory functions
│       │   ├── rate_limiter.py     # Token bucket rate limiter
│       │   ├── fuzzy_match.py      # Levenshtein distance fuzzy matching (rapidfuzz)
│       │   ├── tokens.py           # Token count estimation utilities
│       │   └── url_validator.py    # URL allowlist + SSRF prevention + dynamic expansion
│       └── registry/
│           ├── __init__.py
│           ├── types.py            # Library type + registry resolver interface
│           ├── known_libraries.py  # Curated library registry (Python initially)
│           └── pypi_resolver.py    # PyPI version/URL resolution
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── cache/
│   │   │   ├── test_memory.py
│   │   │   ├── test_sqlite.py
│   │   │   ├── test_page_cache.py
│   │   │   └── test_manager.py
│   │   ├── search/
│   │   │   ├── test_chunker.py
│   │   │   ├── test_bm25.py
│   │   │   └── test_engine.py
│   │   ├── adapters/
│   │   │   ├── test_llms_txt.py
│   │   │   ├── test_github.py
│   │   │   └── test_chain.py
│   │   ├── lib/
│   │   │   ├── test_fuzzy_match.py
│   │   │   ├── test_rate_limiter.py
│   │   │   └── test_url_validator.py
│   │   └── registry/
│   │       └── test_pypi_resolver.py
│   ├── integration/
│   │   ├── test_adapter_cache.py    # Adapter + cache integration
│   │   ├── test_search_pipeline.py  # Fetch → chunk → index → search
│   │   └── test_auth_flow.py        # API key auth end-to-end
│   └── e2e/
│       ├── test_stdio_server.py     # Full MCP client ↔ server via stdio
│       └── test_http_server.py      # Full MCP client ↔ server via HTTP
├── docs/
│   └── specs/
│       ├── 01-competitive-analysis.md
│       ├── 02-functional-spec.md
│       ├── 03-technical-spec.md
│       └── 04-implementation-guide.md
├── Dockerfile
├── docker-compose.yml
├── pro-context.config.yaml          # Default configuration
├── pyproject.toml                   # Python project config, dependencies, build
├── uv.lock                          # uv lock file (checked into git)
├── requirements.txt                 # pip lock file (for CI/CD compatibility)
├── .python-version                  # Python version (3.12)
├── pytest.ini                       # Pytest configuration
├── ruff.toml                        # Ruff linter/formatter config
└── README.md
```

---

## 2. Dependency List

### Production Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `mcp` | `>=1.0.0,<2.0.0` | MCP server SDK — tool/resource/prompt registration, stdio + SSE transport |
| `aiosqlite` | `>=0.20.0,<1.0.0` | Async SQLite — persistent cache, search index, API keys |
| `pydantic` | `>=2.9.0,<3.0.0` | Schema validation — config validation, tool input/output validation |
| `cachetools` | `>=5.3.0,<6.0.0` | In-memory TTL cache — hot path for repeated queries |
| `structlog` | `>=24.1.0,<25.0.0` | Structured logging — JSON format, context binding, redaction |
| `pyyaml` | `>=6.0.1,<7.0.0` | YAML parsing — configuration file loading |
| `httpx` | `>=0.27.0,<1.0.0` | HTTP client — async requests with timeout management |
| `rapidfuzz` | `>=3.6.0,<4.0.0` | Fast fuzzy matching — Levenshtein distance for library name resolution |
| `starlette` | `>=0.37.0,<1.0.0` | ASGI framework — HTTP transport (used by MCP SDK for SSE) |
| `uvicorn` | `>=0.29.0,<1.0.0` | ASGI server — production HTTP server |

### Development Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | `>=8.1.0,<9.0.0` | Test framework — standard Python testing |
| `pytest-asyncio` | `>=0.23.0,<1.0.0` | Async test support for pytest |
| `pytest-cov` | `>=5.0.0,<6.0.0` | Coverage reporting |
| `mypy` | `>=1.9.0,<2.0.0` | Static type checking |
| `ruff` | `>=0.3.0,<1.0.0` | Linter + formatter — replaces flake8/black/isort |
| `hatchling` | `>=1.21.0,<2.0.0` | Build backend for pyproject.toml |

### Notably Absent

| Package | Reason for Exclusion |
|---------|---------------------|
| FastAPI | MCP SDK handles HTTP transport with Starlette; no full web framework needed |
| OpenAI/Anthropic SDK | No vector search in initial version; BM25 is dependency-free |
| Redis | SQLite provides sufficient persistence; no external infra needed |
| BeautifulSoup/lxml | No HTML scraping in initial version (llms.txt only) |
| requests | httpx provides both sync and async interfaces |

---

## 2.1 Dependency Management Strategy

Pro-Context supports two package management workflows:

### Option 1: uv (Recommended)

**uv** is a fast Python package manager from Astral (creators of Ruff), 10-100x faster than pip.

**Initial Setup**:
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (creates uv.lock automatically)
uv sync

# Run server
uv run python -m pro_context
```

**Updating Dependencies**:
```bash
# Update to latest compatible versions
uv lock --upgrade

# Test thoroughly
uv run pytest --cov=pro_context

# Generate requirements.txt for pip compatibility
uv pip compile pyproject.toml -o requirements.txt

# Commit lock files
git add uv.lock requirements.txt
git commit -m "chore: update dependencies"
```

**Why uv?**
- ⚡ 10-100x faster than pip
- 🔒 Built-in lock file (`uv.lock`)
- 🎯 Better dependency resolution
- 🔄 Compatible with standard `pyproject.toml`

### Option 2: pip + pip-tools (Fallback)

Standard Python workflow using pip.

**Initial Setup**:
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Generate lock file
pip freeze > requirements.txt
```

**Updating Dependencies**:
```bash
# Update to latest compatible versions
pip install --upgrade pip pip-tools
pip-compile --upgrade pyproject.toml -o requirements.txt

# Test thoroughly
pytest --cov=pro_context

# Commit lock file
git add requirements.txt
git commit -m "chore: update dependencies"
```

### Two-Tier Pinning Strategy

Both workflows use the same approach:

1. **pyproject.toml** (Intent) - SemVer ranges allowing compatible updates
   ```toml
   dependencies = [
       "mcp>=1.0.0,<2.0.0",        # Latest 1.x at project start
       "pydantic>=2.9.0,<3.0.0",   # Latest 2.x at project start
   ]
   ```
   - Lower bound: Minimum tested version (latest at project start)
   - Upper bound: Major version ceiling (prevents breaking changes)

2. **Lock Files** (Exact Versions) - For reproducibility
   - `uv.lock` (uv native format) or `requirements.txt` (pip format)
   - Checked into git
   - Used by CI/CD for reproducible builds

### CI/CD Usage

**With uv** (faster, recommended):
```yaml
- uses: astral-sh/setup-uv@v1
- run: uv sync --frozen  # Install from uv.lock
- run: uv run pytest
```

**With pip** (compatibility):
```yaml
- uses: actions/setup-python@v5
- run: pip install -r requirements.txt
- run: pytest
```

**Recommendation**: Use `uv` for local development, provide both `uv.lock` and `requirements.txt` for CI flexibility.

---

## 2.2 Key Configuration Files

### .python-version

Create this file in the project root to specify Python version for uv:

```
3.12
```

### .gitignore

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.venv/
venv/
ENV/
env/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.hypothesis/

# Type checking
.mypy_cache/
.dmypy.json
dmypy.json

# Ruff
.ruff_cache/

# Logs
*.log

# OS
.DS_Store
Thumbs.db

# Pro-Context specific
/data/cache/*.db
/data/cache/*.db-wal
/data/cache/*.db-shm

# Lock files are CHECKED IN (don't ignore)
# uv.lock
# requirements.txt
```

---

## 3. Coding Conventions

### 3.1 Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Files | snake_case | `fuzzy_match.py`, `get_docs.py` |
| Classes | PascalCase | `Library`, `DocResult`, `SourceAdapter` |
| Functions | snake_case | `resolve_library`, `fetch_toc`, `check_freshness` |
| Constants | UPPER_SNAKE_CASE | `DEFAULT_TTL_HOURS`, `MAX_TOKENS` |
| Config keys | snake_case (YAML) | `max_memory_mb`, `default_ttl_hours` |
| Env vars | UPPER_SNAKE_CASE | `PRO_CONTEXT_PORT`, `PRO_CONTEXT_DEBUG` |
| Error codes | UPPER_SNAKE_CASE | `LIBRARY_NOT_FOUND`, `RATE_LIMITED` |

### 3.2 Error Handling Pattern

```python
# Use ProContextError for all user-facing errors
from pro_context.lib.errors import ProContextError, ErrorCode

# Factory functions create typed errors with actionable messages
def library_not_found(query: str, suggestion: str | None = None) -> ProContextError:
    """Create a LIBRARY_NOT_FOUND error"""
    return ProContextError(
        code=ErrorCode.LIBRARY_NOT_FOUND,
        message=f"Library '{query}' not found in registry",
        recoverable=True,
        suggestion=(
            f"Did you mean '{suggestion}'? "
            if suggestion
            else "Check spelling, wait for next registry update, or add via custom sources config"
        ),
        details={"query": query, "suggestion": suggestion}
    )

def network_fetch_failed(url: str, status_code: int | None = None) -> ProContextError:
    """Create a NETWORK_FETCH_FAILED error"""
    return ProContextError(
        code=ErrorCode.NETWORK_FETCH_FAILED,
        message=f"Failed to fetch documentation from {url}",
        recoverable=True,
        suggestion="This may be temporary. Retry in a few minutes, or check if the documentation site is accessible",
        retry_after=60,  # Suggest retry after 60 seconds
        details={"url": url, "status_code": status_code}
    )

def stale_cache_expired(library_id: str, cache_age_days: int) -> ProContextError:
    """Create a STALE_CACHE_EXPIRED error"""
    return ProContextError(
        code=ErrorCode.STALE_CACHE_EXPIRED,
        message=f"Cached documentation for '{library_id}' is {cache_age_days} days old and cannot be refreshed",
        recoverable=True,
        suggestion="Documentation site may be down or moved. Try again later, or report the issue",
        details={"library_id": library_id, "cache_age_days": cache_age_days}
    )

# In tool handlers, catch and convert errors
async def handle_get_docs(input: dict) -> dict:
    """Tool handler with error handling"""
    try:
        result = await get_docs_for_library(input)
        return result
    except ProContextError as e:
        logger.warning("tool_error", code=e.code, message=e.message, details=e.details)
        return {"error": e}  # Return structured error
    except Exception as e:
        logger.error("unexpected_error", exc_info=e, tool="get-docs")
        return {"error": internal_error()}
```

### 3.3 Test Pattern

```python
# tests/unit/search/test_bm25.py
import pytest
from pro_context.search.bm25 import BM25Index


class TestBM25Index:
    """Test BM25 search ranking"""

    @pytest.fixture
    def index(self):
        """Create a fresh index for each test"""
        return BM25Index()

    def test_exact_matches_rank_highest(self, index):
        """Exact keyword matches should rank higher"""
        index.add_document("1", "langchain chat models streaming")
        index.add_document("2", "fastapi dependency injection middleware")

        results = index.search("langchain chat models")

        assert results[0].id == "1"
        assert results[0].score > results[1].score if len(results) > 1 else 0
```

### 3.4 Module Pattern

- Each file defines a single primary class/function + supporting types
- Use explicit imports from modules (avoid `from module import *`)
- Use `__all__` to control public API surface when needed
- Keep files focused: one concern per file
- Type hint all function signatures and class attributes

### 3.5 Async Pattern

- Use `async/await` for all I/O operations (database, network, file system)
- `aiosqlite` provides async SQLite access — all DB operations must be awaited
- Use `httpx.AsyncClient` for network fetches with timeout configuration
- Use `asyncio.create_task()` for background tasks (e.g., cache refresh)
- Avoid blocking operations in async functions — use `asyncio.to_thread()` if needed

---

## 4. Implementation Phases

### Phase 0: Registry Build Script

**Goal**: Create the build script that generates `known-libraries.json` from PyPI data and llms.txt discovery. This is a prerequisite for all other phases — the runtime server needs the curated registry to function.

**Verification gate**: Build script runs successfully, generates valid `known-libraries.json` with 1000+ libraries, validates all llms.txt URLs.

#### Files to Create

1. **Build script**
   - `scripts/build_registry.py` — Main build script (see 05-library-resolution.md Section 6.2 for full algorithm)
   - `scripts/utils/pypi_client.py` — PyPI JSON API client (GET /pypi/{name}/json)
   - `scripts/utils/llms_txt_validator.py` — Content validation (HTTP status, Content-Type, HTML detection, markdown header check)
   - `scripts/utils/hub_resolver.py` — Hub link following (detect and resolve hub llms.txt files)
   - `data/manual_overrides.yaml` — Manual package groupings, aliases, corrections

2. **Build outputs**
   - `data/known-libraries.json` — Generated registry (checked into repo)
   - `data/build_log.txt` — Build log with discovery stats, validation errors, skipped packages

3. **CI integration**
   - `.github/workflows/update-registry.yml` — Weekly GitHub Action to auto-update registry

#### Phase 0 Verification Checklist

- [ ] Build script fetches top 1000 PyPI packages by download count
- [ ] For each package: extracts name, summary, docs_url, repo_url from PyPI JSON API
- [ ] Groups packages by Repository URL (same repo = same DocSource)
- [ ] Probes for llms.txt at docsUrl-relative patterns (/llms.txt, /en/llms.txt, /latest/llms.txt, etc.)
- [ ] Validates llms.txt content (not HTML error pages)
- [ ] Detects and resolves hub files (follows links, creates separate DocSources)
- [ ] Applies manual overrides from `manual_overrides.yaml`
- [ ] Outputs valid JSON with 1000+ DocSource entries
- [ ] GitHub Action runs weekly and commits updated registry

**Note**: PyPI resolver (`pypi_client.py`) is ONLY used in this build script. It is not part of the runtime server — the server loads the pre-built registry from `known-libraries.json`.

---

### Phase 1: Foundation

**Goal**: Project initialization, MCP server skeleton, configuration, logging, error infrastructure, stdio transport, health check resource.

**Verification gate**: Server starts, connects via stdio, and responds to health check.

#### Files to Create (in order)

1. **Project init**
   - `pyproject.toml` — project metadata, dependencies, scripts, build config, tool configurations
   - `.python-version` — Python version specification (3.12)
   - `pro-context.config.yaml` — default configuration file
   - `.gitignore` — Ignore `.venv/`, `uv.lock` (not ignored, checked in), `__pycache__/`, etc.

2. **Infrastructure**
   - `src/pro_context/lib/logger.py` — structlog logger setup with redaction, correlation IDs, pretty/JSON format
   - `src/pro_context/lib/errors.py` — `ProContextError` class, error code enum, factory functions for each error type
   - `src/pro_context/lib/tokens.py` — `estimate_tokens(text: str) -> int` using chars/4 approximation
   - `src/pro_context/lib/url_validator.py` — URL allowlist checking, SSRF prevention, dynamic allowlist expansion

3. **Configuration**
   - `src/pro_context/config/schema.py` — Pydantic schema for `ProContextConfig`, defaults for every field
   - `src/pro_context/config/loader.py` — Load YAML config file, apply env var overrides, validate with Pydantic

4. **Server skeleton**
   - `src/pro_context/server.py` — Create MCP `Server` instance, register capabilities (tools, resources, prompts)
   - `src/pro_context/__main__.py` — Entry point: load config, create server, select transport (stdio), connect

5. **Health check**
   - `src/pro_context/resources/health.py` — `pro-context://health` resource returning server status JSON

6. **Tests**
   - `tests/unit/lib/test_url_validator.py`
   - Basic smoke test: server starts and responds to list-tools

#### Phase 1 Verification Checklist

**With uv**:
- [ ] `uv sync` installs dependencies without errors
- [ ] `uv run pytest` runs with zero errors
- [ ] `uv run ruff check .` passes with zero warnings
- [ ] `uv run python -m pro_context` starts without errors
- [ ] Server responds to MCP `initialize` handshake via stdio
- [ ] Health resource returns valid JSON with status "healthy"
- [ ] Configuration file is validated (invalid config produces clear error)
- [ ] Env variable overrides work (e.g., `PRO_CONTEXT_LOG_LEVEL=debug`)
- [ ] `uv.lock` is generated and can be committed

**With pip**:
- [ ] `pip install -e ".[dev]"` installs dependencies without errors
- [ ] `pytest` runs with zero errors
- [ ] `ruff check .` passes with zero warnings
- [ ] `python -m pro_context` starts without errors
- [ ] Server responds to MCP `initialize` handshake via stdio
- [ ] `requirements.txt` can be generated with `pip freeze`

---

### Phase 2: Core Documentation Pipeline

**Goal**: Source adapter interface, curated library registry, **llms.txt adapter only** (GitHub/Custom deferred to Phase 4+), two-tier cache, `resolve-library` tool, `get-library-info` tool, `get-docs` tool.

**Scope limitation**: Phase 2 only implements llms.txt adapter. Libraries without llms.txt return `LLMS_TXT_NOT_AVAILABLE` error. This focuses the implementation on proven technology while keeping architecture clean for future extensions.

**Verification gate**: `resolve-library("langchain")` returns matches from curated registry; `get-library-info` returns TOC; `get-docs` for LangChain returns documentation from llms.txt.

#### Files to Create (in order)

1. **Registry**
   - `src/pro_context/registry/types.py` — `Library` dataclass, registry loader interface
   - `src/pro_context/registry/known_libraries.py` — Registry loader: loads `known-libraries.json` into memory, builds lookup indexes (ID, package name, fuzzy search corpus)
   - `src/pro_context/lib/fuzzy_match.py` — Levenshtein distance (rapidfuzz) + `find_closest_matches()`
   - `data/known-libraries.json` — Comprehensive registry of ~1,350 libraries (top 1000 PyPI + curated sources), all marked with `llmsTxtAvailable` field

2. **Source Adapters** (llms.txt only for Phase 2)
   - `src/pro_context/adapters/types.py` — `SourceAdapter` ABC, `RawPageContent` dataclass, `TocEntry` dataclass
   - `src/pro_context/adapters/llms_txt.py` — Fetch and parse `llms.txt` for TOC, fetch individual pages
   - ~~`src/pro_context/adapters/chain.py`~~ — **Deferred to Phase 4+** (no chain needed with single adapter)
   - ~~`src/pro_context/adapters/github.py`~~ — **Deferred to Phase 4+** (design complete in doc 03)
   - ~~`src/pro_context/adapters/custom.py`~~ — **Deferred to Phase 4+** (design complete in doc 03)

3. **Cache**
   - `src/pro_context/cache/sqlite.py` — SQLite cache: init DB, get/set/delete operations, cleanup
   - `src/pro_context/cache/memory.py` — LRU cache wrapper with TTL
   - `src/pro_context/cache/manager.py` — Two-tier cache orchestrator: memory → SQLite → miss

4. **Tools**
   - `src/pro_context/tools/resolve_library.py` — Fuzzy match query against registry, return all matches with languages, check `llmsTxtAvailable` field
   - `src/pro_context/tools/get_library_info.py` — Check `llmsTxtAvailable`, fetch TOC via llms.txt adapter, extract availableSections, apply sections filter
   - `src/pro_context/tools/get_docs.py` — Multi-library: fetch docs via cache → llms.txt adapter → chunk → BM25 rank → return with relatedPages

5. **Resources**
   - `src/pro_context/resources/session.py` — `pro-context://session/resolved-libraries` resource

6. **Registration**
   - Update `src/pro_context/server.py` — Register `resolve-library`, `get-library-info`, `get-docs` tools + session resource

7. **Tests** (Phase 2: llms.txt only)
   - `tests/unit/registry/test_known_libraries.py` — Registry loading, index building, lookups, `llmsTxtAvailable` flag
   - `tests/unit/lib/test_fuzzy_match.py` — Levenshtein distance + matching
   - `tests/unit/adapters/test_llms_txt.py` — Parse llms.txt TOC, fetch pages, handle 404, handle missing llms.txt
   - ~~`tests/unit/adapters/test_github.py`~~ — **Deferred to Phase 4+**
   - ~~`tests/unit/adapters/test_chain.py`~~ — **Deferred to Phase 4+**
   - `tests/unit/cache/test_memory.py` — TTL cache operations
   - `tests/unit/cache/test_sqlite.py` — SQLite CRUD + cleanup, stale flag handling
   - `tests/unit/cache/test_manager.py` — Two-tier promotion + stale handling
   - `tests/integration/test_adapter_cache.py` — Full fetch → cache → serve flow (llms.txt only)

#### Phase 2 Verification Checklist

- [ ] `resolve-library("langchain")` returns matches including `langchain-ai/langchain`
- [ ] `resolve-library("langchan")` returns fuzzy match for "langchain"
- [ ] `get-library-info("langchain-ai/langchain")` returns TOC with availableSections
- [ ] `get-library-info("langchain-ai/langchain", sections: ["Getting Started"])` returns filtered TOC
- [ ] `get-docs([{libraryId: "langchain-ai/langchain"}], "chat models")` returns markdown content
- [ ] Content comes from llms.txt when available
- [ ] If llms.txt unavailable, falls back to GitHub
- [ ] Second request for same content is served from cache (check logs for cache hit)
- [ ] Cache SQLite file is created at configured path
- [ ] Session resource tracks resolved libraries

---

### Phase 3: Search & Navigation

**Goal**: Document chunking, BM25 search indexing, `search-docs` tool (cross-library), `read-page` tool (offset-based reading), page cache.

**Verification gate**: Search returns relevant results across libraries; read-page supports offset-based reading of large pages.

#### Files to Create (in order)

1. **Search Engine**
   - `src/pro_context/search/chunker.py` — Markdown → `list[DocChunk]`: heading-aware splitting, token budgets, section path extraction
   - `src/pro_context/search/bm25.py` — BM25 algorithm: tokenization, inverted index, IDF computation, query scoring
   - `src/pro_context/search/engine.py` — Search engine orchestrator: index management, query execution, cross-library search, result formatting

2. **Page Cache**
   - `src/pro_context/cache/page_cache.py` — Page cache with offset-based slice support (see technical spec 5.4)

3. **Tools**
   - `src/pro_context/tools/search_docs.py` — Search indexed docs, optional library scoping, JIT indexing trigger
   - `src/pro_context/tools/read_page.py` — Fetch page, cache full content, serve slices with offset/maxTokens, URL allowlist validation

4. **Update get-docs**
   - Update `src/pro_context/tools/get_docs.py` — Integrate chunker: fetch raw docs → chunk → rank by topic across libraries → return best chunks within token budget

5. **Registration**
   - Update `src/pro_context/server.py` — Register `search-docs`, `read-page` tools

6. **Tests**
   - `tests/unit/search/test_chunker.py` — Heading detection, chunk sizing, section paths
   - `tests/unit/search/test_bm25.py` — Ranking correctness, edge cases
   - `tests/unit/search/test_engine.py` — Index + query orchestration, cross-library ranking
   - `tests/unit/cache/test_page_cache.py` — Full page caching, offset slicing, hasMore
   - `tests/integration/test_search_pipeline.py` — Fetch → chunk → index → search → results

#### Phase 3 Verification Checklist

- [ ] `search-docs({query: "streaming"})` searches across all indexed content
- [ ] `search-docs({query: "streaming", libraryIds: ["langchain-ai/langchain"]})` searches within LangChain
- [ ] Results include libraryId, title, snippet, relevance score, URL
- [ ] BM25 ranks exact keyword matches higher than tangential mentions
- [ ] `read-page({url: "https://..."})` returns page content with position metadata
- [ ] `read-page({url: "https://...", offset: 1000})` returns content from offset position
- [ ] `hasMore` is true when content remains beyond offset + maxTokens
- [ ] Pages are cached: second read-page call for same URL is served from cache
- [ ] URL allowlist blocks non-documentation URLs
- [ ] `get-docs` now returns focused chunks (not raw full docs)
- [ ] Average token count per `get-docs` response is <3,000

---

### Phase 4: HTTP Mode & Authentication

**Goal**: Streamable HTTP transport, API key authentication, per-key rate limiting, admin CLI, CORS.

**Verification gate**: HTTP mode works with API key; rate limiting kicks in at configured threshold; unauthorized requests are rejected.

#### Files to Create (in order)

1. **Authentication**
   - `src/pro_context/auth/api_keys.py` — Key generation (`pc_` prefix + random bytes), SHA-256 hashing, validation, CRUD operations on SQLite
   - `src/pro_context/auth/middleware.py` — HTTP middleware: extract Bearer token, validate against DB, attach key info to request context
   - `src/pro_context/auth/admin_cli.py` — CLI entry point: `key create`, `key list`, `key revoke`, `key stats` commands

2. **Rate Limiting**
   - `src/pro_context/lib/rate_limiter.py` — Token bucket implementation: per-key buckets, configurable capacity/refill, rate limit headers

3. **HTTP Transport**
   - Update `src/pro_context/__main__.py` — Add HTTP transport path: when `config.server.transport == "http"`, create HTTP server with auth middleware, rate limiter, CORS headers, and SSE transport

4. **pyproject.toml update**
   - Add `[project.scripts]` entry for `pro-context-admin` CLI

5. **Tests**
   - `tests/unit/lib/test_rate_limiter.py` — Token bucket behavior, burst, refill
   - `tests/integration/test_auth_flow.py` — Create key → authenticate → rate limit → revoke
   - `tests/e2e/test_http_server.py` — Full MCP client ↔ server via HTTP with auth

#### Phase 4 Verification Checklist

- [ ] `PRO_CONTEXT_TRANSPORT=http node dist/index.js` starts HTTP server on port 3100
- [ ] Request without API key → 401 `AUTH_REQUIRED`
- [ ] Request with invalid key → 401 `AUTH_INVALID`
- [ ] Request with valid key → 200 with MCP response
- [ ] `pro-context-admin key create --name "test"` outputs a new API key
- [ ] `pro-context-admin key list` shows created keys
- [ ] `pro-context-admin key revoke --id <id>` disables the key
- [ ] Rate limiting kicks in after configured threshold (default: 60/min)
- [ ] Rate limit response includes `X-RateLimit-*` headers
- [ ] CORS headers are set correctly
- [ ] Multiple clients share the same cache (one fetch benefits all)

---

### Phase 5: Polish & Production Readiness

**Goal**: Prompt templates, custom source adapter completion, Docker deployment, comprehensive test suite, documentation.

**Verification gate**: Full e2e test passes — Claude Code connects, resolves library, gets info, gets docs, searches, reads pages. Docker image builds and runs.

#### Files to Create (in order)

1. **Prompts**
   - `src/pro_context/prompts/migrate_code.py` — Migration prompt template
   - `src/pro_context/prompts/debug_with_docs.py` — Debug prompt template
   - `src/pro_context/prompts/explain_api.py` — API explanation prompt template

2. **Registration**
   - Update `src/pro_context/server.py` — Register prompt templates

3. **Docker**
   - `Dockerfile` — Multi-stage build: install deps → build package → slim runtime image
   - `docker-compose.yml` — Easy local HTTP-mode testing with volume mount for cache

4. **E2E Tests**
   - `tests/e2e/test_stdio_server.py` — Full MCP client ↔ server via stdio: resolve → get-library-info → get-docs → search → read-page
   - Update `tests/e2e/test_http_server.py` — Add prompt and resource tests

5. **README**
   - `README.md` — Project overview, quick start, configuration guide, deployment guide

#### Phase 5 Verification Checklist

- [ ] `migrate-code` prompt template produces correct prompt text
- [ ] `debug-with-docs` prompt template produces correct prompt text
- [ ] `explain-api` prompt template produces correct prompt text
- [ ] `docker build -t pro-context .` succeeds
- [ ] `docker-compose up` starts server in HTTP mode
- [ ] Docker container responds to MCP requests
- [ ] E2E stdio test: client connects → resolve-library → get-library-info → get-docs → search-docs → read-page → all succeed
- [ ] E2E HTTP test: client authenticates → all tools work → rate limiting works
- [ ] `pytest --cov=pro_context` passes with >80% code coverage on src/

---

## 5. Testing Strategy

### 5.1 Test Pyramid

```
        ┌──────────┐
        │   E2E    │  2-3 tests: full MCP client ↔ server
        │  (slow)  │  Real stdio/HTTP transport
        ├──────────┤
        │ Integr.  │  5-8 tests: multi-component flows
        │ (medium) │  Real SQLite, mocked network
        ├──────────┤
        │   Unit   │  30-50 tests: individual functions
        │  (fast)  │  Pure logic, no I/O
        └──────────┘
```

### 5.2 What to Test

| Component | Unit Tests | Integration Tests | What to Mock |
|-----------|-----------|------------------|-------------|
| BM25 | Ranking correctness, edge cases (empty query, single doc) | — | Nothing (pure logic) |
| Chunker | Heading detection, size limits, section paths | — | Nothing (pure logic) |
| Fuzzy match | Edit distance, no match, exact match, multi-match | — | Nothing (pure logic) |
| Rate limiter | Token bucket math, burst, refill | — | Time (use fake timers) |
| URL validator | Allowlist, SSRF blocks, dynamic expansion | — | Nothing (pure logic) |
| Memory cache | Get/set/delete, TTL, LRU eviction | — | Nothing |
| SQLite cache | CRUD, cleanup, expiry | — | Nothing (use in-memory SQLite) |
| Page cache | Full page store, offset slicing, hasMore | — | Nothing (use in-memory SQLite) |
| Cache manager | Tier promotion, stale handling | Adapter + cache flow | Network fetches |
| llms.txt adapter | Parse llms.txt TOC, fetchPage, handle 404 | Full fetch → cache | HTTP responses |
| GitHub adapter | Generate TOC from directory, fetchPage, rate limit | Full fetch → cache | HTTP responses |
| Adapter chain | Fallback on failure, priority order | Full chain with cache | HTTP responses |
| PyPI resolver | Version parsing, latest detection | — | HTTP responses |
| API key auth | Hash validation, key format | Create → auth → revoke | Nothing (use test SQLite) |
| Search engine | Index + query orchestration, cross-library | Fetch → chunk → index → search | HTTP responses |
| Tool handlers | Input validation, output format | — | Core engine (mock adapters) |

### 5.3 What NOT to Test

- MCP SDK internals (trust the SDK)
- SQLite engine behavior (trust better-sqlite3)
- Pino logging output format (trust pino)
- External API response formats beyond what we parse
- Exact token count accuracy (approximation is fine)

### 5.4 Test Configuration

```toml
# pytest.ini or pyproject.toml [tool.pytest.ini_options]
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--tb=short",
    "--cov=pro_context",
    "--cov-branch",
    "--cov-fail-under=80",
]
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "e2e: End-to-end tests",
]
timeout = 10
```

Coverage thresholds:
- Statements: 80%
- Branches: 75%
- Functions: 80%
- Lines: 80%

Excluded from coverage:
- `src/pro_context/__main__.py` (entry point)
- `src/pro_context/auth/admin_cli.py` (CLI tool)

---

## 6. CI/CD and Docker Deployment

### 6.1 Dockerfile

**Option 1: With uv (Recommended - Faster Builds)**

```dockerfile
# Stage 1: Build
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (uses uv.lock for reproducibility)
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ src/
COPY pro-context.config.yaml ./
COPY data/ data/

# Stage 2: Production
FROM python:3.12-slim
WORKDIR /app

# Copy installed dependencies and application from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pro-context.config.yaml ./
COPY --from=builder /app/data ./data

# Create cache directory
RUN mkdir -p /data/cache

ENV PATH="/app/.venv/bin:$PATH"
ENV PRO_CONTEXT_TRANSPORT=http
ENV PRO_CONTEXT_PORT=3100
ENV PRO_CONTEXT_CACHE_DIR=/data/cache

EXPOSE 3100
CMD ["python", "-m", "pro_context"]
```

**Option 2: With pip (Compatibility)**

```dockerfile
# Stage 1: Build
FROM python:3.12-slim AS builder
WORKDIR /app

# Install build dependencies
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ src/
COPY pro-context.config.yaml ./
COPY data/ data/

# Stage 2: Production
FROM python:3.12-slim
WORKDIR /app

# Install production dependencies only
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=builder /app/src ./src
COPY --from=builder /app/pro-context.config.yaml ./
COPY --from=builder /app/data ./data

# Create cache directory
RUN mkdir -p /data/cache

ENV PRO_CONTEXT_TRANSPORT=http
ENV PRO_CONTEXT_PORT=3100
ENV PRO_CONTEXT_CACHE_DIR=/data/cache

EXPOSE 3100
CMD ["python", "-m", "pro_context"]
```

### 6.2 docker-compose.yml

```yaml
version: "3.8"
services:
  pro-context:
    build: .
    ports:
      - "3100:3100"
    volumes:
      - pro-context-cache:/data/cache
    environment:
      - PRO_CONTEXT_TRANSPORT=http
      - PRO_CONTEXT_PORT=3100
      - PRO_CONTEXT_LOG_LEVEL=info
      # Optional: GitHub token for higher rate limits
      # - PRO_CONTEXT_GITHUB_TOKEN=ghp_xxx

volumes:
  pro-context-cache:
```

### 6.3 GitHub Actions CI

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test-uv:
    name: Test with uv (primary)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v1
        with:
          enable-cache: true

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --frozen  # Use locked versions from uv.lock

      - name: Lint
        run: |
          uv run ruff check .
          uv run ruff format --check .

      - name: Type check
        run: uv run mypy src/

      - name: Test
        run: uv run pytest --cov=pro_context --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml

  test-pip:
    name: Test with pip (compatibility)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Lint
        run: |
          ruff check .
          ruff format --check .

      - name: Type check
        run: mypy src/

      - name: Test
        run: pytest --cov=pro_context --cov-report=xml
```

### 6.4 pyproject.toml Configuration

```toml
[project]
name = "pro-context"
version = "1.0.0"
description = "MCP documentation server for AI coding agents"
authors = [{name = "Ankur Tewatia"}]
license = {text = "GPL-3.0"}
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0.0,<2.0.0",
    "aiosqlite>=0.20.0,<1.0.0",
    "pydantic>=2.9.0,<3.0.0",
    "cachetools>=5.3.0,<6.0.0",
    "structlog>=24.1.0,<25.0.0",
    "pyyaml>=6.0.1,<7.0.0",
    "httpx>=0.27.0,<1.0.0",
    "rapidfuzz>=3.6.0,<4.0.0",
    "starlette>=0.37.0,<1.0.0",
    "uvicorn>=0.29.0,<1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.1.0,<9.0.0",
    "pytest-asyncio>=0.23.0,<1.0.0",
    "pytest-cov>=5.0.0,<6.0.0",
    "mypy>=1.9.0,<2.0.0",
    "ruff>=0.3.0,<1.0.0",
]

[project.scripts]
pro-context = "pro_context.__main__:main"
pro-context-admin = "pro_context.auth.admin_cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=8.1.0,<9.0.0",
    "pytest-asyncio>=0.23.0,<1.0.0",
    "pytest-cov>=5.0.0,<6.0.0",
    "mypy>=1.9.0,<2.0.0",
    "ruff>=0.3.0,<1.0.0",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "SIM"]
ignore = []

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--tb=short",
    "--cov=pro_context",
    "--cov-branch",
    "--cov-fail-under=80",
]
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "e2e: End-to-end tests",
]
timeout = 10
```

**Common commands (uv)**:

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=pro_context --cov-report=html

# Lint and format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src/

# Run server (stdio mode)
uv run python -m pro_context

# Run admin CLI
uv run pro-context-admin key create --name "test"
```

**Common commands (pip)**:

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=pro_context --cov-report=html

# Lint and format
ruff check .
ruff format .

# Type check
mypy src/

# Run server (stdio mode)
python -m pro_context

# Run admin CLI
pro-context-admin key create --name "test"
```

---

## 7. Future Expansion Roadmap

### Phase 6: JavaScript/TypeScript Support

**New files:**
- `src/pro_context/registry/npm_resolver.py` — npm registry version/URL resolution
- Extend `src/pro_context/registry/known_libraries.py` — Add JS/TS libraries (React, Next.js, Express, etc.)

**Changes:**
- `src/pro_context/tools/resolve_library.py` — Route to npm resolver when `language: "javascript"` or `"typescript"`

**No changes needed in:** adapters, cache, search, config, auth, transport

### Phase 7: HTML Documentation Adapter

**New files:**
- `src/pro_context/adapters/html_docs.py` — Fetch and parse HTML documentation sites
- `src/pro_context/lib/html_to_markdown.py` — HTML → markdown conversion with sanitization

**New dependencies:** `beautifulsoup4` + `lxml` for HTML parsing, `markdownify` for conversion

**Changes:**
- `src/pro_context/adapters/chain.py` — Add HTML adapter to the chain with appropriate priority

### Phase 8: Vector Search (Hybrid)

**New files:**
- `src/pro_context/search/embeddings.py` — Embedding generation (local sentence-transformers or OpenAI API)
- `src/pro_context/search/vector_index.py` — Vector similarity search using sqlite-vec

**New dependencies:** `sqlite-vec` (SQLite extension), optionally `sentence-transformers` for local embeddings

**Changes:**
- `src/pro_context/search/engine.py` — Add hybrid search path: BM25 + vector → RRF merge
- `src/pro_context/config/schema.py` — Add embedding model configuration

### Phase 9: Prometheus Metrics

**New files:**
- `src/pro_context/lib/metrics.py` — Prometheus metric definitions
- Metrics endpoint at `/metrics` in HTTP mode

**New dependency:** `prometheus-client`

---

## 8. Quick Reference: MCP Client Configuration

### Claude Code (stdio with uv)

```bash
claude mcp add pro-context -- uv run python -m pro_context
```

### Claude Code (stdio with pip)

```bash
# After activating virtual environment
claude mcp add pro-context -- python -m pro_context
```

### Claude Code (HTTP)

```json
{
  "mcpServers": {
    "pro-context": {
      "url": "http://localhost:3100/sse",
      "headers": {
        "Authorization": "Bearer pc_your-api-key-here"
      }
    }
  }
}
```

### Cursor / Windsurf (stdio with uv)

```json
{
  "mcpServers": {
    "pro-context": {
      "command": "uv",
      "args": ["run", "python", "-m", "pro_context"]
    }
  }
}
```

### Cursor / Windsurf (stdio with pip)

```json
{
  "mcpServers": {
    "pro-context": {
      "command": "python",
      "args": ["-m", "pro_context"]
    }
  }
}
```

---

## 9. Development Workflow

### Initial Setup (uv - Recommended)

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone <repo-url>
cd pro-context
uv sync

# Run tests
uv run pytest

# Start in development mode (stdio)
uv run python -m pro_context

# Test with Claude Code
claude mcp add pro-context -- uv run python -m pro_context
```

### Initial Setup (pip - Fallback)

```bash
# Clone and install
git clone <repo-url>
cd pro-context
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run tests
pytest

# Start in development mode (stdio)
python -m pro_context

# Test with Claude Code
claude mcp add pro-context -- python -m pro_context
```

### Common Development Commands

| Task | uv | pip |
|------|-----|-----|
| **Run tests** | `uv run pytest` | `pytest` |
| **Run with coverage** | `uv run pytest --cov=pro_context` | `pytest --cov=pro_context` |
| **Lint** | `uv run ruff check .` | `ruff check .` |
| **Format** | `uv run ruff format .` | `ruff format .` |
| **Type check** | `uv run mypy src/` | `mypy src/` |
| **Run server (stdio)** | `uv run python -m pro_context` | `python -m pro_context` |
| **Run server (HTTP)** | `PRO_CONTEXT_TRANSPORT=http uv run python -m pro_context` | `PRO_CONTEXT_TRANSPORT=http python -m pro_context` |
| **Admin CLI** | `uv run pro-context-admin key create --name "test"` | `pro-context-admin key create --name "test"` |
| **Update dependencies** | `uv lock --upgrade` | `pip-compile --upgrade pyproject.toml` |

### Adding a New Library to the Registry

**With uv**:
1. Edit `src/pro_context/registry/known_libraries.py`
2. Add entry with `id`, `name`, `description`, `languages`, `package_name`, `docs_url`, `repo_url`
3. Run tests: `uv run pytest tests/unit/registry/`
4. Lint: `uv run ruff check .`
5. Format: `uv run ruff format .`

**With pip** (after activating venv):
1. Edit `src/pro_context/registry/known_libraries.py`
2. Add entry with `id`, `name`, `description`, `languages`, `package_name`, `docs_url`, `repo_url`
3. Run tests: `pytest tests/unit/registry/`
4. Lint: `ruff check .`
5. Format: `ruff format .`

### Adding a New Source Adapter

1. Create `src/pro_context/adapters/{name}.py` implementing `SourceAdapter` ABC
2. Implement `can_handle`, `fetch_toc`, `fetch_page`, `check_freshness` async methods
3. Register in `src/pro_context/adapters/chain.py` with appropriate priority
4. Add tests in `tests/unit/adapters/test_{name}.py`
5. Add integration test if the adapter has external dependencies
6. Run full test suite: `uv run pytest` or `pytest`
7. Type check: `uv run mypy src/pro_context/adapters/{name}.py` or `mypy src/pro_context/adapters/{name}.py`
