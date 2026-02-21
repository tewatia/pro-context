# Pro-Context: Technical Specification

> **Document**: 03-technical-spec.md
> **Status**: Draft v2
> **Last Updated**: 2026-02-20
> **Depends on**: 02-functional-spec.md (v3)

---

## Table of Contents

- [1. System Architecture](#1-system-architecture)
  - [1.1 High-Level Architecture](#11-high-level-architecture)
  - [1.2 Request Flow](#12-request-flow)
- [2. Technology Stack](#2-technology-stack)
- [3. Data Models](#3-data-models)
  - [3.1 Core Types](#31-core-types)
  - [3.2 Cache Types](#32-cache-types)
  - [3.3 Auth Types (HTTP Mode)](#33-auth-types-http-mode)
  - [3.4 Configuration Types](#34-configuration-types)
  - [3.5 Infrastructure Protocols](#35-infrastructure-protocols)
- [4. Documentation Fetcher](#4-documentation-fetcher)
  - [4.1 Data Types](#41-data-types)
  - [4.2 Fetcher Implementation](#42-fetcher-implementation)
- [5. Cache Architecture](#5-cache-architecture)
  - [5.1 Two-Tier Cache Design](#51-two-tier-cache-design)
  - [5.2 Cache Domains](#52-cache-domains)
  - [5.3 Cache Manager](#53-cache-manager)
  - [5.4 Page Cache](#54-page-cache)
  - [5.5 Cache Key Strategy](#55-cache-key-strategy)
  - [5.6 Cache Invalidation Signals](#56-cache-invalidation-signals)
  - [5.7 Background Refresh](#57-background-refresh)
- [6. Registry Update Mechanism](#6-registry-update-mechanism)
  - [6.1 Registry Distribution Strategy](#61-registry-distribution-strategy)
  - [6.2 Local Storage](#62-local-storage)
  - [6.3 Update Detection and Download](#63-update-detection-and-download)
  - [6.4 Database Synchronization](#64-database-synchronization)
  - [6.5 Configuration](#65-configuration)
- [7. Search Engine Design](#7-search-engine-design)
  - [7.1 Document Chunking Strategy](#71-document-chunking-strategy)
  - [7.2 BM25 Search Implementation](#72-bm25-search-implementation)
  - [7.3 Cross-Library Search](#73-cross-library-search)
  - [7.4 Incremental Indexing](#74-incremental-indexing)
  - [7.5 Ranking and Token Budgeting](#75-ranking-and-token-budgeting)
- [8. Token Efficiency Strategy](#8-token-efficiency-strategy)
  - [8.1 Target Metrics](#81-target-metrics)
  - [8.2 Techniques](#82-techniques)
  - [8.3 Token Counting](#83-token-counting)
- [9. Transport Layer](#9-transport-layer)
  - [9.1 stdio Transport (Local Mode)](#91-stdio-transport-local-mode)
  - [9.2 Streamable HTTP Transport (HTTP Mode)](#92-streamable-http-transport-http-mode)
- [10. Authentication and API Key Management](#10-authentication-and-api-key-management)
  - [10.1 Key Generation](#101-key-generation)
  - [10.2 Key Validation Flow](#102-key-validation-flow)
  - [10.3 Admin CLI](#103-admin-cli)
- [11. Rate Limiting Design](#11-rate-limiting-design)
  - [11.1 Token Bucket Algorithm](#111-token-bucket-algorithm)
  - [11.2 Rate Limit Headers](#112-rate-limit-headers)
  - [11.3 Per-Key Overrides](#113-per-key-overrides)
- [12. Security Model](#12-security-model)
  - [12.1 Input Validation](#121-input-validation)
  - [12.2 SSRF Prevention](#122-ssrf-prevention)
  - [12.3 Secret Redaction](#123-secret-redaction)
  - [12.4 Content Sanitization](#124-content-sanitization)
- [13. Observability](#13-observability)
  - [13.1 Structured Logging](#131-structured-logging)
  - [13.2 Key Metrics](#132-key-metrics)
  - [13.3 Health Check](#133-health-check)
- [14. Database Schema](#14-database-schema)
  - [14.1 SQLite Tables](#141-sqlite-tables)
  - [14.2 Database Initialization](#142-database-initialization)
  - [14.3 Cleanup Job](#143-cleanup-job)
- [15. Fuzzy Matching](#15-fuzzy-matching)

---

## 1. System Architecture

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Clients                          │
│  (Claude Code, Cursor, Windsurf, VS Code, custom)      │
└──────────────┬──────────────────────┬───────────────────┘
               │ stdio (local)        │ Streamable HTTP (remote)
               ▼                      ▼
┌─────────────────────────────────────────────────────────┐
│                  Pro-Context MCP Server                  │
│                                                         │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐             │
│  │  Tools  │  │Resources │  │  Prompts   │             │
│  │  (5)    │  │  (2)     │  │  (3)       │             │
│  └────┬────┘  └────┬─────┘  └─────┬──────┘             │
│       │             │              │                     │
│  ┌────▼─────────────▼──────────────▼──────┐             │
│  │           Core Engine                   │             │
│  │                                         │             │
│  │  ┌──────────┐  ┌───────────────────┐   │             │
│  │  │ Resolver │  │  Search Engine    │   │             │
│  │  │ (lib ID) │  │  (BM25 ranking)  │   │             │
│  │  └────┬─────┘  └────────┬──────────┘   │             │
│  │       │                  │              │             │
│  │  ┌────▼──────────────────▼──────────┐   │             │
│  │  │      llms.txt Fetcher           │   │             │
│  │  │   (HTTP GET + parse llms.txt)   │   │             │
│  │  └──────────────────────────────────┘   │             │
│  │                                         │             │
│  │  ┌──────────────────────────────────┐   │             │
│  │  │         Cache Layer              │   │             │
│  │  │  ┌──────────┐  ┌─────────────┐  │   │             │
│  │  │  │ Memory   │  │   SQLite    │  │   │             │
│  │  │  │ (LRU)    │  │ (persistent)│  │   │             │
│  │  │  └──────────┘  └─────────────┘  │   │             │
│  │  └──────────────────────────────────┘   │             │
│  └─────────────────────────────────────────┘             │
│                                                         │
│  ┌──────────────────────────────────────────┐           │
│  │  Infrastructure                           │           │
│  │  ┌────────┐ ┌────────┐ ┌──────────────┐  │           │
│  │  │ Logger │ │ Errors │ │ Rate Limiter │  │           │
│  │  │(struct)│ │        │ │              │  │           │
│  │  │  log   │ │        │ │              │  │           │
│  │  └────────┘ └────────┘ └──────────────┘  │           │
│  └──────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────┘
```

### 1.2 Request Flow

```
MCP Client
  │
  ├─ resolve-library("langchain")
  │    │
  │    ├─ 1. Fuzzy match against known-libraries registry (exact pkg → ID → alias → Levenshtein)
  │    ├─ 2. If no match → return empty results (no network calls — registry only)
  │    └─ 3. Return ranked matches with { libraryId, name, languages, relevance }
  │
  ├─ get-library-info("langchain-ai/langchain")
  │    │
  │    ├─ 1. Look up libraryId in registry (exact match)
  │    ├─ 2. If not found → return LIBRARY_NOT_FOUND error
  │    ├─ 3. Fetch TOC from library.llms_txt_url via fetcher
  │    ├─ 4. Extract availableSections from TOC
  │    ├─ 5. Apply sections filter if specified
  │    ├─ 6. Cache TOC, add to session resolved list
  │    └─ 7. Return { libraryId, sources, toc, availableSections }
  │
  ├─ get-docs([{libraryId: "langchain-ai/langchain"}], "chat models")
  │    │
  │    ├─ 1. For each library: validate libraryId
  │    ├─ 2. Cache lookup: memory LRU → SQLite
  │    │    ├─ HIT (fresh) → use cached content
  │    │    ├─ HIT (stale) → use cached + trigger background refresh
  │    │    └─ MISS → continue to step 3
  │    ├─ 3. Fetch content from llmsTxtUrl via fetcher
  │    ├─ 4. Chunk raw content into sections
  │    ├─ 5. Rank chunks across all libraries by topic relevance (BM25)
  │    ├─ 6. Select top chunk(s) within maxTokens budget
  │    ├─ 7. Identify relatedPages from TOC
  │    ├─ 8. Store in cache (memory + SQLite)
  │    └─ 9. Return { libraryId, content, source, version, confidence, relatedPages }
  │
  ├─ search-docs("retry logic", libraryIds: ["langchain-ai/langchain"])
  │    │
  │    ├─ 1. Validate specified libraries exist and have indexed content
  │    ├─ 2. If no libraryIds → search across all indexed content
  │    ├─ 3. Execute BM25 query against indexed chunks
  │    ├─ 4. Rank results by relevance score
  │    └─ 5. Return top N results with { libraryId, snippet, url, relevance }
  │
  └─ read-page("https://docs.langchain.com/docs/streaming.md", offset: 0)
       │
       ├─ 1. Validate URL against allowlist
       ├─ 2. Check page cache for this URL
       │    ├─ HIT → serve from cache (apply offset/maxTokens)
       │    └─ MISS → fetch URL, convert to markdown, cache full page
       ├─ 3. Apply offset + maxTokens: return content slice
       ├─ 4. Index page content for BM25 (background)
       └─ 5. Return { content, totalTokens, offset, tokensReturned, hasMore }
```

---

## 2. Technology Stack

| Component | Technology | Version | Rationale |
|-----------|-----------|---------|-----------|
| Language | Python | 3.12+ | Latest stable, per-interpreter GIL, improved error messages, asyncio improvements |
| Package manager | `uv` (recommended) | latest | 10-100x faster than pip, built-in lock files, better dependency resolution |
| MCP SDK | `mcp` | >=1.0.0,<2.0.0 | Official SDK, maintained by protocol authors |
| Schema validation | Pydantic | >=2.9.0,<3.0.0 | Runtime validation, excellent type integration, v2 Rust core for performance |
| Persistent cache | SQLite via `aiosqlite` | >=0.20.0,<1.0.0 | Async-friendly, zero-config, embedded, no external infra |
| In-memory cache | `cachetools` | >=5.3.0,<6.0.0 | TTL support, LRU eviction, simple async-compatible usage |
| HTTP client | `httpx` | >=0.27.0,<1.0.0 | Async-first, HTTP/2 support, timeout management |
| Search/ranking | BM25 via SQLite FTS5 | — | FTS5 for indexing + custom BM25 scoring; no embedding dependency |
| Logging | `structlog` | >=24.1.0,<25.0.0 | Structured logging, context binding, processor pipelines |
| Testing | `pytest` + `pytest-asyncio` | >=8.1.0,<9.0.0 / >=0.23.0,<1.0.0 | De facto standard, excellent async support, rich plugin ecosystem |
| Linting + Format | `ruff` | >=0.3.0,<1.0.0 | Extremely fast, replaces flake8/black/isort, pyproject.toml config |
| Type checking | `mypy` | >=1.9.0,<2.0.0 | Static type analysis, strict mode enforcement |
| YAML parsing | `pyyaml` | >=6.0.1,<7.0.0 | Standard library equivalent for config parsing |
| Fuzzy matching | `rapidfuzz` | >=3.6.0,<4.0.0 | Fast Levenshtein distance, C++ backend |

**Version Pinning Strategy**: All dependencies use SemVer-compatible ranges. Lower bounds represent minimum tested versions (latest at project start). Lock files (`uv.lock` + `requirements.txt`) pin exact versions for reproducible builds. See Implementation Guide (Doc 04) for detailed dependency management workflow.

### Architectural "Not Chosen" Decisions

- **No vector database**: BM25 handles keyword-heavy documentation search well without requiring an embedding model. Vector search deferred to future phase.
- **No Redis**: SQLite provides sufficient persistence for cache. No external infrastructure needed.
- **No web framework**: MCP SDK handles HTTP transport internally (Starlette under the hood). No FastAPI/Flask needed.

---

## 3. Data Models

### 3.1 Core Types

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

# ===== Library Types =====

@dataclass
class LibraryMatch:
    """Result from resolve-library query"""
    library_id: str  # Canonical identifier (e.g., "langchain-ai/langchain")
    name: str  # Human-readable name (e.g., "LangChain")
    description: str  # Brief description
    languages: list[str]  # Languages this library is available in
    relevance: float  # Match relevance score (0-1)


@dataclass
class Library:
    """Full library metadata"""
    id: str  # Canonical identifier
    name: str  # Human-readable name
    description: str  # Brief description
    languages: list[str]  # Languages this library is available in
    package_name: str  # Package name in registry (e.g., "langchain" on PyPI)
    llms_txt_url: str  # llms.txt URL — builder guarantee: always present, always valid
    docs_url: str | None  # Documentation site URL
    repo_url: str | None  # GitHub repository URL


# ===== TOC Types =====

@dataclass
class TocEntry:
    """Single entry in library table of contents"""
    title: str  # Page title
    url: str  # Page URL (can be passed to read-page)
    description: str  # One-sentence description
    section: str  # Section grouping (e.g., "Getting Started", "API Reference")


@dataclass
class LibraryInfo:
    """Library metadata + TOC from get-library-info"""
    library_id: str
    name: str
    languages: list[str]  # Informational metadata — not used for routing/validation
    toc: list[TocEntry]  # Full or filtered TOC
    available_sections: list[str]  # All unique section names in TOC
    filtered_by_sections: list[str] | None = None  # Sections filter applied
    # Note: no `sources` field — source is always llms.txt (builder guarantee)


# ===== Documentation Types =====

@dataclass
class RelatedPage:
    """Reference to a related documentation page"""
    title: str
    url: str
    description: str


@dataclass
class DocResult:
    """Documentation content result from get-docs"""
    library_id: str  # Which library this content is from
    content: str  # Documentation content in markdown
    source: str  # URL where documentation was fetched from
    last_updated: datetime  # When documentation was last fetched/verified
    confidence: float  # Relevance confidence (0-1)
    cached: bool  # Whether result was served from cache
    stale: bool  # Whether cached content may be outdated
    related_pages: list[RelatedPage]  # Related pages the agent can explore


@dataclass
class DocChunk:
    """Indexed documentation chunk for search"""
    id: str  # Chunk identifier (hash)
    library_id: str  # Library this chunk belongs to
    title: str  # Section title/heading
    content: str  # Chunk content in markdown
    section_path: str  # Hierarchical path (e.g., "Getting Started > Chat Models")
    token_count: int  # Approximate token count
    source_url: str  # Source URL


@dataclass
class SearchResult:
    """Search result from search-docs"""
    library_id: str  # Which library this result is from
    title: str  # Section/page title
    snippet: str  # Relevant text excerpt
    relevance: float  # BM25 relevance score (0-1 normalized)
    url: str  # Source URL — use read-page to fetch full content
    section: str  # Documentation section path


# ===== Page Types =====

@dataclass
class PageResult:
    """Page content result from read-page"""
    content: str  # Page content in markdown
    title: str  # Page title
    url: str  # Canonical URL
    total_tokens: int  # Total page content length in estimated tokens
    offset: int  # Token offset this response starts from
    tokens_returned: int  # Number of tokens in this response
    has_more: bool  # Whether more content exists beyond this response
    cached: bool  # Whether page was served from cache


# ===== Error Types =====

class ErrorCode(str, Enum):
    """Error codes for ProContextError"""
    LIBRARY_NOT_FOUND = "LIBRARY_NOT_FOUND"
    TOPIC_NOT_FOUND = "TOPIC_NOT_FOUND"
    PAGE_NOT_FOUND = "PAGE_NOT_FOUND"
    URL_NOT_ALLOWED = "URL_NOT_ALLOWED"
    INVALID_CONTENT = "INVALID_CONTENT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NETWORK_FETCH_FAILED = "NETWORK_FETCH_FAILED"
    LLMS_TXT_NOT_FOUND = "LLMS_TXT_NOT_FOUND"  # llms.txt URL returns 404
    STALE_CACHE_EXPIRED = "STALE_CACHE_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_INVALID = "AUTH_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ProContextError(Exception):
    """Structured error with recovery information.

    Not a dataclass — dataclass + Exception has non-obvious behaviour in Python
    (dataclass __init__ conflicts with Exception.args). Use explicit __init__ instead.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        recoverable: bool,
        suggestion: str,
        retry_after: int | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recoverable = recoverable
        self.suggestion = suggestion
        self.retry_after = retry_after
        self.details = details
```

### 3.2 Cache Types

```python
@dataclass
class CacheEntry:
    """Entry in documentation cache (doc_cache table)"""
    key: str  # Cache key (SHA-256 hash)
    library_id: str  # Library identifier
    identifier: str  # Topic hash (for get-docs) or URL (for pages)
    content: str  # Cached content
    source_url: str  # Source URL
    content_hash: str  # Content SHA-256 hash (for freshness checking)
    fetched_at: datetime  # When this entry was created
    expires_at: datetime  # When this entry expires
    etag: str | None = None  # ETag from source (used by check_freshness for cheap HEAD comparison)
    last_modified: str | None = None  # Last-Modified from source (fallback if no ETag)


@dataclass
class PageCacheEntry:
    """Entry in page cache (page_cache table)"""
    url: str  # Page URL (cache key)
    content: str  # Full page content in markdown
    title: str  # Page title
    total_tokens: int  # Total content length in estimated tokens
    content_hash: str  # Content SHA-256 hash
    fetched_at: datetime  # When this page was fetched
    expires_at: datetime  # When this entry expires
    etag: str | None = None  # ETag from source (used by check_freshness)
    last_modified: str | None = None  # Last-Modified from source (fallback if no ETag)


@dataclass
class CacheStats:
    """Cache statistics for health check"""
    memory_entries: int  # Number of entries in memory cache
    memory_bytes: int  # Memory cache size in bytes
    sqlite_entries: int  # Number of entries in SQLite cache
    hit_rate: float  # Cache hit rate (0-1)
```

### 3.3 Auth Types (HTTP Mode)

```python
@dataclass
class ApiKey:
    """API key for HTTP authentication"""
    id: str  # Unique key identifier (UUID)
    name: str  # Display name for the key
    key_hash: str  # SHA-256 hash of the actual key (never store plaintext)
    key_prefix: str  # Key prefix for display (first 8 chars)
    rate_limit_per_minute: int | None  # Per-key rate limit (None = use default)
    created_at: datetime  # When this key was created
    last_used_at: datetime | None  # When this key was last used
    request_count: int  # Total number of requests made with this key
    active: bool  # Whether this key is active
```

### 3.4 Configuration Types

```python
from typing import Literal

@dataclass
class ServerConfig:
    """Server transport configuration"""
    transport: Literal["stdio", "http"]
    port: int
    host: str


@dataclass
class CacheConfig:
    """Cache configuration"""
    directory: str  # SQLite database directory
    max_memory_mb: int  # Memory cache size limit
    max_memory_entries: int  # Memory cache entry limit
    default_ttl_hours: int  # Default TTL for cache entries
    cleanup_interval_minutes: int  # Cleanup job interval


@dataclass
class CustomSource:
    """User-configured documentation source"""
    name: str
    type: Literal["url", "file", "github"]
    url: str | None = None
    path: str | None = None
    library_id: str
    ttl_hours: int | None = None


@dataclass
class SourcesConfig:
    """Documentation source configuration"""
    llms_txt: dict[str, bool]  # {"enabled": True}
    github: dict[str, bool | str]  # {"enabled": True, "token": "ghp_xxx"}
    custom: list[CustomSource]


@dataclass
class LibraryOverride:
    """Per-library configuration overrides"""
    docs_url: str | None = None
    source: str | None = None
    ttl_hours: int | None = None


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    max_requests_per_minute: int
    burst_size: int


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: Literal["debug", "info", "warn", "error"]
    format: Literal["json", "pretty"]


@dataclass
class SecurityConfig:
    """Security configuration"""
    cors: dict[str, list[str]]  # {"origins": ["*"]}
    url_allowlist: list[str]  # Domain patterns


@dataclass
class ProContextConfig:
    """Complete Pro-Context configuration"""
    server: ServerConfig
    cache: CacheConfig
    sources: SourcesConfig
    library_overrides: dict[str, LibraryOverride]
    rate_limit: RateLimitConfig
    logging: LoggingConfig
    security: SecurityConfig


# Note: PRO_CONTEXT_DEBUG=true env var sets logging.level to "debug"
# See functional spec section 12 for full env var override table
```

### 3.5 Infrastructure Protocols

All swappable infrastructure layers are defined as Python `Protocol` classes (PEP 544). Concrete implementations (SQLite, in-memory, etc.) satisfy these protocols via structural subtyping — no explicit inheritance required. This enables backend swaps (e.g., SQLite → PostgreSQL, in-memory → Redis) without changing any code that depends on the protocol.

**File**: `src/pro_context/protocols.py`

```python
from typing import Any, Protocol, runtime_checkable
from collections.abc import Callable

# ===== Cache Protocols =====

@runtime_checkable
class MemoryCache(Protocol):
    """In-memory cache with TTL and LRU eviction.

    Concrete implementations:
      - AsyncTTLCache (cachetools.TTLCache + asyncio.Lock) — default
      - Future: Redis-backed (shared across processes)

    Individual get/set ops are synchronous (atomic in asyncio's cooperative model).
    get_or_set is async because the fetch_fn crosses an await boundary.
    """

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any) -> None: ...
    def pop(self, key: str, default: Any = None) -> Any: ...
    async def get_or_set(self, key: str, fetch_fn: Callable) -> Any: ...


@runtime_checkable
class PersistentCache(Protocol):
    """Persistent cache backend (Tier 2).

    Concrete implementations:
      - SqliteCache (aiosqlite, WAL mode) — default
      - Future: PostgreSQL-backed (shared across instances)
    """

    async def get(self, key: str) -> CacheEntry | None: ...
    async def set(self, key: str, entry: CacheEntry) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def mark_stale(self, library_id: str) -> None: ...
    async def cleanup_expired(self) -> int: ...


@runtime_checkable
class PersistentPageCache(Protocol):
    """Persistent page cache backend (Tier 2, page-specific).

    Concrete implementations:
      - SqlitePageCache (aiosqlite) — default
      - Future: PostgreSQL-backed
    """

    async def get(self, url: str) -> PageCacheEntry | None: ...
    async def set(self, url: str, entry: PageCacheEntry) -> None: ...
    async def delete(self, url: str) -> None: ...
    async def cleanup_expired(self) -> int: ...


# ===== Rate Limiting Protocol =====

@runtime_checkable
class RateLimiter(Protocol):
    """Rate limiter for inbound request throttling.

    Concrete implementations:
      - TokenBucketRateLimiter (in-memory, per-process) — default
      - Future: Redis-backed (shared across instances, Lua script for atomicity)
    """

    async def check(self, key: str) -> "RateLimitResult": ...
    async def get_headers(self, key: str) -> dict[str, str]: ...


@dataclass
class RateLimitResult:
    """Result of a rate limit check"""
    allowed: bool  # Whether the request is allowed
    remaining: int  # Remaining requests in current window
    retry_after: int | None = None  # Seconds until next allowed request (if rejected)


# ===== Search Protocol =====

@runtime_checkable
class SearchBackend(Protocol):
    """Full-text search backend for documentation chunks.

    Concrete implementations:
      - FTS5SearchBackend (SQLite FTS5 with bm25()) — default
      - Future: PostgreSQL tsvector + GIN index
      - Future: Hybrid BM25 + vector search (Phase 8)
    """

    async def index(self, chunks: list["DocChunk"]) -> None: ...
    async def search(
        self,
        query: str,
        library_ids: list[str] | None = None,
        max_results: int = 10,
    ) -> list["SearchResult"]: ...
    async def delete_by_library(self, library_id: str) -> None: ...
    async def get_indexed_libraries(self) -> list[str]: ...


# ===== Session Store Protocol =====

@runtime_checkable
class SessionStore(Protocol):
    """Session state storage for tracking resolved libraries.

    Concrete implementations:
      - SqliteSessionStore (aiosqlite) — default
      - Future: Redis-backed (TTL-based expiry, shared across instances)
    """

    async def add(self, library_id: str, name: str, languages: list[str]) -> None: ...
    async def list_all(self) -> list[dict[str, Any]]: ...
    async def clear(self) -> None: ...


# ===== API Key Store Protocol =====

@runtime_checkable
class ApiKeyStore(Protocol):
    """API key storage and validation for HTTP mode.

    Concrete implementations:
      - SqliteApiKeyStore (aiosqlite) — default
      - Future: PostgreSQL-backed (shared across instances)
    """

    async def validate(self, key_hash: str) -> "ApiKey | None": ...
    async def create(self, name: str, rate_limit: int | None = None) -> tuple[str, "ApiKey"]: ...
    async def revoke(self, key_id: str) -> bool: ...
    async def list_keys(self) -> list["ApiKey"]: ...
    async def record_usage(self, key_id: str) -> None: ...
```

**Why `@runtime_checkable`?** Allows `isinstance(obj, MemoryCache)` checks in tests and dependency injection, without requiring concrete classes to inherit from the protocol.

**Why protocols instead of ABCs?** Protocols use structural subtyping (duck typing with type checker support). Concrete implementations don't need to import or inherit from the protocol — they just need to have the right methods. This keeps the dependency direction clean: protocols live in `protocols.py`, concrete implementations live in `cache/`, `search/`, `auth/`, etc.

---

## 4. Documentation Fetcher

**Architectural shift**: All documentation sources are normalized to llms.txt format by the builder system (see `docs/builder/` for details). The MCP server is a simple fetch-parse-cache layer with no source-specific logic.

### 4.1 Data Types

```python
@dataclass
class RawPageContent:
    """Raw page content fetched from llms.txt sources"""
    content: str  # Page content in markdown
    title: str  # Page title (extracted from first heading or URL)
    source_url: str  # Canonical source URL
    content_hash: str  # Content SHA-256 hash
    etag: str | None = None  # ETag header value (if available)
    last_modified: str | None = None  # Last-Modified header (if available)
```

### 4.2 Fetcher Implementation

```python
class LlmsTxtFetcher:
    """Simple HTTP fetcher for llms.txt files"""

    def __init__(self, http_client: httpx.AsyncClient, timeout: int = 30):
        self.client = http_client
        self.timeout = timeout

    async def fetch_toc(self, library: Library) -> list[TocEntry]:
        """Fetch TOC from llms.txt URL (guaranteed by builder)"""
        llms_txt_url = library.llms_txt_url

        try:
            response = await self.client.get(
                llms_txt_url,
                timeout=self.timeout,
                follow_redirects=True
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ProContextError(
                    code=ErrorCode.LLMS_TXT_NOT_FOUND,
                    message=f"llms.txt not found at {llms_txt_url}",
                    recoverable=False
                )
            raise ProContextError(
                code=ErrorCode.NETWORK_FETCH_FAILED,
                message=f"Failed to fetch llms.txt: {e}",
                recoverable=True
            )
        except httpx.RequestError as e:
            raise ProContextError(
                code=ErrorCode.NETWORK_FETCH_FAILED,
                message=f"Network error fetching llms.txt: {e}",
                recoverable=True
            )

        # Parse llms.txt markdown format
        return self._parse_llms_txt(response.text, llms_txt_url)

    async def fetch_page(self, url: str) -> RawPageContent:
        """Fetch a single documentation page"""
        try:
            response = await self.client.get(
                url,
                timeout=self.timeout,
                follow_redirects=True
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ProContextError(
                    code=ErrorCode.PAGE_NOT_FOUND,
                    message=f"Page not found: {url}",
                    recoverable=False
                )
            raise ProContextError(
                code=ErrorCode.NETWORK_FETCH_FAILED,
                message=f"Failed to fetch page: {e}",
                recoverable=True
            )
        except httpx.RequestError as e:
            raise ProContextError(
                code=ErrorCode.NETWORK_FETCH_FAILED,
                message=f"Network error fetching page: {e}",
                recoverable=True
            )

        content = response.text
        title = self._extract_title(content)
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        return RawPageContent(
            content=content,
            title=title,
            source_url=url,
            content_hash=content_hash,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified")
        )

    async def check_freshness(self, url: str, cached_hash: str) -> bool:
        """Check if cached content is still fresh using HEAD request"""
        try:
            response = await self.client.head(url, timeout=self.timeout)
            response.raise_for_status()

            # If ETag available, compare with cached
            etag = response.headers.get("etag")
            if etag:
                # ETag comparison requires storing ETag in cache
                # For now, we'll refetch and compare content hash
                pass

            # Last-Modified comparison
            last_modified = response.headers.get("last-modified")
            if last_modified:
                # Parse and compare timestamps
                pass

            # Fallback: Refetch and compare content hash
            full_response = await self.client.get(url, timeout=self.timeout)
            full_response.raise_for_status()
            new_hash = hashlib.sha256(full_response.text.encode()).hexdigest()
            return new_hash == cached_hash

        except (httpx.HTTPStatusError, httpx.RequestError):
            # On error, assume cache is stale (safer to refetch)
            return False

    def _parse_llms_txt(self, content: str, base_url: str) -> list[TocEntry]:
        """Parse llms.txt markdown format into TOC entries"""
        # Extract ## headings as sections, list items as entries
        # For each entry: extract title, URL, description
        # Return structured TocEntry[]
        pass  # Implementation details in Phase 2

    def _extract_title(self, markdown: str) -> str:
        """Extract title from first heading in markdown"""
        # Look for first # heading
        pass  # Implementation details in Phase 2
```

**Key simplifications from adapter architecture:**
- No adapter chain, no fallback logic, no priority ordering
- Every library in registry has a valid `llmsTxtUrl` (guaranteed by builder)
- Builder handles source-specific complexity at build time
- MCP server only deals with HTTP GET + parse llms.txt format
- Error handling is simple: HTTP errors → ProContextError

---

## 5. Cache Architecture

### 5.1 Two-Tier Cache Design

```
Query → Memory LRU (Tier 1) → SQLite (Tier 2) → llms.txt Fetcher
         │                      │                   │
         ▼                      ▼                   ▼
      <1ms latency           <10ms latency       100ms-3s latency
      500 entries max        Unlimited             Network fetch
      1hr TTL (search)       24hr TTL (default)    Stored on return
      24hr TTL (docs/pages)  Configurable/library
```

### 5.2 Cache Domains

The cache stores three types of content:

| Domain | Key | Content | TTL |
|--------|-----|---------|-----|
| **TOC** | `toc:{libraryId}` | Parsed TocEntry[] | 24 hours |
| **Docs/Chunks** | `doc:{libraryId}:{topicHash}` | BM25-matched content | 24 hours |
| **Pages** | `page:{urlHash}` | Full page markdown | 24 hours |

Pages are cached separately because they're shared across tools — `read-page` and `get-docs` both benefit from cached pages.

### 5.3 Cache Manager

**Memory cache implementation**: `cachetools.TTLCache` is not async-safe — using `threading.Lock` blocks the event loop. Instead, `src/pro_context/cache/memory.py` implements a thin `AsyncTTLCache` wrapper using `asyncio.Lock` for the check-then-set path to prevent cache stampede (concurrent coroutines all missing the same key). Individual reads (`cache.get(key)`) are safe without a lock in asyncio's cooperative scheduling model.

```python
# src/pro_context/cache/memory.py
from cachetools import TTLCache
import asyncio

class AsyncTTLCache:
    """asyncio-safe TTL+LRU cache wrapping cachetools.TTLCache.

    cachetools.TTLCache is not safe with threading.Lock in asyncio (blocks event loop).
    This wrapper uses asyncio.Lock for the miss→fetch→store path to prevent stampede.
    Individual get/set ops are atomic in asyncio (no await = no context switch).
    """

    def __init__(self, maxsize: int, ttl: int):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, key: str):
        """Read from cache — atomic in asyncio, no lock needed."""
        return self._cache.get(key)

    def set(self, key: str, value) -> None:
        """Write to cache — atomic in asyncio, no lock needed."""
        self._cache[key] = value

    def pop(self, key: str, default=None):
        return self._cache.pop(key, default)

    async def get_or_set(self, key: str, fetch_fn) -> any:
        """Fetch from cache or call fetch_fn, serializing concurrent misses."""
        if key in self._cache:                     # fast path
            return self._cache[key]
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        async with self._locks[key]:               # serialize concurrent misses
            if key in self._cache:                 # double-check after acquiring lock
                return self._cache[key]
            result = await fetch_fn()
            self._cache[key] = result
            return result


# src/pro_context/cache/manager.py
from datetime import datetime
from pro_context.protocols import MemoryCache, PersistentCache

class CacheManager:
    """Two-tier cache orchestrator: memory (Tier 1) → persistent (Tier 2) → miss.

    Depends on MemoryCache and PersistentCache protocols (Section 3.5).
    Default implementations: AsyncTTLCache (memory) + SqliteCache (persistent).
    Swappable: Redis (memory) + PostgreSQL (persistent) for multi-instance deployments.
    """

    def __init__(self, memory: MemoryCache, persistent: PersistentCache):
        self.memory = memory
        self.persistent = persistent

    async def get(self, key: str) -> CacheEntry | None:
        """Get entry from cache (memory → persistent → miss)"""
        # Tier 1: Memory (atomic get, no lock needed in asyncio)
        mem_result = self.memory.get(key)
        if mem_result and not self._is_expired(mem_result):
            return mem_result

        # Tier 2: Persistent backend
        persist_result = await self.persistent.get(key)
        if persist_result and not self._is_expired(persist_result):
            # Promote to memory cache (atomic set, no lock needed)
            self.memory.set(key, persist_result)
            return persist_result

        # Return stale entry if exists (caller decides whether to use it)
        return persist_result or mem_result or None

    async def set(self, key: str, entry: CacheEntry) -> None:
        """Write to both cache tiers"""
        self.memory.set(key, entry)
        await self.persistent.set(key, entry)

    async def invalidate(self, key: str) -> None:
        """Remove entry from both cache tiers"""
        self.memory.pop(key, None)
        await self.persistent.delete(key)

    def _is_expired(self, entry: CacheEntry) -> bool:
        return datetime.now() > entry.expires_at
```

### 5.4 Page Cache

Pages fetched by `read-page` are cached in full. Offset-based reads serve slices from the cached page without re-fetching.

```python
class PageCache:
    """Page-specific cache with offset-based slice support.

    Depends on MemoryCache and PersistentPageCache protocols (Section 3.5).
    Default implementations: AsyncTTLCache (memory) + SqlitePageCache (persistent).
    """

    def __init__(self, memory: MemoryCache, persistent: PersistentPageCache):
        self.memory = memory
        self.persistent = persistent

    async def get_page(self, url: str) -> PageCacheEntry | None:
        """Get full page from cache (same two-tier pattern as CacheManager)"""
        # Tier 1: Memory
        mem_result = self.memory.get(url)
        if mem_result and not self._is_expired(mem_result):
            return mem_result

        # Tier 2: Persistent backend
        persist_result = await self.persistent.get(url)
        if persist_result and not self._is_expired(persist_result):
            self.memory.set(url, persist_result)
            return persist_result

        return persist_result or mem_result or None

    async def get_slice(
        self, url: str, offset: int, max_tokens: int
    ) -> PageResult | None:
        """Get a slice of the page content at the given offset"""
        page = await self.get_page(url)
        if not page:
            return None

        # Estimate character positions from token counts (1 token ≈ 4 chars)
        start_char = offset * 4
        max_chars = max_tokens * 4
        slice_content = page.content[start_char : start_char + max_chars]
        tokens_returned = len(slice_content) // 4

        return PageResult(
            content=slice_content,
            title=page.title,
            url=url,
            total_tokens=page.total_tokens,
            offset=offset,
            tokens_returned=tokens_returned,
            has_more=start_char + max_chars < len(page.content),
            cached=True,
        )

    def _is_expired(self, entry: PageCacheEntry) -> bool:
        """Check if cache entry has expired"""
        return datetime.now() > entry.expires_at
```

### 5.5 Cache Key Strategy

```
TOC key:  SHA-256("toc:" + libraryId)
Doc key:  SHA-256("doc:" + libraryId + ":" + normalizedTopic)
Page key: SHA-256("page:" + url)
```

### 5.6 Cache Invalidation Signals

| Signal | Trigger | Action |
|--------|---------|--------|
| TTL expiry | Automatic | Entry marked stale; served with `stale: true` |
| SHA mismatch | Background refresh (step 2b) | Update cache entry with new content |
| ETag / Last-Modified mismatch | `check_freshness()` called during background refresh | Triggers full content re-fetch |
| Registry URL change | Registry update diff | All affected entries marked `stale = 1` |
| Manual invalidation | Admin CLI command | Delete entry from both tiers |
| Cleanup job | Scheduled (configurable interval) | Delete all expired entries from SQLite |

**`check_freshness()` call point**: During background refresh (step 2 below), the fetcher's `check_freshness()` is called first as a cheap HEAD request. If it returns `True` (cache still valid), only the `expires_at` timestamp is extended — no re-fetch needed. If it returns `False` or is unavailable, the full content is re-fetched and the SHA is compared.

### 5.7 Background Refresh

When a stale cache entry is served, a background refresh is triggered:

```
1. Return stale content immediately (with stale: true)
2. Spawn background task:
   a. Call fetcher.check_freshness(url, cached_hash)
      - Returns True (content hash matches) → extend expiresAt, done
      - Returns False or error → proceed to re-fetch
   b. Fetch fresh content from llmsTxtUrl via fetcher
   c. Compare content hash (SHA-256) with cached content_hash
   d. If changed → update cache entry with new content and hash
   e. If unchanged → update expiresAt timestamp only
```

**Handling refresh failures:**

If background refresh fails (network error, site down, 404), the server:

1. **Keeps serving stale content** with `stale: true` flag
2. **Logs warning** with error details and next retry timestamp
3. **Continues retry attempts** on subsequent requests (with exponential backoff)
4. **Maximum stale age**: 7 days (configurable)
   - After 7 days without successful refresh, cache entry is invalidated
   - Next request triggers fresh fetch (not background)
   - If fresh fetch also fails, return `SOURCE_UNAVAILABLE` error

**Agent behavior recommendations:**
- `stale: false` → content is fresh, use confidently
- `stale: true` → content may be outdated but likely still accurate; agent can choose to:
  - Use the content (most cases)
  - Show warning to user ("documentation may be outdated")
  - Skip if absolute freshness required (rare)

---

## 6. Registry Update Mechanism

**IMPORTANT**: The registry (`known-libraries.json`) is **completely independent from the pro-context package version**.

- **Registry updates** do NOT require updating the pro-context package
- **Users download new libraries** without reinstalling pro-context
- **Separate release cadence**: Registry updates weekly, code updates as-needed
- **Different versioning**: Registry uses date-based versions (`registry-v2024-02-20`), code uses semver (`v0.1.0`)

This separation allows frequent data updates without code changes.

### 6.1 Registry Distribution Strategy

**Release strategy:**
- **Code releases**: Semantic versioning (`v0.1.0`, `v0.2.0`, etc.)
- **Registry releases**: Date-based versioning (`registry-v2024-02-19`, `registry-v2024-02-26`, etc.)

**Distribution:**
- Registry hosted as GitHub Release assets on the same repository
- Each registry release includes:
  ```
  registry-v2024-02-19/
    ├── known-libraries.json          # The registry data (1-2MB)
    ├── registry_metadata.json        # Version, checksum, stats
    └── known-libraries.json.gz       # Compressed (optional, 200-300KB)
  ```

**Metadata format:**
```json
{
  "version": "registry-v2024-02-19",
  "created_at": "2024-02-19T10:00:00Z",
  "total_entries": 1247,
  "checksum": "sha256:abc123...",
  "download_url": "https://github.com/tewatia/pro-context/releases/download/registry-v2024-02-19/known-libraries.json"
}
```

**Bundled fallback:**
- Pro-context package bundles a registry snapshot at build time
- Used if local copy is missing or GitHub is unreachable
- Ensures offline functionality

### 6.2 Local Storage

**Location:** `~/.local/share/pro-context/registry/`

```
~/.local/share/pro-context/
  ├── cache.db                      # SQLite cache + search index
  └── registry/
      ├── known-libraries.json      # Current registry
      └── registry_metadata.json    # Version info
```

**Permissions:**
- Directory created on first run if it doesn't exist
- Files owned by user running pro-context
- No special permissions required

### 6.3 Update Detection and Download

**stdio mode (local):**

On startup, load the local registry from disk immediately (server is available with local/bundled data). Spawn a non-blocking background task that fetches the latest `registry_metadata.json` from GitHub. If the version differs from local, download the new registry, validate its checksum, and save to local storage. The updated registry is used on next startup. Any failures (network error, checksum mismatch) are silently ignored — the server continues with the current registry.

**HTTP mode (long-running server):**

A background task polls GitHub for registry updates every 24 hours. When a new version is detected: download it, compute the diff (entries added, removed, or with changed `llms_txt_url`), mark affected cache entries as stale in the database, then atomically swap the in-memory registry. No server restart required.

**Diff strategy:** Compare old and new registries by `library_id`. Classify each library as: added, removed, or `url_changed` (only `llms_txt_url` changes matter — they invalidate cached content). All other metadata changes are safe to apply without cache invalidation.

### 6.4 Database Synchronization

When a registry update is applied, all cache entries for libraries with changed `llms_txt_url` are marked `stale = 1` in a single batched UPDATE within a transaction. The registry version is recorded in `system_metadata`. Stale entries are served immediately (with `stale: true`) while a background refresh fetches fresh content.

**Safety guarantees:**

1. **Transaction atomicity**: If server crashes mid-update, SQLite rolls back. Old data intact.

2. **Concurrent query safety**: SQLite WAL mode allows reads during writes. No deadlocks.

3. **Content preservation**: Never delete cached data. Only mark as `stale = 1`. This preserves:
   - Search index (FTS5 content intact)
   - No cold start penalty (old data available while fetching new)
   - Graceful degradation (if new fetch fails, stale data still works)

**Edge case handling:**

| Scenario | Behavior |
|----------|----------|
| Update fails halfway | Transaction rollback, old registry still active |
| DB locked by long query | WAL mode allows concurrent access, minimal delay |
| 500 URLs change at once | Single query, ~30ms lock, all marked stale |
| Server crashes during update | Transaction rollback on startup, retry |
| New URL returns 404 | Serve stale data, retry later, log warning |
| Offline (no GitHub) | Skip update, use current registry |

### 6.5 Configuration

**config.yaml:**
```yaml
registry:
  auto_update: true                         # Check for updates automatically
  update_check_interval_seconds: 86400      # 24 hours (HTTP mode only)
  github_repo: "tewatia/pro-context"
  fallback_to_bundled: true                 # Use bundled registry if fetch fails
  storage_path: "~/.local/share/pro-context/registry"  # Local storage location

  # Optional: Override registry URL (for private registries)
  # registry_url: "https://internal.company.com/pro-context-registry.json"
```

**Manual update command:**
```bash
# Check for and download latest registry
pro-context update-registry

# For HTTP servers: triggers hot reload
# For stdio: used on next startup
```

---

## 7. Search Engine Design

All search operations go through the `SearchBackend` protocol (Section 3.5). The default implementation uses SQLite FTS5. The chunker is independent of the search backend — it produces `DocChunk` objects that any `SearchBackend` can index.

### 7.1 Document Chunking Strategy

Raw documentation is chunked into focused sections for indexing and retrieval.

**Chunking algorithm:**

```
1. Parse markdown into AST (heading-aware)
2. Split on H1/H2/H3 headings → creates section boundaries
3. For each section:
   a. Estimate token count (chars / 4 approximation)
   b. If section > 1000 tokens → split on paragraphs
   c. If section > 2000 tokens → split on sentences with 200-token overlap
   d. If section < 100 tokens → merge with next section
4. For each chunk:
   a. Assign section path (e.g., "Getting Started > Chat Models > Streaming")
   b. Compute token count
   c. Extract title from nearest heading
   d. Generate chunk ID: SHA-256(libraryId + version + sectionPath + chunkIndex)
```

**Target chunk sizes:**

| Chunk Type | Target Tokens | Min | Max |
|-----------|--------------|-----|-----|
| Section chunk | 500 | 100 | 1,000 |
| Paragraph chunk (oversized sections) | 300 | 100 | 500 |
| Code example chunk | Variable | 50 | 2,000 |

### 7.2 BM25 Search Implementation

BM25 ranking is provided by SQLite FTS5's built-in `bm25()` function. FTS5 handles tokenization, inverted index maintenance, and scoring internally. Queries use the `MATCH` operator against `search_fts`, ordered by `bm25(search_fts)`.

**Parameters** (passed as FTS5 column weights or via configuration):
- `k1 = 1.5` (term frequency saturation)
- `b = 0.75` (document length normalization)

Results are normalized to a 0–1 relevance score before returning to callers.

### 7.3 Cross-Library Search

When `search-docs` is called without `libraryIds`, it searches across all indexed content. The BM25 index contains chunks from all libraries, each tagged with their `libraryId`. Results are ranked globally — a highly relevant chunk from library A ranks above a marginally relevant chunk from library B.

The `searchedLibraries` field in the response lists which libraries had indexed content at query time, so the agent knows the search scope.

### 7.4 Incremental Indexing

Pages are indexed for BM25 as they're fetched — by `get-docs` (JIT fetch), `get-library-info` (TOC fetch), and `read-page` (page fetch). The search index grows organically as the agent uses Pro-Context. There is no upfront bulk indexing step.

### 7.5 Ranking and Token Budgeting

When returning results via `get-docs`, the system applies a token budget:

```
1. Rank all matching chunks by BM25 relevance (across all specified libraries)
2. Starting from highest-ranked chunk:
   a. Add chunk to result set
   b. Subtract chunk.tokenCount from remaining budget
   c. If budget exhausted → stop
3. If no chunks match → return TOPIC_NOT_FOUND error
4. Compute confidence score:
   - 1.0 if top chunk BM25 score > 0.8
   - Proportional to top chunk BM25 score otherwise
```

---

## 8. Token Efficiency Strategy

### 8.1 Target Metrics

**Token metrics:**

| Metric | Target | Benchmark |
|--------|--------|-----------|
| Avg tokens per response (get-docs) | <3,000 | Deepcon: 2,365 |
| Accuracy | >85% | Deepcon: 90% |
| Tokens per correct answer | <3,529 | Deepcon: 2,628 |

**Latency SLOs (P95, measured from tool call to first byte of response):**

| Tool | Cache hit | Cache miss (cold fetch) |
|------|-----------|------------------------|
| `resolve-library` | <10ms (registry in memory) | N/A — no network calls; unrecognised library returns empty result |
| `get-library-info` | <50ms (TOC from memory/SQLite) | <3s (fetcher HTTP) |
| `get-docs` | <100ms (chunks from SQLite + BM25) | <5s (fetch + chunk + index) |
| `search-docs` | <200ms (BM25 query across index) | N/A (requires prior indexing) |
| `read-page` | <50ms (page from memory/SQLite) | <3s (fetcher HTTP) |

These are the pass/fail criteria for integration and performance tests. Cold fetch latency depends on network conditions and documentation site response time; 3–5s represents a reasonable P95 for well-behaved external sources.

### 8.2 Techniques

1. **Focused chunking**: Split docs into small, self-contained sections (target: 500 tokens/chunk)
2. **Relevance ranking**: BM25 ensures only relevant chunks are returned
3. **Token budgeting**: `maxTokens` parameter caps response size (default: 5,000 for get-docs, 10,000 for read-page)
4. **Snippet generation**: `search-docs` returns snippets (~100 tokens each), not full content
5. **Section targeting**: Use heading hierarchy to find the most specific relevant section
6. **Offset-based reading**: `read-page` returns slices of large pages, avoiding re-sending content the agent has already seen
7. **TOC section filtering**: `get-library-info` with `sections` parameter returns only relevant sections of large TOCs

### 8.3 Token Counting

Approximate token count using character count / 4. This is sufficient for budgeting purposes — exact token counts are model-specific and not needed.

---

## 9. Transport Layer

### 9.1 stdio Transport (Local Mode)

```python
# src/pro_context/__main__.py
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server

async def main():
    server = Server("pro-context")

    # Register tools, resources, prompts...
    # (See implementation guide for full registration code)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )

if __name__ == "__main__":
    asyncio.run(main())
```

**Characteristics:**
- Zero configuration
- No authentication required
- Single-user (one client connection)
- Communication via stdin/stdout
- Process lifecycle managed by MCP client

### 9.2 Streamable HTTP Transport (HTTP Mode)

> **Note**: This replaces the deprecated HTTP+SSE transport from MCP spec 2024-11-05. The old `SseServerTransport` / `mcp.server.sse` is **not** used. See [MCP spec 2025-11-25 transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports.md) for the full specification.

**Streamable HTTP protocol summary:**
- Single `/mcp` endpoint supporting both `POST` (client→server messages) and `GET` (opens SSE stream for server→client)
- `DELETE /mcp` — client signals session termination (server MAY return 405 if not supported)
- `MCP-Session-Id` header — server assigns at initialization; client MUST include on all subsequent requests
- `MCP-Protocol-Version` header — client MUST include on all post-initialization requests; server MUST return 400 for unsupported versions
- FastMCP handles Streamable HTTP protocol details (session assignment, SSE framing, reconnect via `Last-Event-ID`)

```python
# src/pro_context/__main__.py (HTTP mode)
#
# Security requirements per MCP spec 2025-11-25:
#   - MUST validate Origin header on all connections → 403 if present and invalid
#     (prevents DNS rebinding attacks)
#   - SHOULD bind to 127.0.0.1 for local deployments (not 0.0.0.0)
#   - SHOULD implement authentication for all connections

import re
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import uvicorn

# FastMCP manages Streamable HTTP transport internally (Starlette under the hood).
# It handles MCP-Session-Id assignment, protocol version negotiation,
# POST/GET routing to the single MCP endpoint, and SSE stream framing.
mcp = FastMCP("pro-context")

# Register tools, resources, prompts...
# (See implementation guide for full registration code)

# Supported protocol versions (2025-03-26 included for backwards compatibility)
SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2025-11-25", "2025-03-26"})

# Allowed Origin patterns for localhost deployments.
# For remote (internet-facing) deployments: replace with allowlist of known client origins.
_LOCALHOST_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


class MCPSecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware enforcing MCP spec 2025-11-25 requirements.

    Applied before FastMCP transport sees the request.
    Order of checks: Origin → Protocol Version → Auth → Rate Limit
    """

    async def dispatch(self, request: Request, call_next):
        # 1. Origin validation — REQUIRED by MCP spec (DNS rebinding prevention).
        #    If Origin header is present and does not match allowed origins → 403.
        #    Response body is a JSON-RPC error with no id (as per spec).
        origin = request.headers.get("origin")
        if origin and not _LOCALHOST_ORIGIN.match(origin):
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32000, "message": "Forbidden: invalid Origin"}},
                status_code=403,
            )

        # 2. Protocol version validation.
        #    Absence is allowed (backwards compat — assume 2025-03-26).
        #    If present and unsupported → 400 Bad Request.
        version = request.headers.get("mcp-protocol-version")
        if version is not None and version not in SUPPORTED_PROTOCOL_VERSIONS:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32000, "message": f"Unsupported protocol version: {version}"}},
                status_code=400,
            )

        # 3. API key authentication
        if not await authenticate_request(request):
            return JSONResponse(
                {"code": "AUTH_REQUIRED", "message": "Valid API key required"},
                status_code=401,
            )

        # 4. Rate limiting
        rate_result = await rate_limit_check(request)
        if not rate_result.allowed:
            return JSONResponse(
                {"code": "RATE_LIMITED", "message": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(rate_result.retry_after)},
            )

        return await call_next(request)


# Obtain the underlying Starlette ASGI app from FastMCP.
# FastMCP.get_asgi_app() exposes the internal Starlette app for middleware wrapping.
# Note: If the SDK version changes this method name, consult FastMCP release notes.
app = mcp.get_asgi_app()

# Starlette middleware is applied in reverse order:
# last added = outermost wrapper = first to run on incoming requests.
app.add_middleware(MCPSecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.security.cors["origins"],
    allow_methods=["GET", "POST", "DELETE"],   # DELETE: session termination signal
    allow_headers=[
        "Authorization",
        "MCP-Session-Id",
        "MCP-Protocol-Version",
        "Last-Event-ID",    # For SSE stream resumption after disconnection
    ],
    expose_headers=["MCP-Session-Id"],         # Client needs to read session ID
)

uvicorn.run(
    app,
    host=config.server.host,   # "127.0.0.1" for local, "0.0.0.0" for remote
    port=config.server.port,
    log_config=None,            # Disable uvicorn default logging — use structlog
)
```

**Characteristics:**
- Streamable HTTP transport per MCP spec 2025-11-25 (single `/mcp` endpoint, POST + GET)
- Requires API key authentication
- Multi-user (concurrent connections, session-scoped via `MCP-Session-Id`)
- Shared documentation cache across all users
- Origin header validation (DNS rebinding prevention — required by MCP spec)
- Per-key rate limiting
- CORS configuration with `MCP-Session-Id` header exposure

---

## 10. Authentication and API Key Management

### 10.1 Key Generation

```
1. Generate 32 random bytes using secrets.token_bytes(32)
2. Encode as base64url → this is the API key (43 chars)
3. Compute SHA-256 hash of the key using hashlib.sha256()
4. Store only the hash + prefix (first 8 chars) in SQLite
5. Return the full key to the admin (shown once, never stored)
```

**Key format**: `pc_` prefix + 40 chars base64url = `pc_aBcDeFgH...` (43 chars total)

### 10.2 Key Validation Flow

```
1. Extract Bearer token from Authorization header
2. Compute SHA-256 hash of the provided token
3. Look up hash in api_keys table
4. If found and active → authenticated
5. If found but inactive → AUTH_INVALID
6. If not found → AUTH_INVALID
7. Update last_used_at and request_count
```

### 10.3 Admin CLI

```bash
# Create a new API key
pro-context-admin key create --name "team-dev" --rate-limit 120

# List all keys
pro-context-admin key list

# Revoke a key
pro-context-admin key revoke --id <key-id>

# Show key usage stats
pro-context-admin key stats --id <key-id>
```

The admin CLI is a separate entry point (`src/pro_context/auth/admin_cli.py`) that operates on the `ApiKeyStore` protocol (Section 3.5). Default implementation uses SQLite directly.

---

## 11. Rate Limiting Design

All rate limiting operations go through the `RateLimiter` protocol (Section 3.5). The default implementation is an in-memory token bucket. For multi-instance deployments, swap in a Redis-backed implementation satisfying the same protocol.

### 11.1 Token Bucket Algorithm

Each API key gets its own token bucket:

```
Bucket parameters:
  - capacity: config.rateLimit.burstSize (default: 10)
  - refillRate: config.rateLimit.maxRequestsPerMinute / 60 (default: 1/sec)
  - tokens: starts at capacity

On request:
  1. Compute tokens to add since last request: elapsed_seconds * refillRate
  2. Add tokens (capped at capacity)
  3. If tokens >= 1 → consume 1 token, allow request
  4. If tokens < 1 → reject with RATE_LIMITED, retryAfter = (1 - tokens) / refillRate
```

### 11.2 Rate Limit Headers

HTTP responses include rate limit headers:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1707700000
```

### 11.3 Per-Key Overrides

API keys can have custom rate limits:

```sql
-- api_keys table includes rate_limit_per_minute column
-- NULL means use default from config
SELECT rate_limit_per_minute FROM api_keys WHERE key_hash = ?;
```

### 11.4 Outbound Fetcher Rate Limiting

Inbound rate limiting (Sections 11.1–11.3) protects the server. Outbound rate limiting protects the documentation sources from being hammered.

**Per-domain concurrency cap**: The `httpx` client is configured with a connection pool limit per host (default: 5 concurrent connections). This prevents a burst of inbound requests from spawning an equal burst of outbound fetches to a single documentation site.

**Default limits:**

| Domain | Max concurrent connections | Notes |
|--------|---------------------------|-------|
| `api.github.com` | 2 | GitHub API rate limit: 60 req/hr unauthenticated, 5,000 req/hr authenticated |
| `raw.githubusercontent.com` | 5 | Raw file fetches, no rate limit but be polite |
| `*.readthedocs.io`, `*.github.io`, other doc sites | 5 | Per-host cap via httpx pool |

**GitHub API token**: If `sources.github.token` is configured, it is sent as a `Authorization: Bearer` header on all `api.github.com` requests, raising the rate limit to 5,000 req/hr.

---

## 12. Security Model

### 12.1 Input Validation

All inputs are validated at the MCP boundary using Pydantic models before any processing:

```python
from pydantic import BaseModel, Field, field_validator
import re

class LibraryInput(BaseModel):
    """Input for a single library reference"""
    library_id: str = Field(min_length=1, max_length=200)

    @field_validator('library_id')
    @classmethod
    def validate_library_id(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9\-_./]+$', v):
            raise ValueError('library_id must contain only alphanumeric, dash, underscore, dot, or slash characters')
        return v

class GetDocsInput(BaseModel):
    """Input schema for get-docs tool"""
    libraries: list[LibraryInput] = Field(min_length=1, max_length=10)
    topic: str = Field(min_length=1, max_length=500)
    max_tokens: int = Field(default=5000, ge=500, le=10000)

class ReadPageInput(BaseModel):
    """Input schema for read-page tool"""
    url: str = Field(max_length=2000)
    max_tokens: int = Field(default=10000, ge=500, le=50000)
    offset: int = Field(default=0, ge=0)

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError('url must be a valid URL')
        return v
```

### 12.2 SSRF Prevention

URL fetching is restricted to known documentation domains:

```python
from urllib.parse import urlparse
import fnmatch
import ipaddress

DEFAULT_ALLOWLIST = [
    "github.com",
    "raw.githubusercontent.com",
    "*.readthedocs.io",
    "*.github.io",
]

def is_allowed_url(url: str, allowlist: list[str]) -> bool:
    """Check if URL is allowed based on domain allowlist"""
    parsed = urlparse(url)

    # Block file:// URLs
    if parsed.scheme == "file":
        return False

    # Block private IP addresses
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback:
            return False
    except ValueError:
        # Not an IP address, continue with domain check
        pass

    # Check against allowlist with wildcard matching
    return any(fnmatch.fnmatch(parsed.hostname, pattern) for pattern in allowlist)
```

- No fetching of private IPs (127.0.0.1, 10.x, 192.168.x, etc.)
- No fetching of file:// URLs
- URLs must come from resolved TOCs, search results, relatedPages, or configured allowlist
- Custom sources in config are added to the allowlist
- **Dynamic expansion**: When an llms.txt file is fetched, all URLs in it are added to the session allowlist

**Redirect validation**: `httpx` must be configured with `follow_redirects=False`. Redirects are handled manually: the redirect target URL is passed through `is_allowed_url()` before following. A redirect to a private IP or non-allowlisted domain is rejected with `URL_NOT_ALLOWED`, even if the original URL passed the check. Maximum redirect depth: 3.

### 12.3 Secret Redaction

structlog logger is configured with processor pipelines for secret redaction:

```python
import structlog

def redact_secrets(logger, method_name, event_dict):
    """Processor to redact sensitive fields"""
    sensitive_keys = {
        "authorization", "api_key", "apiKey", "token",
        "password", "secret", "key_hash"
    }

    def redact_dict(d):
        if not isinstance(d, dict):
            return d
        return {
            k: "[REDACTED]" if k.lower() in sensitive_keys else redact_dict(v)
            for k, v in d.items()
        }

    return redact_dict(event_dict)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_secrets,  # Custom redaction processor
        structlog.processors.JSONRenderer(),
    ],
)
```

### 12.4 Content Sanitization

Documentation content is treated as untrusted text:

- No `eval()` or dynamic `import()` of documentation content
- All content is fetched as plain text markdown (llms.txt format)
- No execution of code examples
- Content stored in SQLite uses parameterized queries (no SQL injection)

---

## 13. Observability

### 13.1 Structured Logging

Every request produces a structured log entry:

```json
{
  "level": "info",
  "time": "2026-02-16T10:00:00.000Z",
  "correlationId": "abc-123-def",
  "tool": "get-docs",
  "libraries": ["langchain-ai/langchain"],
  "topic": "chat models",
  "cacheHit": true,
  "cacheTier": "memory",
  "stale": false,
  "duration": 3,
  "tokenCount": 1250,
  "status": "success"
}
```

### 13.2 Key Metrics

| Metric | Description | Exposed Via |
|--------|-------------|-------------|
| Cache hit rate | % of requests served from cache | health resource |
| Cache tier distribution | memory vs SQLite vs miss | health resource |
| Fetcher success rate | % of successful HTTP fetches | health resource |
| Average latency | Per-tool response time | logs |
| Avg tokens per response | Token efficiency tracking | logs |
| Error rate | % of requests returning errors | health resource |
| Rate limit rejections | Count of rate-limited requests | logs |

### 13.3 Health Check

The `pro-context://health` resource returns:

```json
{
  "status": "healthy | degraded | unhealthy",
  "uptime": 3600,
  "cache": { "memoryEntries": 142, "memoryBytes": 52428800, "sqliteEntries": 1024, "hitRate": 0.87 },
  "fetcher": {
    "status": "available",
    "lastSuccess": "2026-02-20T10:30:00Z",
    "errorCount": 0,
    "successRate": 0.98
  },
  "version": "1.0.0"
}
```

Status determination:
- `healthy`: Fetcher working, cache functional, hit rate > 80%
- `degraded`: Fetcher experiencing errors, or cache hit rate < 50%
- `unhealthy`: Fetcher completely failing, or cache corrupted

---

## 14. Database Schema

This section documents the **default SQLite schema**. The concrete SQLite classes (`SqliteCache`, `SqlitePageCache`, `SqliteSessionStore`, `SqliteApiKeyStore`, `FTS5SearchBackend`) implement the protocols defined in Section 3.5. Alternative backends (PostgreSQL, Redis) implement the same protocols with their own storage schemas.

### 14.1 SQLite Tables

```sql
-- Documentation cache (chunks from get-docs)
CREATE TABLE IF NOT EXISTS doc_cache (
  key TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,
  identifier TEXT NOT NULL,
  content TEXT NOT NULL,
  source_url TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  etag TEXT,                      -- ETag header from source (NULL if not provided)
  last_modified TEXT,             -- Last-Modified header from source (NULL if not provided)
  fetched_at TEXT NOT NULL,       -- ISO 8601
  expires_at TEXT NOT NULL,       -- ISO 8601
  stale INTEGER NOT NULL DEFAULT 0, -- 1 if registry URL changed, requires background refresh
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_doc_cache_library ON doc_cache(library_id);
CREATE INDEX IF NOT EXISTS idx_doc_cache_expires ON doc_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_doc_cache_stale ON doc_cache(stale) WHERE stale = 1;

-- Page cache (full pages from read-page)
CREATE TABLE IF NOT EXISTS page_cache (
  url_hash TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  total_tokens INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  etag TEXT,                      -- ETag header from source (NULL if not provided)
  last_modified TEXT,             -- Last-Modified header from source (NULL if not provided)
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  stale INTEGER NOT NULL DEFAULT 0, -- 1 if registry URL changed, requires background refresh
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_page_cache_expires ON page_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_page_cache_stale ON page_cache(stale) WHERE stale = 1;

-- TOC cache
CREATE TABLE IF NOT EXISTS toc_cache (
  key TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,
  toc_json TEXT NOT NULL,          -- JSON array of TocEntry
  available_sections TEXT NOT NULL, -- JSON array of section names
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  stale INTEGER NOT NULL DEFAULT 0 -- 1 if registry URL changed, requires background refresh
);

CREATE INDEX IF NOT EXISTS idx_toc_cache_library ON toc_cache(library_id);
CREATE INDEX IF NOT EXISTS idx_toc_cache_stale ON toc_cache(stale) WHERE stale = 1;

-- Search index (BM25 term index)
CREATE TABLE IF NOT EXISTS search_chunks (
  id TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  section_path TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  source_url TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_search_chunks_library ON search_chunks(library_id);

-- FTS5 virtual table for full-text search (wraps search_chunks)
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
  title,
  content,
  section_path,
  content='search_chunks',
  content_rowid='rowid',
  tokenize='porter unicode61'
);

-- FTS5 sync triggers (required for external content mode)
-- Without these, search_fts index will NOT update when search_chunks changes.
CREATE TRIGGER IF NOT EXISTS search_chunks_ai AFTER INSERT ON search_chunks BEGIN
  INSERT INTO search_fts(rowid, title, content, section_path)
  VALUES (new.rowid, new.title, new.content, new.section_path);
END;

CREATE TRIGGER IF NOT EXISTS search_chunks_ad AFTER DELETE ON search_chunks BEGIN
  INSERT INTO search_fts(search_fts, rowid, title, content, section_path)
  VALUES ('delete', old.rowid, old.title, old.content, old.section_path);
END;

CREATE TRIGGER IF NOT EXISTS search_chunks_au AFTER UPDATE ON search_chunks BEGIN
  INSERT INTO search_fts(search_fts, rowid, title, content, section_path)
  VALUES ('delete', old.rowid, old.title, old.content, old.section_path);
  INSERT INTO search_fts(rowid, title, content, section_path)
  VALUES (new.rowid, new.title, new.content, new.section_path);
END;

-- API keys (HTTP mode only)
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  key_prefix TEXT NOT NULL,
  rate_limit_per_minute INTEGER,    -- NULL = use default
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_used_at TEXT,
  request_count INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);

-- Session state (resolved libraries in current session)
-- Session = one MCP client connection lifetime.
-- stdio mode: table is cleared on server startup (each process is one session).
-- HTTP mode: table is cleared per MCP session (scoped to the MCP-Session-Id lifetime).
-- Purpose: allows tools to know which libraries have already been resolved in this
--   session without the agent having to re-call resolve-library.
-- Cleared by: DELETE FROM session_libraries at process start (stdio) or
--   on MCP session teardown / expiry (HTTP mode).
CREATE TABLE IF NOT EXISTS session_libraries (
  library_id TEXT NOT NULL PRIMARY KEY,
  name TEXT NOT NULL,
  languages TEXT NOT NULL,           -- JSON array (informational metadata)
  resolved_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- System metadata (registry version, etc.)
CREATE TABLE IF NOT EXISTS system_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Initialize with registry version
INSERT OR IGNORE INTO system_metadata (key, value)
VALUES ('registry_version', 'bundled');  -- Updated on first registry load
```

### 14.2 Database Initialization

```python
import aiosqlite

async def initialize_database(db: aiosqlite.Connection) -> None:
    """Initialize SQLite database with pragmas and tables"""
    await db.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
    await db.execute("PRAGMA busy_timeout = 5000")  # 5s timeout
    await db.execute("PRAGMA synchronous = NORMAL")  # Durability vs performance
    await db.execute("PRAGMA foreign_keys = ON")

    # Run CREATE TABLE statements...
    # (See section 14.1 for full schema)
    await db.commit()
```

### 14.3 Cleanup Job

```python
from datetime import datetime

async def cleanup_expired_entries(db: aiosqlite.Connection) -> None:
    """Remove expired cache entries"""
    now = datetime.now().isoformat()

    await db.execute("DELETE FROM doc_cache WHERE expires_at < ?", (now,))
    await db.execute("DELETE FROM page_cache WHERE expires_at < ?", (now,))
    await db.execute("DELETE FROM toc_cache WHERE expires_at < ?", (now,))
    await db.commit()
    # FTS5 content sync handled by triggers
```

The cleanup job runs on the configured interval (`cache.cleanup_interval_minutes`, default: 60 minutes).

---

## 15. Fuzzy Matching

Library name resolution uses Levenshtein distance for fuzzy matching via `rapidfuzz`:

```python
import re
from rapidfuzz import fuzz

def find_closest_matches(query: str, candidates: list[Library]) -> list[LibraryMatch]:
    """Find library matches using fuzzy string matching"""
    normalized = re.sub(r"[^a-z0-9]", "", query.lower())
    results: list[LibraryMatch] = []

    for candidate in candidates:
        normalized_name = re.sub(r"[^a-z0-9]", "", candidate.name.lower())
        normalized_id = re.sub(r"[^a-z0-9]", "", candidate.id.lower())

        # Use rapidfuzz for fast Levenshtein distance
        name_dist = fuzz.distance(normalized, normalized_name)
        id_dist = fuzz.distance(normalized, normalized_id)
        best_dist = min(name_dist, id_dist)

        # Threshold scales with query length: allow up to 20% edit distance,
        # minimum threshold of 1 (for very short queries), maximum of 4.
        # Avoids negative relevance and false positives on short strings.
        max_allowed = max(1, min(4, len(normalized) // 5))
        if best_dist <= max_allowed:
            # Normalise against the longer of the two strings to keep score in [0, 1]
            max_len = max(len(normalized), len(normalized_name), len(normalized_id), 1)
            relevance = 1.0 - (best_dist / max_len)
            results.append(
                LibraryMatch(
                    library_id=candidate.id,
                    name=candidate.name,
                    description=candidate.description,
                    languages=candidate.languages,
                    relevance=relevance,
                )
            )

    return sorted(results, key=lambda x: x.relevance, reverse=True)
```

This handles common typos like "langchan" → "langchain", "fasapi" → "fastapi", "pydanctic" → "pydantic". Returns all matches ranked by relevance, not just the best one.
