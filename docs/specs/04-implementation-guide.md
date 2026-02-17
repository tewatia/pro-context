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
│       │   ├── chain.py            # AdapterChain: ordered execution with fallback
│       │   ├── llms_txt.py         # llms.txt adapter implementation
│       │   ├── github.py           # GitHub docs adapter implementation
│       │   └── custom.py           # User-configured source adapter
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
├── pytest.ini                       # Pytest configuration
├── ruff.toml                        # Ruff linter/formatter config
└── README.md
```

---

## 2. Dependency List

### Production Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `mcp` | `>=1.0.0` | MCP server SDK — tool/resource/prompt registration, stdio + SSE transport |
| `aiosqlite` | `^0.20.0` | Async SQLite — persistent cache, search index, API keys |
| `pydantic` | `^2.0` | Schema validation — config validation, tool input/output validation |
| `cachetools` | `^5.3` | In-memory TTL cache — hot path for repeated queries |
| `structlog` | `^24.0` | Structured logging — JSON format, context binding, redaction |
| `pyyaml` | `^6.0` | YAML parsing — configuration file loading |
| `httpx` | `^0.27` | HTTP client — async requests with timeout management |
| `rapidfuzz` | `^3.6` | Fast fuzzy matching — Levenshtein distance for library name resolution |
| `starlette` | `^0.37` | ASGI framework — HTTP transport (used by MCP SDK for SSE) |
| `uvicorn` | `^0.29` | ASGI server — production HTTP server |

### Development Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | `^8.1` | Test framework — standard Python testing |
| `pytest-asyncio` | `^0.23` | Async test support for pytest |
| `pytest-cov` | `^5.0` | Coverage reporting |
| `mypy` | `^1.9` | Static type checking |
| `ruff` | `^0.3` | Linter + formatter — replaces flake8/black/isort |
| `hatchling` | `^1.21` | Build backend for pyproject.toml |

### Notably Absent

| Package | Reason for Exclusion |
|---------|---------------------|
| FastAPI | MCP SDK handles HTTP transport with Starlette; no full web framework needed |
| OpenAI/Anthropic SDK | No vector search in initial version; BM25 is dependency-free |
| Redis | SQLite provides sufficient persistence; no external infra needed |
| BeautifulSoup/lxml | No HTML scraping in initial version |
| requests | httpx provides both sync and async interfaces |

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
from pro_context.lib.errors import ProContextError, library_not_found

# Factory functions create typed errors
def library_not_found(query: str, suggestion: str | None = None) -> ProContextError:
    """Create a LIBRARY_NOT_FOUND error"""
    return ProContextError(
        code=ErrorCode.LIBRARY_NOT_FOUND,
        message=f"Library '{query}' not found.",
        recoverable=True,
        suggestion=(
            f"Did you mean '{suggestion}'?"
            if suggestion
            else "Check the library name and try again."
        ),
    )


# In tool handlers, catch and convert errors
async def handle_get_docs(input: dict) -> dict:
    """Tool handler with error handling"""
    try:
        result = await get_docs_for_library(input)
        return result
    except ProContextError as e:
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
   - `package.json` — project metadata, scripts, dependencies
   - `tsconfig.json` — TypeScript strict mode, ESM target, path aliases
   - `biome.json` — lint + format configuration
   - `vitest.config.ts` — test configuration
   - `pro-context.config.yaml` — default configuration file

2. **Infrastructure**
   - `src/lib/logger.ts` — Pino logger setup with redaction, correlation IDs, pretty/JSON format
   - `src/lib/errors.ts` — `ProContextError` class, error code enum, factory functions for each error type
   - `src/lib/tokens.ts` — `estimateTokens(text: string): number` using chars/4 approximation
   - `src/lib/url-validator.ts` — URL allowlist checking, SSRF prevention, dynamic allowlist expansion

3. **Configuration**
   - `src/config/schema.ts` — Zod schema for `ProContextConfig`, defaults for every field
   - `src/config/loader.ts` — Load YAML config file, apply env var overrides, validate with Zod

4. **Server skeleton**
   - `src/server.ts` — Create MCP `Server` instance, register capabilities (tools, resources, prompts)
   - `src/index.ts` — Entry point: load config, create server, select transport (stdio), connect

5. **Health check**
   - `src/resources/health.ts` — `pro-context://health` resource returning server status JSON

