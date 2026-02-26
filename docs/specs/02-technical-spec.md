# ProContext: Technical Specification

> **Document**: 02-technical-spec.md
> **Status**: Draft v1
> **Last Updated**: 2026-02-23
> **Depends on**: 01-functional-spec.md

---

## Table of Contents

- [1. System Architecture](#1-system-architecture)
  - [1.1 Component Overview](#11-component-overview)
  - [1.2 Request Flow](#12-request-flow)
- [2. Technology Stack](#2-technology-stack)
- [3. Data Models](#3-data-models)
  - [3.1 Registry Models](#31-registry-models)
  - [3.2 Cache Models](#32-cache-models)
  - [3.3 Tool Input/Output Models](#33-tool-inputoutput-models)
  - [3.4 Error Model](#34-error-model)
- [4. Library Resolution](#4-library-resolution)
  - [4.1 In-Memory Indexes](#41-in-memory-indexes)
  - [4.2 Resolution Algorithm](#42-resolution-algorithm)
  - [4.3 Fuzzy Matching](#43-fuzzy-matching)
  - [4.4 Query Normalisation](#44-query-normalisation)
- [5. Documentation Fetcher](#5-documentation-fetcher)
  - [5.1 HTTP Client](#51-http-client)
  - [5.2 SSRF Prevention](#52-ssrf-prevention)
  - [5.3 Redirect Handling](#53-redirect-handling)
- [6. Cache](#6-cache)
  - [6.1 SQLite Schema](#61-sqlite-schema)
  - [6.2 Stale-While-Revalidate](#62-stale-while-revalidate)
- [7. Heading Parser](#7-heading-parser)
  - [7.1 Algorithm](#71-algorithm)
- [8. Transport Layer](#8-transport-layer)
  - [8.1 stdio Transport](#81-stdio-transport)
  - [8.2 HTTP Transport](#82-http-transport)
- [9. Registry Updates](#9-registry-updates)
- [10. Configuration](#10-configuration)
- [11. Logging](#11-logging)

---

## 1. System Architecture

### 1.1 Component Overview

```
┌─────────────────────────────────────────────────────┐
│                 MCP Client                          │
│  (Claude Code, Cursor, Windsurf, custom)            │
└──────────────┬──────────────────┬───────────────────┘
               │ stdio            │ Streamable HTTP
               ▼                  ▼
┌─────────────────────────────────────────────────────┐
│              ProContext MCP Server                  │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  Tools                                       │   │
│  │  resolve_library │ get_library_docs │ read_page│  │
│  └────────────────────────┬─────────────────────┘   │
│                           │                         │
│  ┌────────────────────────▼─────────────────────┐   │
│  │  Core                                        │   │
│  │  ┌──────────────┐  ┌────────────────────┐   │   │
│  │  │  Resolver    │  │  Fetcher           │   │   │
│  │  │  (in-memory) │  │  (httpx + SSRF)    │   │   │
│  │  └──────────────┘  └─────────┬──────────┘   │   │
│  │                              │              │   │
│  │  ┌───────────────────────────▼──────────┐   │   │
│  │  │  Cache (SQLite, WAL mode)            │   │   │
│  │  └──────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  Infrastructure                               │   │
│  │  Config │ Logger │ Errors │ Registry Loader   │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 1.2 Request Flow

```
resolve_library("langchain-openai>=0.3")
  │
  ├─ Normalise: strip version/extras → "langchain-openai" → lowercase
  ├─ Index 1 (package → ID): "langchain-openai" → "langchain"  ✓
  └─ Return [{ library_id: "langchain", matched_via: "package_name", relevance: 1.0 }]

get_library_docs("langchain")
  │
  ├─ Registry lookup: "langchain" → llms_txt_url
  ├─ Cache check: toc:langchain
  │    HIT (fresh)  → return cached content
  │    HIT (stale)  → return cached content + trigger background refresh
  │    MISS         → continue
  ├─ Fetch: HTTP GET llms_txt_url (30s timeout, SSRF validated)
  ├─ Store: toc_cache (TTL 24h)
  └─ Return: { content: "<raw llms.txt markdown>" }

read_page("https://docs.langchain.com/concepts/streaming.md")
  │
  ├─ SSRF check: domain in allowlist?
  ├─ Cache check: page:{sha256(url)}
  │    HIT (fresh)  → parse headings from cached content → return
  │    HIT (stale)  → return + trigger background refresh
  │    MISS         → continue
  ├─ Fetch: HTTP GET url (30s timeout, SSRF validated per redirect)
  ├─ Store: page_cache (TTL 24h)
  ├─ Parse: extract headings (code-block-aware, H1–H4, line numbers, deduplicated anchors)
  └─ Return: { headings: [...], content: "..." }
```

---

## 2. Technology Stack

| Component          | Choice                | Version | Rationale                                                                     |
| ------------------ | --------------------- | ------- | ----------------------------------------------------------------------------- |
| Language           | Python                | 3.12+   | Modern asyncio, improved error messages, per-interpreter GIL                  |
| Package manager    | uv                    | latest  | Fast installs, lock files, `uvx` for tool distribution                        |
| MCP framework      | FastMCP (mcp package) | ≥1.26   | Official Python MCP SDK; handles protocol, tool registration, transport       |
| HTTP client        | httpx                 | ≥0.28   | Async-native, connection pooling, manual redirect control (required for SSRF) |
| SQLite driver      | aiosqlite             | ≥0.19   | Async wrapper over sqlite3; WAL mode for concurrent reads                     |
| Data validation    | pydantic v2           | ≥2.5    | Fast validation, settings management, serialisation                           |
| Fuzzy matching     | rapidfuzz             | ≥3.6    | C extension, Levenshtein distance for resolve_library fuzzy step              |
| Logging            | structlog             | ≥24.1   | Structured JSON logs; context binding per request                             |
| Config             | pydantic-settings     | ≥2.2    | YAML config with env var overrides, validated at startup                      |
| Config parsing     | pyyaml                | ≥6.0    | YAML parser required by pydantic-settings `YamlConfigSettingsSource`          |
| ASGI server        | uvicorn               | ≥0.34   | HTTP transport for Phase 4; ASGI lifespan support                             |
| Linting/formatting | ruff                  | ≥0.11   | Single tool for lint + format, replaces flake8/black/isort                    |

---

## 3. Data Models

All models use pydantic v2. Models are defined in the `src/procontext/models/` package, split by domain (`registry.py`, `cache.py`, `tools.py`). All public models are re-exported from `models/__init__.py` so callers can import from either `procontext.models` or the specific submodule.

### 3.1 Registry Models

```python
from pydantic import BaseModel, field_validator

class RegistryPackages(BaseModel):
    pypi: list[str] = []
    npm: list[str] = []

class RegistryEntry(BaseModel):
    """Single entry in known-libraries.json"""
    id: str
    name: str
    docs_url: str | None = None
    repo_url: str | None = None
    languages: list[str] = []
    packages: RegistryPackages = RegistryPackages()
    aliases: list[str] = []
    llms_txt_url: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", v):
            raise ValueError(f"Invalid library ID: {v!r}")
        return v

class LibraryMatch(BaseModel):
    """Single result from resolve_library"""
    library_id: str
    name: str
    languages: list[str]
    docs_url: str | None
    matched_via: str          # "package_name" | "library_id" | "alias" | "fuzzy"
    relevance: float          # 0.0–1.0
```

### 3.2 Cache Models

```python
from datetime import datetime
from pydantic import BaseModel

class TocCacheEntry(BaseModel):
    library_id: str
    llms_txt_url: str
    content: str              # Raw llms.txt markdown
    fetched_at: datetime
    expires_at: datetime
    stale: bool = False

class PageCacheEntry(BaseModel):
    url: str
    url_hash: str             # SHA-256 of url (primary key)
    content: str              # Full page markdown
    headings: str             # Plain-text heading map: "<line>: <heading>\n..."
    fetched_at: datetime
    expires_at: datetime
    stale: bool = False
```

### 3.3 Tool Input/Output Models

```python
class ResolveLibraryInput(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        if len(v) > 500:
            raise ValueError("query must not exceed 500 characters")
        return v

class ResolveLibraryOutput(BaseModel):
    matches: list[LibraryMatch]

class GetLibraryDocsInput(BaseModel):
    library_id: str

    @field_validator("library_id")
    @classmethod
    def validate_library_id(cls, v: str) -> str:
        import re
        v = v.strip()
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", v):
            raise ValueError(f"Invalid library ID: {v!r}")
        return v

class GetLibraryDocsOutput(BaseModel):
    library_id: str
    name: str
    content: str              # Raw llms.txt markdown
    cached: bool
    cached_at: datetime | None
    stale: bool = False

class ReadPageInput(BaseModel):
    url: str
    offset: int = 1
    limit: int = 2000

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 2048:
            raise ValueError("url must not exceed 2048 characters")
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must use http or https scheme")
        return v

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 1:
            raise ValueError("offset must be >= 1")
        return v

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v < 1:
            raise ValueError("limit must be >= 1")
        return v

class ReadPageOutput(BaseModel):
    url: str
    headings: str             # Plain-text heading map: "<line>: <heading>\n..."
    total_lines: int
    offset: int
    limit: int
    content: str              # Page markdown for the requested window
    cached: bool
    cached_at: datetime | None
    stale: bool = False
```

### 3.4 Error Model

```python
from enum import StrEnum
from pydantic import BaseModel

class ErrorCode(StrEnum):
    LIBRARY_NOT_FOUND     = "LIBRARY_NOT_FOUND"
    LLMS_TXT_FETCH_FAILED = "LLMS_TXT_FETCH_FAILED"
    PAGE_NOT_FOUND        = "PAGE_NOT_FOUND"
    PAGE_FETCH_FAILED     = "PAGE_FETCH_FAILED"
    URL_NOT_ALLOWED       = "URL_NOT_ALLOWED"
    INVALID_INPUT         = "INVALID_INPUT"

class ProContextError(Exception):
    """Base exception for all ProContext errors.

    Raised by tool handlers and caught by the MCP framework layer,
    which serialises it into the MCP error response format.
    """
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        suggestion: str,
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestion = suggestion
        self.recoverable = recoverable

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "suggestion": self.suggestion,
                "recoverable": self.recoverable,
            }
        }
```

---

## 4. Library Resolution

### 4.1 In-Memory Indexes

Loaded from `known-libraries.json` at startup. Three Python dicts rebuilt in a single pass (<100ms for 1,000 entries):

```python
@dataclass
class RegistryIndexes:
    # Index 1: package name (lowercase) → library ID
    # Many-to-one: "langchain-openai", "langchain-core" → "langchain"
    by_package: dict[str, str]

    # Index 2: library ID (lowercase) → full RegistryEntry
    by_id: dict[str, RegistryEntry]

    # Index 3: flat list of (term, library_id) for fuzzy matching
    # Populated from: all IDs + all package names + all aliases (lowercased)
    fuzzy_corpus: list[tuple[str, str]]

def build_indexes(entries: list[RegistryEntry]) -> RegistryIndexes:
    by_package: dict[str, str] = {}
    by_id: dict[str, RegistryEntry] = {}
    fuzzy_corpus: list[tuple[str, str]] = []

    for entry in entries:
        by_id[entry.id] = entry
        fuzzy_corpus.append((entry.id, entry.id))

        for pkg in entry.packages.pypi + entry.packages.npm:
            by_package[pkg.lower()] = entry.id
            fuzzy_corpus.append((pkg.lower(), entry.id))

        for alias in entry.aliases:
            fuzzy_corpus.append((alias.lower(), entry.id))

    return RegistryIndexes(
        by_package=by_package,
        by_id=by_id,
        fuzzy_corpus=fuzzy_corpus,
    )
```

### 4.2 Resolution Algorithm

Five steps in priority order. Returns on the first hit.

```
Step 0: Normalise query (see Section 4.4)

Step 1: Exact package match
        indexes.by_package.get(normalised)
        "langchain-openai" → "langchain"  ✓

Step 2: Exact ID match
        indexes.by_id.get(normalised)
        "langchain" → RegistryEntry  ✓

Step 3: Alias match
        Linear scan of fuzzy_corpus for exact string equality
        "lang-chain" → "langchain"  ✓

Step 4: Fuzzy match (Levenshtein)
        rapidfuzz.process.extract against fuzzy_corpus terms
        "langchan" → "langchain" (distance 1)  ✓
        Returns ALL matches above threshold, ranked by relevance

Step 5: No match → return empty list
```

### 4.3 Fuzzy Matching

```python
from rapidfuzz import process, fuzz

def fuzzy_search(
    query: str,
    corpus: list[tuple[str, str]],  # (term, library_id)
    limit: int = 5,
) -> list[LibraryMatch]:
    terms = [term for term, _ in corpus]
    results = process.extract(
        query,
        terms,
        scorer=fuzz.ratio,
        limit=limit,
        score_cutoff=70,          # Reject matches below 70% similarity
    )

    seen: set[str] = set()
    matches: list[LibraryMatch] = []

    for term, score, idx in results:
        _, library_id = corpus[idx]
        if library_id in seen:    # Deduplicate: one result per library
            continue
        seen.add(library_id)
        matches.append(
            LibraryMatch(
                library_id=library_id,
                relevance=round(score / 100, 2),
                matched_via="fuzzy",
                # ... other fields from by_id lookup
            )
        )

    return sorted(matches, key=lambda m: m.relevance, reverse=True)
```

**Score cutoff rationale**: 70% rejects clearly wrong matches while catching common typos (`"fastapi"` → `"fasapi"`, `"langchain"` → `"langchan"`). Exact matches in steps 1–3 always score `1.0`.

### 4.4 Query Normalisation

Applied before every resolution attempt:

```python
import re

def normalise_query(raw: str) -> str:
    # 1. Strip pip extras:      "package[extra1,extra2]" → "package"
    query = re.sub(r"\[.*?\]", "", raw)

    # 2. Strip version specs:   "package>=1.0,<2.0" → "package"
    query = re.sub(r"[><=!~^].+", "", query)

    # 3. Lowercase
    query = query.lower()

    # 4. Trim whitespace
    query = query.strip()

    return query
```

---

## 5. Documentation Fetcher

All network I/O goes through a single `Fetcher` instance shared across tool calls. Defined in `src/procontext/fetcher.py`.

### 5.1 HTTP Client

```python
import httpx

def build_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        follow_redirects=False,       # Manual redirect handling (SSRF requirement)
        timeout=httpx.Timeout(30.0),  # 30s total; applies to connect + read
        headers={"User-Agent": "procontext/1.0"},
        limits=httpx.Limits(
            max_connections=10,
            max_keepalive_connections=5,
        ),
    )
```

The client is created once at startup and closed on shutdown. It is never re-created per request.

### 5.2 SSRF Prevention

The SSRF allowlist is built at startup from the loaded registry. In HTTP mode, if a background registry update succeeds, a new allowlist is rebuilt from the updated registry and swapped in-memory together with the new indexes. It stores **base domains** (the last two DNS labels: `langchain.com`, `pydantic.dev`) rather than exact hostnames. This allows any subdomain of a registered documentation domain — including subdomains not explicitly listed in the registry — to be fetched by `read_page`.

```python
from urllib.parse import urlparse
import ipaddress

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

def _base_domain(hostname: str) -> str:
    """Return the last two DNS labels: 'api.langchain.com' → 'langchain.com'."""
    parts = hostname.rstrip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else hostname

def build_allowlist(entries: list[RegistryEntry]) -> frozenset[str]:
    base_domains: set[str] = set()
    for entry in entries:
        for url in [entry.llms_txt_url, entry.docs_url]:
            if url:
                hostname = urlparse(url).hostname or ""
                if hostname:
                    base_domains.add(_base_domain(hostname))
    return frozenset(base_domains)

def is_url_allowed(url: str, allowlist: frozenset[str]) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Block private IPs unconditionally
    try:
        addr = ipaddress.ip_address(hostname)
        if any(addr in net for net in PRIVATE_NETWORKS):
            return False
    except ValueError:
        pass  # hostname is a domain name, not an IP — proceed to allowlist check

    return _base_domain(hostname) in allowlist
```

**Known limitation**: Two-label base domain extraction is a simplification of proper eTLD+1 calculation. For shared hosting platforms like `github.io` or `readthedocs.io`, the base domain would be `github.io` or `readthedocs.io` — permitting all projects hosted there, not just the registered library. This is an acceptable trade-off for v1; a future version could adopt the `tldextract` library for accurate Public Suffix List-based matching.

### 5.3 Redirect Handling

Each redirect hop is individually validated before following:

```python
async def fetch(
    self,
    url: str,
    allowlist: frozenset[str],
    max_redirects: int = 3,
) -> httpx.Response:
    current_url = url

    for hop in range(max_redirects + 1):
        if not is_url_allowed(current_url, allowlist):
            raise ProContextError(
                code=ErrorCode.URL_NOT_ALLOWED,
                message=f"URL not in allowlist: {current_url}",
                suggestion="Only URLs from known documentation domains are permitted.",
                recoverable=False,
            )

        response = await self.client.get(current_url)

        if response.is_redirect:
            if hop == max_redirects:
                raise ProContextError(
                    code=ErrorCode.PAGE_FETCH_FAILED,
                    message=f"Too many redirects fetching {url}",
                    suggestion="The documentation URL has an unusually long redirect chain.",
                    recoverable=False,
                )
            current_url = str(response.next_request.url)
            continue

        return response

    raise ProContextError(  # unreachable but satisfies type checker
        code=ErrorCode.PAGE_FETCH_FAILED,
        message="Redirect loop",
        suggestion="",
        recoverable=False,
    )
```

---

## 6. Cache

### 6.1 SQLite Schema

Single database at `<data_dir>/cache.db` (where `<data_dir>` is the platform-specific data directory resolved by `platformdirs.user_data_dir("procontext")`). WAL mode is set once at connection time and persists — it does not need to be re-applied on subsequent opens.

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS toc_cache (
    library_id   TEXT PRIMARY KEY,
    llms_txt_url TEXT NOT NULL,
    content      TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,   -- ISO 8601
    expires_at   TEXT NOT NULL    -- ISO 8601
);

CREATE TABLE IF NOT EXISTS page_cache (
    url_hash    TEXT PRIMARY KEY,             -- SHA-256(url)
    url         TEXT NOT NULL UNIQUE,
    content     TEXT NOT NULL,
    headings    TEXT NOT NULL DEFAULT '',     -- Plain-text heading map
    fetched_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_toc_expires   ON toc_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_page_expires  ON page_cache(expires_at);
```

**Why TEXT for timestamps**: SQLite has no native datetime type. ISO 8601 strings (`"2026-02-23T10:00:00Z"`) sort lexicographically as datetimes, making range queries on `expires_at` correct without any conversion.

**Cleanup**: A periodic task (runs at startup and every 6 hours thereafter) deletes entries where `expires_at < now() - 7 days`. Stale entries are kept up to 7 days to allow stale-while-revalidate to function even if the source is temporarily unreachable.

### 6.2 Stale-While-Revalidate

```python
async def get_toc(self, library_id: str) -> TocCacheEntry | None:
    entry = await self.db.fetch_toc(library_id)
    if entry is None:
        return None
    if entry.expires_at < datetime.now(UTC):
        entry.stale = True
        asyncio.create_task(self._refresh_toc(library_id))  # background
    return entry

async def _refresh_toc(self, library_id: str) -> None:
    log = structlog.get_logger().bind(tool="get_library_docs", library_id=library_id)
    try:
        content = await self.fetcher.fetch_text(llms_txt_url, self.allowlist)
        await self.db.upsert_toc(library_id, content, ttl_hours=24)
        log.info("stale_refresh_complete", key=f"toc:{library_id}")
    except Exception:
        # Non-fatal: stale content continues to be served; retry on next request.
        # exc_info=True captures the full traceback — required for suppressed exceptions.
        log.warning("stale_refresh_failed", key=f"toc:{library_id}", exc_info=True)
```

The same pattern applies to `page_cache`. The agent always gets a response immediately — a background `asyncio.create_task` handles the refresh without blocking.

**Why `except Exception` and not `except ProContextError`**: Background refresh failures include both expected errors (`ProContextError` — e.g., fetch failed, URL not allowed) and unexpected ones (network timeouts not yet wrapped, `aiosqlite` write failures). Catching only `ProContextError` would let infrastructure exceptions escape and crash the background task silently. `except Exception` with `exc_info=True` ensures all failures are logged and the server continues serving stale content regardless of the failure type.

### 6.3 Cache Error Handling

`aiosqlite` exceptions must never escape the `Cache` class boundary. Tool handlers must not need to import or handle `sqlite3`/`aiosqlite` errors directly — this would leak infrastructure details through the abstraction.

**Read failures** (`get_toc`, `get_page`): If the SQLite read raises `aiosqlite.Error`, catch it, log a warning with `exc_info=True`, and return `None`. The caller treats `None` as a cache miss and falls back to a network fetch. The agent receives a valid response with `cached: false`.

**Write failures** (`set_toc`, `set_page`): If the SQLite write raises `aiosqlite.Error`, catch it, log a warning with `exc_info=True`, and return normally. The content was already fetched successfully — failure to persist it is non-fatal. The agent receives the fetched content; the next request will simply be a cache miss again.

**Cleanup failures** (`cleanup_expired`): Catch `aiosqlite.Error`, log a warning, and continue. Cleanup is a background maintenance task — failure to delete expired rows is non-critical.

```python
# Example: read failure degrades gracefully to cache miss
async def get_toc(self, library_id: str) -> TocCacheEntry | None:
    try:
        entry = await self.db.fetch_toc(library_id)
        ...
        return entry
    except aiosqlite.Error:
        log.warning("cache_read_error", key=f"toc:{library_id}", exc_info=True)
        return None  # Caller treats as cache miss

# Example: write failure is non-fatal
async def set_toc(self, library_id: str, ...) -> None:
    try:
        await self.db.upsert_toc(...)
    except aiosqlite.Error:
        log.warning("cache_write_error", key=f"toc:{library_id}", exc_info=True)
        # Return normally — content was fetched successfully
```

---

## 7. Heading Parser

The heading parser is used exclusively by `read_page`. It produces a plain-text heading map with 1-based line numbers for each heading (H1–H4). Defined in `src/procontext/parser.py`.

The output format is a newline-separated string where each line is `<line_number>: <heading line>`, e.g.:

```
1: # Streaming
3: ## Overview
12: ## Streaming with Chat Models
18: ### Using .stream()
```

This plain-text format is compact and directly navigable — the agent reads line numbers from the heading map and passes them as `offset` to `read_page` for targeted section reads.

### 7.1 Algorithm

Two rules applied in a single pass:

**Rule 1 — Code block tracking**

Suppress heading detection inside fenced code blocks. A block opens on a line starting with ` ``` ` or `~~~` and closes on the next line starting with the same fence string. Heading detection is disabled between open and close.

````python
def parse_headings(content: str) -> str:
    lines: list[str] = []

    in_code_block = False
    fence: str | None = None

    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()

        # Rule 1: code block tracking
        if stripped.startswith("```") or stripped.startswith("~~~"):
            current_fence = stripped[:3]
            if not in_code_block:
                in_code_block = True
                fence = current_fence
            elif current_fence == fence:
                in_code_block = False
                fence = None
            continue

        if in_code_block:
            continue

        # Rule 2: heading detection (H1–H4)
        match = re.match(r"^(#{1,4}) (.+)", line)
        if not match:
            continue

        lines.append(f"{lineno}: {line}")

    return "\n".join(lines)
````

**What is deliberately excluded**:

- `#####` and `######` headings: Too granular, negligible in real documentation
- HTML headings (`<h2>`): Essentially absent from markdown documentation pages
- Setext-style headings (`===` / `---` underlines): Rare in practice, ambiguous with horizontal rules

---

## 8. Transport Layer

### 8.1 stdio Transport

FastMCP handles stdio transport natively. The server runs as a subprocess spawned by the MCP client.

`AppState` is created in a lifespan context manager and flows into tool handlers via FastMCP's `Context` object. Tool business logic lives in `src/procontext/tools/` — `server.py` only registers and dispatches.

```python
# src/procontext/server.py
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context
from procontext.state import AppState
import procontext.tools.resolve_library as t_resolve
import procontext.tools.get_library_docs as t_get_docs
import procontext.tools.read_page as t_read_page

@asynccontextmanager
async def lifespan(server: FastMCP):
    state = await _create_app_state()
    yield state                    # accessible as ctx.request_context.lifespan_context
    await state.http_client.aclose()

mcp = FastMCP("procontext", lifespan=lifespan)

@mcp.tool()
async def resolve_library(query: str, ctx: Context) -> dict:
    state: AppState = ctx.request_context.lifespan_context
    return await t_resolve.handle(query, state)

@mcp.tool()
async def get_library_docs(library_id: str, ctx: Context) -> dict:
    state: AppState = ctx.request_context.lifespan_context
    return await t_get_docs.handle(library_id, state)

@mcp.tool()
async def read_page(url: str, ctx: Context) -> dict:
    state: AppState = ctx.request_context.lifespan_context
    return await t_read_page.handle(url, state)

def main() -> None:
    mcp.run()   # defaults to stdio; HTTP mode handled via config
```

### 8.2 HTTP Transport

Implements MCP Streamable HTTP (spec 2025-11-25). A single `/mcp` endpoint handles both POST (JSON-RPC requests) and GET (SSE event streams). Session state is tracked via `MCP-Session-Id` header.

**Security middleware** runs before the MCP handler on every request:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import re
import secrets
import structlog

SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2025-11-25", "2025-03-26"})
_LOCALHOST_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")

class MCPSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, auth_enabled: bool, auth_key: str | None = None):
        super().__init__(app)
        self.auth_enabled = auth_enabled
        self.auth_key = auth_key

    async def dispatch(self, request: Request, call_next):
        # 1. Optional bearer key authentication
        if self.auth_enabled:
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer ") or auth_header[7:] != self.auth_key:
                return Response("Unauthorized", status_code=401)

        # 2. Origin validation — prevents DNS rebinding attacks
        origin = request.headers.get("origin", "")
        if origin and not _LOCALHOST_ORIGIN.match(origin):
            return Response("Forbidden", status_code=403)

        # 3. Protocol version — reject unknown versions early
        proto_version = request.headers.get("mcp-protocol-version", "")
        if proto_version and proto_version not in SUPPORTED_PROTOCOL_VERSIONS:
            return Response(
                f"Unsupported protocol version: {proto_version}",
                status_code=400,
            )

        return await call_next(request)
```

**Authentication mode**:

- If `server.auth_enabled` is `true`, bearer-key authentication is enforced.
- If `server.auth_enabled` is `true` and `server.auth_key` is empty, the server generates a key at startup (`secrets.token_urlsafe(32)`) and logs it to stderr.
- If `server.auth_enabled` is `false` (default), authentication is disabled and the server logs a startup warning (regardless of host/bind address).

**Server startup** for HTTP mode:

```python
import uvicorn
from starlette.middleware import Middleware

def run_http_server(config: ServerConfig) -> None:
    log = structlog.get_logger().bind(transport="http")
    auth_key = config.auth_key or None

    if config.auth_enabled and not auth_key:
        auth_key = secrets.token_urlsafe(32)
        log.warning("http_auth_key_auto_generated", auth_key=auth_key)

    if not config.auth_enabled:
        log.warning("http_auth_disabled")

    app = mcp.get_asgi_app()
    app.add_middleware(
        MCPSecurityMiddleware,
        auth_enabled=config.auth_enabled,
        auth_key=auth_key,
    )

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_config=None,         # Disable uvicorn's default logging; structlog handles it
    )
```

---

## 9. Registry Updates

### Startup

```
1. Attempt to load <data_dir>/registry/known-libraries.json
2. Attempt to load <data_dir>/registry/registry-state.json
3. Validate local pair: both files parse and sha256(known-libraries.json) equals registry-state.json.checksum
4. If either file is missing or validation fails → ignore local pair, load bundled snapshot (src/procontext/data/known-libraries.json), set local version to "unknown"
5. Build in-memory indexes and SSRF allowlist from loaded data
6. Spawn background task: _check_for_registry_update()
```

### Local Registry State File

`registry-state.json` is stored alongside `known-libraries.json` at `<data_dir>/registry/`:

```json
{
  "version": "2026-02-24",
  "checksum": "sha256:abc123...",
  "updated_at": "2026-02-24T07:10:00Z"
}
```

Rules:

- `version` is the canonical local registry version used for remote comparison (`remote_version == local_version`)
- Local disk files are treated as a consistency unit: if either file is missing/invalid or checksum validation fails, both are ignored and startup falls back to bundled snapshot (`local_version = "unknown"`)
- On successful update, both `known-libraries.json` and `registry-state.json` are persisted atomically for next startup

### Atomic Persistence of Local Registry Pair

`save_registry_to_disk()` writes both files with crash-safe semantics:

```python
def save_registry_to_disk(
    *,
    registry_bytes: bytes,
    version: str,
    checksum: str,
    registry_path: Path,
    state_path: Path,
) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    state_bytes = json.dumps(
        {
            "version": version,
            "checksum": checksum,
            "updated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        }
    ).encode("utf-8")

    registry_tmp = registry_path.with_suffix(registry_path.suffix + ".tmp")
    state_tmp = state_path.with_suffix(state_path.suffix + ".tmp")

    try:
        _write_bytes_fsync(registry_tmp, registry_bytes)
        _write_bytes_fsync(state_tmp, state_bytes)

        os.replace(registry_tmp, registry_path)
        os.replace(state_tmp, state_path)
        _fsync_directory(registry_path.parent)
    finally:
        for tmp in (registry_tmp, state_tmp):
            with suppress(OSError):
                tmp.unlink(missing_ok=True)
```

Operational guarantees:

- A partially written destination file is never observed
- If persistence fails before replace, previous valid pair remains intact
- If persistence fails after replacing one file, startup checksum validation detects mismatch and falls back to bundled snapshot

### Background Update Check

```python
RegistryUpdateOutcome = Literal["success", "transient_failure", "semantic_failure"]

async def check_for_registry_update(state: AppState) -> RegistryUpdateOutcome:
    # 1. Fetch metadata (transient on network error or 5xx/408/429)
    metadata_response = await _safe_get(state, state.settings.registry.metadata_url, timeout=10.0)
    if metadata_response is None:
        return "transient_failure"
    if not metadata_response.is_success:
        return _classify_http_failure(...)

    # 2. Parse and validate metadata fields (semantic on invalid shape)
    metadata = metadata_response.json()
    remote_version, download_url, expected_checksum = ...  # validate or return "semantic_failure"

    # 3. Short-circuit if already up to date
    if remote_version == state.registry_version:
        return "success"

    # 4. Download registry (transient on network error or 5xx/408/429)
    registry_response = await _safe_get(state, download_url, timeout=60.0)
    if registry_response is None:
        return "transient_failure"

    # 5. Checksum validation (semantic on mismatch)
    actual_checksum = _sha256_prefixed(registry_response.content)
    if actual_checksum != expected_checksum:
        return "semantic_failure"

    # 6. Parse registry entries (semantic on schema error)
    new_entries = [RegistryEntry(**e) for e in registry_response.json()]

    # 7. Rebuild indexes + allowlist and swap atomically
    new_indexes = build_indexes(new_entries)
    new_allowlist = build_allowlist(new_entries)
    state.indexes, state.allowlist, state.registry_version = (
        new_indexes, new_allowlist, remote_version,
    )

    # 8. Persist to disk (non-fatal on failure)
    save_registry_to_disk(
        registry_bytes=registry_response.content,
        version=remote_version,
        checksum=expected_checksum,
        registry_path=state.registry_path,
        state_path=state.registry_state_path,
    )

    return "success"
```

The scheduler (in `server.py`) calls `check_for_registry_update()` and uses the returned outcome to decide the next sleep interval. See Scheduling Policy below.

### Scheduling Policy (Hybrid)

Registry update checks use a hybrid scheduler:

- Always run one check at startup (both stdio and HTTP)
- In HTTP mode, after a successful check, schedule the next check at `SUCCESS_INTERVAL = 24h`
- In HTTP mode, after a **transient failure** (network timeout/DNS/connection failures, upstream 5xx), schedule retry using exponential backoff with jitter:
  - `INITIAL_BACKOFF = 60s`
  - `MAX_BACKOFF = 3600s`
  - `MAX_TRANSIENT_BACKOFF_ATTEMPTS = 8` (consecutive transient failures)
  - `next_backoff = min(current_backoff * 2, MAX_BACKOFF)`
  - jitter: random multiplier in `[0.8, 1.2]`
- If consecutive transient failures reach `MAX_TRANSIENT_BACKOFF_ATTEMPTS`, reset the failure counter and backoff, then return to `SUCCESS_INTERVAL = 24h` cadence. This gives the next round a fresh set of fast-retry attempts.
- In HTTP mode, after a **semantic failure** (invalid metadata fields, checksum mismatch, registry schema parse failure), do not use backoff; log and return to `SUCCESS_INTERVAL = 24h`
- After a successful check, reset backoff state and return to 24h cadence
- In stdio mode, no post-startup retries are scheduled because the process is typically short-lived

Illustrative scheduler logic:

```python
success_interval = 24 * 60 * 60
initial_backoff = 60
max_backoff = 60 * 60
max_transient_backoff_attempts = 8
backoff = initial_backoff
consecutive_transient_failures = 0

while running_http_server:
    outcome = await run_registry_update_cycle(state)  # "success" | "transient_failure" | "semantic_failure"
    if outcome == "success":
        consecutive_transient_failures = 0
        backoff = initial_backoff
        await sleep(success_interval)
    elif outcome == "transient_failure":
        consecutive_transient_failures += 1
        if consecutive_transient_failures >= max_transient_backoff_attempts:
            consecutive_transient_failures = 0
            backoff = initial_backoff
            await sleep(success_interval)
            continue
        delay = backoff * random.uniform(0.8, 1.2)
        await sleep(delay)
        backoff = min(backoff * 2, max_backoff)
    else:  # semantic_failure
        consecutive_transient_failures = 0
        backoff = initial_backoff
        await sleep(success_interval)
```

---

## 10. Configuration

Configuration is loaded from `procontext.yaml` (searched in current directory, then the platform config directory via `platformdirs.user_config_dir("procontext")`). All values have defaults — the config file is optional.

```yaml
server:
  transport: stdio # stdio | http
  host: "0.0.0.0" # HTTP mode only
  port: 8080 # HTTP mode only
  auth_enabled: false # HTTP mode only — default false
  auth_key: "" # HTTP mode only — used only when auth_enabled=true; if empty, auto-generated at startup

registry:
  url: "https://procontext.github.io/known-libraries.json"
  metadata_url: "https://procontext.github.io/registry_metadata.json"

cache:
  ttl_hours: 24
  # db_path: platform-specific default via platformdirs.user_data_dir("procontext")
  cleanup_interval_hours: 6

logging:
  level: INFO # DEBUG | INFO | WARNING | ERROR
  format: json # json | text (text for local dev)
```

Loaded via pydantic-settings:

```python
from typing import Any, Literal
from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

class ServerSettings(BaseModel):
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8080
    auth_enabled: bool = False  # HTTP mode only — default false
    auth_key: str = ""  # HTTP mode only — used when auth_enabled=true; if empty, auto-generated

class RegistrySettings(BaseModel):
    url: str = "https://procontext.github.io/known-libraries.json"
    metadata_url: str = "https://procontext.github.io/registry_metadata.json"

class CacheSettings(BaseModel):
    ttl_hours: int = 24
    db_path: str = _DEFAULT_DB_PATH  # platformdirs.user_data_dir("procontext") / "cache.db"
    cleanup_interval_hours: int = 6

class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["json", "text"] = "json"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Double-underscore prefix keeps env vars visually consistent:
        # all separators are __ e.g. PROCONTEXT__SERVER__PORT=9090
        env_prefix="PROCONTEXT__",
        env_nested_delimiter="__",
        yaml_file=_find_config_file(),   # Returns first existing path or None
        yaml_file_encoding="utf-8",
    )

    server: ServerSettings = ServerSettings()
    registry: RegistrySettings = RegistrySettings()
    cache: CacheSettings = CacheSettings()
    logging: LoggingSettings = LoggingSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        **kwargs: Any,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,                         # Constructor args (highest priority)
            env_settings,                          # Environment variables
            YamlConfigSettingsSource(settings_cls),
        )
```

`_find_config_file()` searches `procontext.yaml` in the current directory first, then the platform config directory (`platformdirs.user_config_dir("procontext")`), returning the first path that exists or `None` (config file is optional). Environment variables use the prefix `PROCONTEXT__` with `__` as the nested delimiter (e.g., `PROCONTEXT__SERVER__PORT=9090`, `PROCONTEXT__SERVER__AUTH_ENABLED=true`, `PROCONTEXT__CACHE__TTL_HOURS=48`).

---

## 11. Logging

Structured logging via structlog. All log entries are JSON in production, human-readable text in development (`log_format = "text"`).

```python
import structlog

log = structlog.get_logger()

# Per-request context binding
async def get_library_docs_handler(library_id: str) -> dict:
    log = structlog.get_logger().bind(tool="get_library_docs", library_id=library_id)

    log.info("cache_check")
    entry = await cache.get_toc(library_id)

    if entry and not entry.stale:
        log.info("cache_hit")
        return entry.to_output()

    log.info("cache_miss_fetching")
    content = await fetcher.fetch_text(llms_txt_url)
    log.info("fetch_complete", content_length=len(content))
    ...
```

**Key log events and their fields**:

| Event                    | Fields                                               |
| ------------------------ | ---------------------------------------------------- |
| `server_started`         | `transport`, `version`, `registry_entries`, `registry_version` |
| `registry_loaded`        | `version`, `entries`, `source` (`disk` \| `bundled`) — for `disk`, `version` comes from `registry-state.json`; for `bundled`, `version` is `"unknown"` |
| `registry_updated`       | `version`, `entries`                                 |
| `registry_local_pair_invalid` | `reason`, `path_registry`, `path_state`       |
| `registry_persist_failed` | `version`, `error`                                   |
| `cache_hit`              | `tool`, `library_id` or `url_hash`                   |
| `cache_miss_fetching`    | `tool`, `url`                                        |
| `fetch_complete`         | `url`, `status_code`, `content_length`               |
| `fetch_failed`           | `url`, `error`, `status_code`                        |
| `ssrf_blocked`           | `url`, `reason`                                      |
| `stale_refresh_started`  | `key`                                                |
| `stale_refresh_complete` | `key`, `changed`                                     |
| `stale_refresh_failed`   | `key`, `error`                                       |
| `cache_read_error`       | `key`                                                |
| `cache_write_error`      | `key`                                                |