6. **Tests**
   - `tests/unit/lib/url-validator.test.ts`
   - Basic smoke test: server starts and responds to list-tools

#### Phase 1 Verification Checklist

- [ ] `npm run build` succeeds with zero errors
- [ ] `npm run lint` passes with zero warnings
- [ ] `node dist/index.js` starts without errors
- [ ] Server responds to MCP `initialize` handshake via stdio
- [ ] Health resource returns valid JSON with status "healthy"
- [ ] Configuration file is validated (invalid config produces clear error)
- [ ] Env variable overrides work (e.g., `PRO_CONTEXT_LOG_LEVEL=debug`)

---

### Phase 2: Core Documentation Pipeline

**Goal**: Source adapter interface, curated library registry, llms.txt adapter, GitHub adapter, two-tier cache, `resolve-library` tool, `get-library-info` tool, `get-docs` tool.

**Verification gate**: `resolve-library("langchain")` returns matches from curated registry; `get-library-info` returns TOC; `get-docs` for LangChain returns documentation from llms.txt.

#### Files to Create (in order)

1. **Registry**
   - `src/pro_context/registry/types.py` — `Library` dataclass, registry loader interface
   - `src/pro_context/registry/known_libraries.py` — Registry loader: loads `known-libraries.json` into memory, builds lookup indexes (ID, package name, fuzzy search corpus)
   - `src/pro_context/lib/fuzzy_match.py` — Levenshtein distance (rapidfuzz) + `find_closest_matches()`
   - `data/known-libraries.json` — Curated registry of ~1000 Python libraries (generated by build script, checked into repo)

2. **Source Adapters**
   - `src/adapters/types.ts` — `SourceAdapter` interface, `RawPageContent` type, `TocEntry` type
   - `src/adapters/chain.ts` — `AdapterChain` class: ordered adapter execution with fallback (fetchToc + fetchPage)
   - `src/adapters/llms-txt.ts` — Fetch and parse `llms.txt` for TOC, fetch individual pages
   - `src/adapters/github.ts` — Fetch docs from GitHub repo (/docs/, README.md), generate TOC from directory structure
   - `src/adapters/custom.ts` — User-configured sources (URL, file, GitHub)

3. **Cache**
   - `src/cache/sqlite.ts` — SQLite cache: init DB, get/set/delete operations, cleanup
   - `src/cache/memory.ts` — LRU cache wrapper with TTL
   - `src/cache/manager.ts` — Two-tier cache orchestrator: memory → SQLite → miss

4. **Tools**
   - `src/tools/resolve-library.ts` — Fuzzy match query against registry, return all matches with languages
   - `src/tools/get-library-info.ts` — Fetch TOC via adapter chain, extract availableSections, apply sections filter
   - `src/tools/get-docs.ts` — Multi-library: fetch docs via cache → adapter chain → chunk → BM25 rank → return with relatedPages

5. **Resources**
   - `src/resources/session.ts` — `pro-context://session/resolved-libraries` resource

6. **Registration**
   - Update `src/server.ts` — Register `resolve-library`, `get-library-info`, `get-docs` tools + session resource

7. **Tests**
   - `tests/unit/registry/test_known_libraries.py` — Registry loading, index building, lookups
   - `tests/unit/lib/test_fuzzy_match.py` — Levenshtein distance + matching
   - `tests/unit/adapters/test_llms_txt.py` — Parse llms.txt TOC, fetch pages, handle 404
   - `tests/unit/adapters/test_github.py` — Generate TOC from directory, fetch pages
   - `tests/unit/adapters/test_chain.py` — Fallback behavior (fetch_toc + fetch_page)
   - `tests/unit/cache/test_memory.py` — TTL cache operations
   - `tests/unit/cache/test_sqlite.py` — SQLite CRUD + cleanup
   - `tests/unit/cache/test_manager.py` — Two-tier promotion + stale handling
   - `tests/integration/test_adapter_cache.py` — Full fetch → cache → serve flow

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
   - `src/search/chunker.ts` — Markdown → `DocChunk[]`: heading-aware splitting, token budgets, section path extraction
   - `src/search/bm25.ts` — BM25 algorithm: tokenization, inverted index, IDF computation, query scoring
   - `src/search/engine.ts` — Search engine orchestrator: index management, query execution, cross-library search, result formatting

2. **Page Cache**
   - `src/cache/page-cache.ts` — Page cache with offset-based slice support (see technical spec 5.4)

3. **Tools**
   - `src/tools/search-docs.ts` — Search indexed docs, optional library scoping, JIT indexing trigger
   - `src/tools/read-page.ts` — Fetch page, cache full content, serve slices with offset/maxTokens, URL allowlist validation

4. **Update get-docs**
   - Update `src/tools/get-docs.ts` — Integrate chunker: fetch raw docs → chunk → rank by topic across libraries → return best chunks within token budget

5. **Registration**
   - Update `src/server.ts` — Register `search-docs`, `read-page` tools

6. **Tests**
   - `tests/unit/search/chunker.test.ts` — Heading detection, chunk sizing, section paths
   - `tests/unit/search/bm25.test.ts` — Ranking correctness, edge cases
   - `tests/unit/search/engine.test.ts` — Index + query orchestration, cross-library ranking
   - `tests/unit/cache/page-cache.test.ts` — Full page caching, offset slicing, hasMore
   - `tests/integration/search-pipeline.test.ts` — Fetch → chunk → index → search → results

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
   - `src/auth/api-keys.ts` — Key generation (`pc_` prefix + random bytes), SHA-256 hashing, validation, CRUD operations on SQLite
   - `src/auth/middleware.ts` — HTTP middleware: extract Bearer token, validate against DB, attach key info to request context
   - `src/auth/admin-cli.ts` — CLI entry point: `key create`, `key list`, `key revoke`, `key stats` commands

2. **Rate Limiting**
   - `src/lib/rate-limiter.ts` — Token bucket implementation: per-key buckets, configurable capacity/refill, rate limit headers

3. **HTTP Transport**
   - Update `src/index.ts` — Add HTTP transport path: when `config.server.transport === "http"`, create HTTP server with auth middleware, rate limiter, CORS headers, and Streamable HTTP transport

4. **Package.json update**
   - Add `bin` entry for `pro-context-admin` CLI

5. **Tests**
   - `tests/unit/lib/rate-limiter.test.ts` — Token bucket behavior, burst, refill
   - `tests/integration/auth-flow.test.ts` — Create key → authenticate → rate limit → revoke
   - `tests/e2e/http-server.test.ts` — Full MCP client ↔ server via HTTP with auth

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
   - `src/prompts/migrate-code.ts` — Migration prompt template
   - `src/prompts/debug-with-docs.ts` — Debug prompt template
   - `src/prompts/explain-api.ts` — API explanation prompt template

2. **Registration**
   - Update `src/server.ts` — Register prompt templates

3. **Docker**
   - `Dockerfile` — Multi-stage build: install deps → compile TS → slim runtime image
   - `docker-compose.yml` — Easy local HTTP-mode testing with volume mount for cache

4. **E2E Tests**
   - `tests/e2e/stdio-server.test.ts` — Full MCP client ↔ server via stdio: resolve → get-library-info → get-docs → search → read-page
   - Update `tests/e2e/http-server.test.ts` — Add prompt and resource tests

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
- [ ] `npm test` passes with >80% code coverage on src/

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

```dockerfile
# Stage 1: Build
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir hatchling
COPY src/ src/
RUN pip install --no-cache-dir .

# Stage 2: Production
FROM python:3.11-slim
WORKDIR /app

# Install production dependencies only
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY pro-context.config.yaml ./

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
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy src/
      - run: pytest --cov=pro_context --cov-report=xml
```

### 6.4 pyproject.toml Configuration

```toml
[project]
name = "pro-context"
version = "1.0.0"
description = "MCP documentation server for AI coding agents"
authors = [{name = "Ankur Tewatia"}]
license = {text = "GPL-3.0"}
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "aiosqlite>=0.20.0",
    "pydantic>=2.0",
    "cachetools>=5.3",
    "structlog>=24.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "rapidfuzz>=3.6",
    "starlette>=0.37",
    "uvicorn>=0.29",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.1",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "mypy>=1.9",
    "ruff>=0.3",
]

[project.scripts]
pro-context = "pro_context.__main__:main"
pro-context-admin = "pro_context.auth.admin_cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "SIM"]
ignore = []

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
```

**Common commands:**

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
- `src/registry/npm-resolver.ts` — npm registry version/URL resolution
- Extend `src/registry/known-libraries.ts` — Add JS/TS libraries (React, Next.js, Express, etc.)

**Changes:**
- `src/tools/resolve-library.ts` — Route to npm resolver when `language: "javascript"` or `"typescript"`

**No changes needed in:** adapters, cache, search, config, auth, transport

### Phase 7: HTML Documentation Adapter

**New files:**
- `src/adapters/html-docs.ts` — Fetch and parse HTML documentation sites
- `src/lib/html-to-markdown.ts` — HTML → markdown conversion with sanitization

**New dependency:** `cheerio` or `linkedom` for HTML parsing

**Changes:**
- `src/adapters/chain.ts` — Add HTML adapter to the chain with appropriate priority

### Phase 8: Vector Search (Hybrid)

**New files:**
- `src/search/embeddings.ts` — Embedding generation (local MiniLM or OpenAI API)
- `src/search/vector-index.ts` — Vector similarity search using sqlite-vec

**New dependencies:** `sqlite-vec` (SQLite extension), optionally `@xenova/transformers` for local embeddings

**Changes:**
- `src/search/engine.ts` — Add hybrid search path: BM25 + vector → RRF merge
- `src/config/schema.ts` — Add embedding model configuration

### Phase 9: Prometheus Metrics

**New files:**
- `src/lib/metrics.ts` — Prometheus metric definitions
- Metrics endpoint at `/metrics` in HTTP mode

**New dependency:** `prom-client`

---

## 8. Quick Reference: MCP Client Configuration

### Claude Code (stdio)

```bash
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

### Cursor / Windsurf (stdio)

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

### Initial Setup

```bash
# Clone and install
git clone <repo-url>
cd pro-context
pip install -e ".[dev]"

# Run tests
pytest

# Start in development mode (stdio)
python -m pro_context

# Test with Claude Code
claude mcp add pro-context -- python -m pro_context

# Or use uvicorn for HTTP mode with auto-reload
uvicorn pro_context.server:app --reload --port 3100
```

### Adding a New Library to the Registry

1. Edit `src/pro_context/registry/known_libraries.py`
2. Add entry with `id`, `name`, `description`, `languages`, `package_name`, `docs_url`, `repo_url`
3. Run tests: `pytest tests/unit/registry/`
4. Lint: `ruff check .`

### Adding a New Source Adapter

1. Create `src/pro_context/adapters/{name}.py` implementing `SourceAdapter` ABC
2. Implement `can_handle`, `fetch_toc`, `fetch_page`, `check_freshness` methods
3. Register in `src/pro_context/adapters/chain.py` with appropriate priority
4. Add tests in `tests/unit/adapters/test_{name}.py`
5. Add integration test if the adapter has external dependencies
6. Run full test suite: `pytest`
