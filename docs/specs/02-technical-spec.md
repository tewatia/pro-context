# ProContext: Technical Specification

> **Document**: 02-technical-spec.md
> **Status**: Draft v2
> **Last Updated**: 2026-03-08
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
- [7. Outline Parser](#7-outline-parser)
  - [7.1 Algorithm](#71-algorithm)
- [7A. Search](#7a-search)
  - [7A.1 Pattern Compilation](#7a1-pattern-compilation)
  - [7A.2 Line Scanning](#7a2-line-scanning)
- [8. Transport Layer](#8-transport-layer)
  - [8.1 stdio Transport](#81-stdio-transport)
  - [8.2 HTTP Transport](#82-http-transport)
- [9. Registry Updates](#9-registry-updates)
  - [9.1 Registry Files](#91-registry-files)
  - [9.2 procontext setup](#92-procontext-setup)
  - [9.3 Startup Sequence](#93-startup-sequence)
  - [9.4 Two-URL Design](#94-two-url-design)
  - [9.5 Outcome Classification](#95-outcome-classification)
  - [9.6 Background Update Check](#96-background-update-check)
  - [9.7 In-Memory Hot-Swap](#97-in-memory-hot-swap)
  - [9.8 Atomic Persistence of Local Registry Pair](#98-atomic-persistence-of-local-registry-pair)
  - [9.9 Scheduling Policy](#99-scheduling-policy)
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
│  │  resolve_library │ read_page │ search_page  │   │
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
  └─ Return [{ library_id: "langchain", index_url: "...", matched_via: "package_name", relevance: 1.0 }]

read_page("https://python.langchain.com/llms.txt")
  │
  ├─ SSRF check: domain in allowlist?
  ├─ Cache check: page:{sha256(url)}
  │    HIT (fresh)  → return cached content + outline
  │    HIT (stale)  → return + trigger background refresh
  │    MISS         → continue
  ├─ Fetch: HTTP GET url (30s timeout, SSRF validated per redirect)
  ├─ Store: page_cache (TTL 24h)
  ├─ Parse: extract outline (H1–H6, fence lines, line numbers)
  └─ Return: { outline: "...", content: "...", has_more: bool }

search_page("https://python.langchain.com/llms.txt", "streaming")
  │
  ├─ SSRF check: domain in allowlist?
  ├─ Cache check: page:{sha256(url)} — shared cache with read_page
  │    HIT  → use cached content
  │    MISS → fetch and cache (same path as read_page)
  ├─ Build matcher from query + mode + case_mode + whole_word
  ├─ Scan lines from offset, collect up to max_results matches
  └─ Return: { outline: "...", matches: [...], has_more: bool }
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
| ASGI server        | uvicorn               | ≥0.34   | HTTP transport; ASGI lifespan support                                         |
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
    description: str = ""
    docs_url: str | None = None
    repo_url: str | None = None
    readme_url: str | None = None
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
    description: str          # Short description of what the library does
    languages: list[str]
    index_url: str             # URL to the library's llms.txt documentation index
    readme_url: str | None    # URL to the library's README file
    matched_via: Literal["package_name", "library_id", "alias", "fuzzy"]
    relevance: float          # 0.0–1.0
```

### 3.2 Cache Models

```python
from datetime import datetime
from pydantic import BaseModel

class PageCacheEntry(BaseModel):
    url: str
    url_hash: str             # SHA-256 of url (primary key)
    content: str              # Full page markdown (llms.txt, README, or docs)
    outline: str              # Plain-text structural outline: "<line>: <original line>\n..."
    fetched_at: datetime
    expires_at: datetime
    stale: bool = False
    discovered_domains: frozenset[str] = frozenset()  # Base domains extracted from content URLs
```

All fetched content — llms.txt indexes, README files, and documentation pages — is stored in a single `page_cache` table. Both `read_page` and `search_page` share this cache.

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

class ReadPageInput(BaseModel):
    url: str
    offset: int = 1
    limit: int = 500
    view: Literal["outline", "full"] = "full"

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
    outline: str              # Plain-text structural outline: "<line>: <original line>\n..."
    total_lines: int
    offset: int
    limit: int
    content: str | None       # Page markdown for the requested window; None when view="outline"
    has_more: bool             # True if more content exists beyond the current window
    next_offset: int | None    # Line number to pass as offset to continue; None if no more
    cached: bool
    cached_at: datetime | None
    stale: bool = False

class SearchPageInput(BaseModel):
    url: str
    query: str
    mode: Literal["literal", "regex"] = "literal"
    case_mode: Literal["smart", "insensitive", "sensitive"] = "smart"
    whole_word: bool = False
    offset: int = 1
    max_results: int = 20

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 2048:
            raise ValueError("url must not exceed 2048 characters")
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must use http or https scheme")
        return v

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        if len(v) > 200:
            raise ValueError("query must not exceed 200 characters")
        return v

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 1:
            raise ValueError("offset must be >= 1")
        return v

    @field_validator("max_results")
    @classmethod
    def validate_max_results(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_results must be >= 1")
        return v

class LineMatch(BaseModel):
    line_number: int          # 1-based line number
    content: str              # Full text of the matching line

class SearchPageOutput(BaseModel):
    url: str
    query: str
    outline: str              # Same outline as read_page
    matches: list[LineMatch]
    total_lines: int
    has_more: bool
    next_offset: int | None   # Line number for next search call; None if no more matches
    cached: bool
    cached_at: datetime | None
```

### 3.4 Error Model

```python
from enum import StrEnum
from pydantic import BaseModel

class ErrorCode(StrEnum):
    PAGE_NOT_FOUND        = "PAGE_NOT_FOUND"
    PAGE_FETCH_FAILED     = "PAGE_FETCH_FAILED"
    TOO_MANY_REDIRECTS    = "TOO_MANY_REDIRECTS"
    URL_NOT_ALLOWED       = "URL_NOT_ALLOWED"
    INVALID_INPUT         = "INVALID_INPUT"

class ProContextError(Exception):
    """Base exception for all ProContext errors.

    Raised by tool handlers. FastMCP catches it automatically and converts
    it into an MCP tool result with isError=true. No explicit serialisation
    method is needed — the framework handles the wire format.
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
```

---

## 4. Library Resolution

### 4.1 In-Memory Indexes

Loaded from `known-libraries.json` at startup. Four Python dicts/lists rebuilt in a single pass (<100ms for 1,000 entries):

```python
@dataclass
class RegistryIndexes:
    # Index 1: package name (lowercase) → library ID
    # Many-to-one: "langchain-openai", "langchain-core" → "langchain"
    by_package: dict[str, str]

    # Index 2: library ID (lowercase) → full RegistryEntry
    by_id: dict[str, RegistryEntry]

    # Index 3: alias (lowercase) → library ID (O(1) exact alias lookup)
    # e.g. "torch" → "pytorch"
    by_alias: dict[str, str]

    # Index 4: flat list of (term, library_id) for fuzzy matching
    # Populated from: all IDs + all package names + all aliases (lowercased)
    fuzzy_corpus: list[tuple[str, str]]

def build_indexes(entries: list[RegistryEntry]) -> RegistryIndexes:
    by_package: dict[str, str] = {}
    by_id: dict[str, RegistryEntry] = {}
    by_alias: dict[str, str] = {}
    fuzzy_corpus: list[tuple[str, str]] = []

    for entry in entries:
        by_id[entry.id] = entry
        fuzzy_corpus.append((entry.id, entry.id))

        for pkg in entry.packages.pypi + entry.packages.npm:
            by_package[pkg.lower()] = entry.id
            fuzzy_corpus.append((pkg.lower(), entry.id))

        for alias in entry.aliases:
            by_alias[alias.lower()] = entry.id
            fuzzy_corpus.append((alias.lower(), entry.id))

    return RegistryIndexes(
        by_package=by_package,
        by_id=by_id,
        by_alias=by_alias,
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
        indexes.by_alias.get(normalised)   # O(1) dict lookup
        "torch" → "pytorch"  ✓

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

def build_http_client(settings: FetcherSettings | None = None) -> httpx.AsyncClient:
    read_timeout = settings.request_timeout_seconds if settings is not None else 30.0
    connect_timeout = settings.connect_timeout_seconds if settings is not None else 5.0
    return httpx.AsyncClient(
        follow_redirects=False,       # Manual redirect handling (SSRF requirement)
        timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
        headers={"User-Agent": f"procontext/{__version__}"},
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

def build_allowlist(
    entries: list[RegistryEntry],
    extra_domains: list[str] | None = None,
) -> frozenset[str]:
    """Build the SSRF domain allowlist from registry entries and optional extra domains."""
    base_domains: set[str] = set()
    for entry in entries:
        for url in [entry.llms_txt_url, entry.docs_url]:
            if url:
                hostname = urlparse(url).hostname or ""
                if hostname:
                    base_domains.add(_base_domain(hostname))
    for domain in extra_domains or []:
        domain = domain.strip().lower()
        if domain:
            base_domains.add(_base_domain(domain))
    return frozenset(base_domains)

def extract_base_domains_from_content(content: str) -> frozenset[str]:
    """Extract base domains from all http/https URLs found in content.

    Used for runtime allowlist expansion at depth 1 (llms.txt) and depth 2 (pages).
    """
    domains: set[str] = set()
    for match in _URL_RE.finditer(content):
        hostname = urlparse(match.group()).hostname or ""
        if hostname:
            domains.add(_base_domain(hostname))
    return frozenset(domains)

def expand_allowlist_from_content(
    content: str,
    state: AppState,
) -> frozenset[str]:
    """Extract discovered domains from content and optionally expand the live allowlist.

    Always returns the full set of discovered domains for cache persistence,
    regardless of expansion configuration. Only mutates ``state.allowlist`` when
    ``settings.fetcher.allowlist_expansion == "discovered"``.

    Called by both read_page and search_page after any successful fetch.
    """
    discovered_domains = extract_base_domains_from_content(content)
    if state.settings.fetcher.allowlist_expansion == "discovered":
        new_domains = discovered_domains - state.allowlist
        if new_domains:
            state.allowlist = state.allowlist | new_domains
            log.info("allowlist_expanded", added_domains=len(new_domains))
    return discovered_domains

def is_url_allowed(
    url: str,
    allowlist: frozenset[str],
    *,
    check_private_ips: bool = True,
    check_domain: bool = True,
) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    if check_private_ips:
        try:
            addr = ipaddress.ip_address(hostname)
            if any(addr in net for net in PRIVATE_NETWORKS):
                return False
        except ValueError:
            pass

    if not check_domain:
        return True

    return _base_domain(hostname) in allowlist
```

**SSRF controls are configurable** via `FetcherSettings` (see Section 10):

- **`ssrf_private_ip_check`** (default `true`): blocks all requests to private/internal IP ranges. Strongly recommended to keep enabled.
- **`ssrf_domain_check`** (default `true`): enforces the domain allowlist. When `false`, any public domain is reachable — only appropriate for isolated/air-gapped environments.
- **`allowlist_expansion`** (default `"registry"`): controls whether the allowlist is expanded at runtime beyond the registry (see below).
- **`extra_allowed_domains`**: manually specified domains always merged into the allowlist at startup, regardless of expansion setting. Ships with `["github.com", "githubusercontent.com"]` as defaults.

**Runtime allowlist expansion** (reactive, not pre-fetched):

- **`"registry"`** (default): allowlist is fixed at startup — only registry domains + `extra_allowed_domains`.
- **`"discovered"`**: after `read_page` or `search_page` fetches any content (llms.txt, README, or documentation page), all URLs in the content have their base domains extracted and merged into `state.allowlist`. Enables following cross-domain links found in documentation.

When expansion is `"discovered"`, it is monotonic (domains are only added, never removed). The allowlist resets to the registry baseline on each registry update. In long-running HTTP mode, the allowlist may grow across sessions until the next registry update.

**Cross-restart persistence**: `discovered_domains` are always extracted from fetched content and written to the SQLite cache — even when expansion is `"registry"` — so they are available if the operator later enables `"discovered"` expansion. At startup, `Cache.load_discovered_domains()` reads all `discovered_domains` from `page_cache` and merges them into the initial allowlist (subject to `allowlist_expansion` setting). This ensures that cached pages from a previous session remain reachable after a server restart, and avoids the performance cost of re-running domain extraction on every server start.

**Known limitation**: Two-label base domain extraction is a simplification of proper eTLD+1 calculation. For shared hosting platforms like `github.io` or `readthedocs.io`, the base domain would be `github.io` or `readthedocs.io` — permitting all projects hosted there, not just the registered library. This is an acceptable trade-off for v1; a future version could adopt the `tldextract` library for accurate Public Suffix List-based matching.

### 5.3 Redirect Handling

Each redirect hop is individually validated before following:

```python
async def fetch(
    self,
    url: str,
    allowlist: frozenset[str],
    max_redirects: int = 3,
) -> str:
    """Returns response text on success. Raises ProContextError on failure."""
    current_url = url

    for hop in range(max_redirects + 1):
        if not is_url_allowed(
            current_url,
            allowlist,
            check_private_ips=self._settings.ssrf_private_ip_check,
            check_domain=self._settings.ssrf_domain_check,
        ):
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
                    code=ErrorCode.TOO_MANY_REDIRECTS,
                    message=f"Too many redirects fetching {url}",
                    suggestion="The documentation URL has an unusually long redirect chain.",
                    recoverable=False,
                )
            location = response.headers["location"]
            current_url = urljoin(current_url, location)  # resolves relative redirects
            continue

        if not response.is_success:
            # ... raise PAGE_NOT_FOUND (404) or PAGE_FETCH_FAILED (other)

        return response.text

    raise ProContextError(  # unreachable but satisfies type checker
        code=ErrorCode.TOO_MANY_REDIRECTS,
        message="Redirect loop",
        suggestion="",
        recoverable=False,
    )
```

The return type is `str` (response text), not `httpx.Response`. This keeps `httpx` out of the tool layer — tool handlers and `FetcherProtocol` consumers never touch `httpx` types directly.

---

## 6. Cache

### 6.1 SQLite Schema

Single database at `cache.db_path` (default: `platformdirs.user_data_dir("procontext")/cache.db`). This default is intentionally independent from `data_dir` overrides. WAL mode is set once at connection time and persists — it does not need to be re-applied on subsequent opens.

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS page_cache (
    url_hash           TEXT PRIMARY KEY,             -- SHA-256(url)
    url                TEXT NOT NULL UNIQUE,
    content            TEXT NOT NULL,
    outline            TEXT NOT NULL DEFAULT '',     -- Plain-text structural outline
    discovered_domains TEXT NOT NULL DEFAULT '',     -- Space-separated base domains extracted from content
    fetched_at         TEXT NOT NULL,                -- ISO 8601
    expires_at         TEXT NOT NULL                 -- ISO 8601
);

CREATE INDEX IF NOT EXISTS idx_page_expires  ON page_cache(expires_at);

CREATE TABLE IF NOT EXISTS server_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

The `server_metadata` table stores operational state such as the last cleanup timestamp. It is a simple key-value store.

All fetched content — llms.txt indexes, README files, and documentation pages — is stored in a single `page_cache` table. Both `read_page` and `search_page` share this cache.

**Why TEXT for timestamps**: SQLite has no native datetime type. ISO 8601 strings (`"2026-02-23T10:00:00Z"`) sort lexicographically as datetimes, making range queries on `expires_at` correct without any conversion.

**`discovered_domains` column**: Stores the base domains (`example.com`, `docs.dev`) extracted from fetched content by `extract_base_domains_from_content`. Serialised as a space-separated string (base domains never contain spaces). Written unconditionally on every cache write — regardless of the current `allowlist_expansion` config — so the data is always available if the operator later enables `"discovered"` expansion. At startup, `Cache.load_discovered_domains()` reads all non-empty `discovered_domains` values from `page_cache` and merges them back into the in-memory allowlist (subject to `allowlist_expansion`). This restores cross-restart continuity for the runtime-expanded allowlist.

**Cleanup**: A periodic task (runs at startup and every 6 hours thereafter) deletes entries where `expires_at < now() - 7 days`. Stale entries are kept up to 7 days to allow stale-while-revalidate to function even if the source is temporarily unreachable.

### 6.2 Stale-While-Revalidate

`Cache.get_page()` marks the entry as stale but does **not** launch the background task — that responsibility belongs to the tool layer, which has the full `AppState` (fetcher, allowlist, settings) needed to do the re-fetch.

```python
# In Cache.get_page() — marks stale, returns entry; does NOT create a task
async def get_page(self, url_hash: str) -> PageCacheEntry | None:
    entry = await self.db.fetch_page(url_hash)
    if entry is None:
        return None
    if entry.expires_at < datetime.now(UTC):
        entry.stale = True
    return entry

# In tools/_shared.py — shared helper used by both read_page and search_page
page = await state.cache.get_page(url_hash)
if page is not None and page.stale:
    asyncio.create_task(_refresh_page(state, url))
```

Both `read_page` and `search_page` use a shared helper (`fetch_or_cached_page`) that encapsulates the full cache-check → fetch → cache-write → stale-refresh flow. The agent always gets a response immediately — a background `asyncio.create_task` handles the refresh without blocking.

**Why `except Exception` and not `except ProContextError`**: Background refresh failures include both expected errors (`ProContextError` — e.g., fetch failed, URL not allowed) and unexpected ones (network timeouts not yet wrapped, `aiosqlite` write failures). Catching only `ProContextError` would let infrastructure exceptions escape and crash the background task silently. `except Exception` with `exc_info=True` ensures all failures are logged and the server continues serving stale content regardless of the failure type.

### 6.3 Cache Error Handling

`aiosqlite` exceptions must never escape the `Cache` class boundary. Tool handlers must not need to import or handle `sqlite3`/`aiosqlite` errors directly — this would leak infrastructure details through the abstraction.

**Read failures** (`get_page`): If the SQLite read raises `aiosqlite.Error`, catch it, log a warning with `exc_info=True`, and return `None`. The caller treats `None` as a cache miss and falls back to a network fetch. The agent receives a valid response with `cached: false`.

**Write failures** (`set_page`): If the SQLite write raises `aiosqlite.Error`, catch it, log a warning with `exc_info=True`, and return normally. The content was already fetched successfully — failure to persist it is non-fatal. The agent receives the fetched content; the next request will simply be a cache miss again.

**Cleanup failures** (`cleanup_expired`): Catch `aiosqlite.Error`, log a warning, and continue. Cleanup is a background maintenance task — failure to delete expired rows is non-critical.

```python
# Example: read failure degrades gracefully to cache miss
async def get_page(self, url_hash: str) -> PageCacheEntry | None:
    try:
        entry = await self.db.fetch_page(url_hash)
        ...
        return entry
    except aiosqlite.Error:
        log.warning("cache_read_error", key=f"page:{url_hash}", exc_info=True)
        return None  # Caller treats as cache miss

# Example: write failure is non-fatal
async def set_page(self, url: str, url_hash: str, ...) -> None:
    try:
        await self.db.upsert_page(...)
    except aiosqlite.Error:
        log.warning("cache_write_error", key=f"page:{url_hash}", exc_info=True)
        # Return normally — content was fetched successfully
```

---

## 7. Outline Parser

The outline parser is used exclusively by `read_page`. It produces a plain-text structural map with 1-based line numbers for headings and fenced code block boundaries. Defined in `src/procontext/parser.py`.

The output format is a newline-separated string where each line is `<line_number>: <original line>`, e.g.:

```
1: # Authenticate
5: ## OpenAPI
7: ````yaml https://api.example.com/openapi.json
14:     ## Authentication
22: ````
25: ## Next Section
```

Fence opener/closer lines are included so the agent can determine which heading-like lines belong to code block content vs. structural page sections. The agent reads line numbers from the map and passes them as `offset` to `read_page` for targeted section reads.

### 7.1 Algorithm

Stateless single-pass: emit a line if it matches either of two patterns.

**Pattern 1 — Fence lines**

```python
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
```

Matched against the original `line`. The `^ {0,3}` indentation constraint ensures that 4-space indented lines (CommonMark indented code blocks) are not treated as fences.

**Pattern 2 — Heading lines**

```python
_HEADING_RE = re.compile(r"(?:>\s*)?(#{1,6}) .+")
```

Matched against `stripped` (leading/trailing whitespace removed). Matching on the stripped line serves two purposes:
- Handles blockquote headings (`> ## Section`) by ignoring the `>` prefix
- Captures headings inside code blocks regardless of their indentation (e.g. `    ## Host` in a YAML block)

```python
for lineno, line in enumerate(content.splitlines(), start=1):
    stripped = line.strip()
    if _FENCE_RE.match(line) or _HEADING_RE.match(stripped):
        lines.append(f"{lineno}: {line}")
```

**What is deliberately excluded**:

- Lines with 7+ hashes (`#######`): Not valid in CommonMark; only H1–H6 exist
- HTML headings (`<h2>`): Essentially absent from markdown documentation pages
- Setext-style headings (`===` / `---` underlines): Rare in practice, ambiguous with horizontal rules
- Deeply nested blockquotes (`>> ## heading`): The `(?:>\s*)?` prefix matches a single `>` only

---

## 7A. Search

The search module is used exclusively by `search_page`. It compiles a search pattern from the tool input parameters and scans page content line by line. Defined in `src/procontext/search.py`.

### 7A.1 Pattern Compilation

```python
import re

def build_matcher(
    query: str,
    mode: Literal["literal", "regex"],
    case_mode: Literal["smart", "insensitive", "sensitive"],
    whole_word: bool,
) -> re.Pattern[str]:
    if mode == "literal":
        pattern = re.escape(query)
    else:
        pattern = query  # raw regex — validated at search time, not input time

    if whole_word:
        pattern = rf"\b{pattern}\b"

    flags = 0
    if case_mode == "insensitive":
        flags = re.IGNORECASE
    elif case_mode == "smart":
        if query == query.lower():
            flags = re.IGNORECASE
    # case_mode == "sensitive": no flags

    return re.compile(pattern, flags)
```

**Regex validation**: Invalid regex patterns are caught by `re.compile` raising `re.error`. This is caught at search time (not input validation time) and raised as `ProContextError(code=ErrorCode.INVALID_INPUT)`. This avoids adding latency to input validation by attempting pattern compilation before the page fetch.

**ReDoS protection**: Query length is capped at 200 characters in `SearchPageInput`. This limits the complexity of regex patterns. Catastrophic backtracking patterns typically require longer input.

### 7A.2 Line Scanning

```python
def search_lines(
    content: str,
    matcher: re.Pattern[str],
    offset: int,
    max_results: int,
) -> tuple[list[LineMatch], bool, int | None]:
    """Scan content lines from offset, return matches, has_more flag, and next_offset.

    Returns:
        (matches, has_more, next_offset)
    """
    lines = content.splitlines()
    matches: list[LineMatch] = []

    for lineno, line in enumerate(lines, start=1):
        if lineno < offset:
            continue
        if matcher.search(line):
            matches.append(LineMatch(line_number=lineno, content=line))
            if len(matches) == max_results:
                # Check if there are more matches
                for remaining_lineno, remaining_line in enumerate(
                    lines[lineno:], start=lineno + 1
                ):
                    if matcher.search(remaining_line):
                        return matches, True, lineno + 1
                return matches, False, None

    return matches, False, None
```

Stateless single-pass scan. No index, no pre-processing — the page content is already in memory from the cache read. For typical documentation pages (hundreds to low thousands of lines), a linear scan completes in under 1ms.

---

## 8. Transport Layer

### 8.1 stdio Transport

FastMCP handles stdio transport natively. The server runs as a subprocess spawned by the MCP client.

`AppState` is created in a lifespan context manager (`mcp/lifespan.py`) and flows into tool handlers via FastMCP's `Context` object. Tool business logic lives in `src/procontext/tools/` — `mcp/server.py` only registers and dispatches.

```python
# src/procontext/mcp/server.py
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP, Context
from procontext.state import AppState
import procontext.tools.resolve_library as t_resolve
import procontext.tools.read_page as t_read_page
import procontext.tools.search_page as t_search_page

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
async def read_page(url: str, ctx: Context, offset: int = 1, limit: int = 500) -> dict:
    state: AppState = ctx.request_context.lifespan_context
    return await t_read_page.handle(url, offset, limit, state)

@mcp.tool()
async def search_page(url: str, query: str, ctx: Context) -> dict:
    state: AppState = ctx.request_context.lifespan_context
    return await t_search_page.handle(url, query, ctx, state)

def main() -> None:
    mcp.run()   # defaults to stdio; HTTP mode handled via config
```

### 8.2 HTTP Transport

Implements MCP Streamable HTTP (spec 2025-11-25). A single `/mcp` endpoint handles both POST (JSON-RPC requests) and GET (SSE event streams). Session state is tracked via `MCP-Session-Id` header.

**Security middleware** runs before the MCP handler on every request.

Implemented as a **pure ASGI middleware** (not `BaseHTTPMiddleware`) so that SSE streaming responses from the MCP endpoint are never buffered by the middleware layer:

```python
from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send
import ipaddress
import secrets
from urllib.parse import urlparse

SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2025-11-25", "2025-03-26"})

def _is_loopback_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.params or parsed.query or parsed.fragment:
        return False
    hostname = parsed.hostname
    if hostname == "localhost":
        return True
    if hostname is None:
        return False
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False

class MCPSecurityMiddleware:
    def __init__(self, app: ASGIApp, *, auth_enabled: bool, auth_key: str | None = None):
        self.app = app
        self.auth_enabled = auth_enabled
        self.auth_key = auth_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)

            # 1. Optional bearer key authentication
            if self.auth_enabled:
                auth_header = headers.get("authorization", "")
                if not auth_header.startswith("Bearer ") or auth_header[7:] != self.auth_key:
                    await Response("Unauthorized", status_code=401)(scope, receive, send)
                    return

            # 2. Origin validation — prevents DNS rebinding attacks
            origin = headers.get("origin", "")
            if origin and not _is_loopback_origin(origin):
                await Response("Forbidden", status_code=403)(scope, receive, send)
                return

            # 3. Protocol version — reject unknown versions early
            proto_version = headers.get("mcp-protocol-version", "")
            if proto_version and proto_version not in SUPPORTED_PROTOCOL_VERSIONS:
                await Response(
                    f"Unsupported protocol version: {proto_version}",
                    status_code=400,
                )(scope, receive, send)
                return

        await self.app(scope, receive, send)
```

**Authentication mode**:

- If `server.auth_enabled` is `true`, bearer-key authentication is enforced.
- If `server.auth_enabled` is `true` and `server.auth_key` is empty, the server generates a key at startup (`secrets.token_urlsafe(32)`) and logs it to stderr. The key is **not persisted to disk** — a new key is generated on every server restart. This is intentional: persistence would require file-permission and encryption-at-rest decisions that exceed the scope of this lightweight access control. MCP clients read the key from the server's startup log output and reconnect after a restart.
- If `server.auth_enabled` is `false` (default), authentication is disabled and the server logs a startup warning (regardless of host/bind address).

**Server startup** for HTTP mode:

```python
import uvicorn

def run_http_server(mcp: FastMCP, settings: Settings) -> None:
    # Logging is already configured by main() before this is called.
    http_log = log.bind(transport="http")
    auth_key: str | None = settings.server.auth_key or None

    if settings.server.auth_enabled and not auth_key:
        auth_key = secrets.token_urlsafe(32)
        http_log.warning("http_auth_key_auto_generated", auth_key=auth_key)

    if not settings.server.auth_enabled:
        http_log.warning("http_auth_disabled")

    # mcp.streamable_http_app() returns a Starlette ASGI app with the FastMCP
    # lifespan already wired in.  Wrap it directly — no add_middleware() needed.
    http_app = mcp.streamable_http_app()
    secured_app = MCPSecurityMiddleware(
        http_app,
        auth_enabled=settings.server.auth_enabled,
        auth_key=auth_key,
    )

    uvicorn.run(
        secured_app,
        host=settings.server.host,
        port=settings.server.port,
        log_config=None,         # Disable uvicorn's default logging; structlog handles it
    )
```

---

## 9. Registry Updates

The registry update system keeps the in-memory library index fresh without interrupting request serving. It is designed around three principles:

1. **Explicit initialisation** — the server requires a local registry on disk. Run `procontext setup` once to download it; the server refuses to start without it.
2. **Cheap polling** — a tiny metadata file is fetched on each poll cycle; the full registry is only downloaded when its checksum changes.
3. **Zero-downtime swap** — new registry data is applied to the live `AppState` atomically while in-flight requests continue using the previous data safely.

---

### 9.1 Registry Files

Two registry artefacts live on disk:

| Artefact             | Location                                   | Purpose                                                                                          |
| -------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| **Local registry**   | `<data_dir>/registry/known-libraries.json` | Downloaded by `procontext setup` and updated by the background scheduler.                        |
| **Local state file** | `<data_dir>/registry/registry-state.json`  | Stores `version`, `sha256` checksum, `updated_at`, and `last_checked_at` for the local registry. |

`<data_dir>` defaults to `platformdirs.user_data_dir("procontext")` and can be overridden via `PROCONTEXT__DATA_DIR`.

`registry-state.json` format:

```json
{
  "version": "2026-02-24",
  "checksum": "sha256:abc123...",
  "updated_at": "2026-02-24T07:10:00Z",
  "last_checked_at": "2026-02-25T08:00:00Z"
}
```

- `updated_at` — set only when a new registry version is actually downloaded and persisted.
- `last_checked_at` — set after every successful update check, even when the registry is already current. Used by both transports to gate checks: if the gap between now and `last_checked_at` is less than `registry.poll_interval_hours`, the startup check (stdio) or first poll (HTTP) is skipped to avoid redundant metadata fetches on frequent restarts or immediately after auto-setup.

The local registry pair (both files together) is the consistency unit. If either file is missing, cannot be parsed, or the checksum in the state file does not match `sha256(known-libraries.json)`, the pair is considered invalid and the server treats it as if no registry exists.

---

### 9.2 `procontext setup`

`procontext setup` is a one-time CLI command that must be run before starting the server for the first time:

```
procontext setup
# or
uvx procontext setup
```

It fetches the registry metadata, downloads the full registry, validates the checksum, and saves the local registry pair to `<data_dir>/registry/`. Exits with a clear error if the fetch fails.

`setup` uses the same split HTTP timeout as all registry fetches: **5s to connect** (fail fast if unreachable), **5 minutes to read** (patient once the transfer has started).

---

### 9.3 Startup Sequence

```
1. Try to load local registry pair from <data_dir>/registry/
      Both files must exist, parse, and pass checksum validation.
      On success → proceed to step 3.

2. If local pair is missing or invalid →
      Attempt a blocking auto-setup (same as procontext setup).
        On success → load the newly saved pair, proceed to step 3.
        On failure → exit with:
          "Registry not initialised. Run 'procontext setup' to download the registry."

3. Build in-memory indexes (RegistryIndexes) and SSRF allowlist from loaded data.
   Server is now ready to handle requests.

4. Spawn background task:
      stdio  → run_registry_startup_check()   (runs once, consults last_checked_at)
      HTTP   → run_registry_update_scheduler() (infinite loop, consults last_checked_at
                                                before first poll)
```

The auto-setup in step 2 makes the server self-healing on first run: if a user forgets to run `procontext setup`, a direct invocation will attempt to initialise the registry automatically. If the network is unavailable, the server exits with an actionable error rather than starting with no data.

---

### 9.4 Two-URL Design

The update check uses two separate URLs:

- **`registry.metadata_url`** — a tiny JSON file (`~200 bytes`) containing the current `version`, `checksum`, and `download_url`. Fetched on every poll cycle.
- **`download_url`** (from metadata) — the full registry JSON (potentially hundreds of KB). Fetched only when the remote `version` differs from the local one.

This split means that on a typical poll cycle where the registry has not changed, only the small metadata file is fetched. The full registry download is triggered only when there is actually an update — reducing outbound traffic significantly in long-running HTTP deployments.

All registry HTTP requests use a **split timeout**: 5s to connect (fail fast if unreachable), 5 minutes to read (patient once the transfer has started). This avoids cutting off large downloads on slow networks while still failing quickly when the registry host is unreachable.

```
Poll cycle:
  GET metadata_url → { version, checksum, download_url }
       │
       ├─ version == local_version  → return "success" (no download needed)
       │
       └─ version != local_version  → GET download_url
                                           │
                                           ├─ sha256(body) == checksum → apply update
                                           └─ sha256(body) != checksum → return "semantic_failure"
```

---

### 9.5 Outcome Classification

`check_for_registry_update()` returns one of three outcomes, which the scheduler uses to decide the next sleep interval:

| Outcome               | Meaning                                                        | Examples                                                        |
| --------------------- | -------------------------------------------------------------- | --------------------------------------------------------------- |
| `"success"`           | Registry is up to date or was successfully updated             | Version match, clean download + checksum pass                   |
| `"transient_failure"` | Recoverable infrastructure problem — retry with backoff        | Network timeout, DNS failure, upstream 5xx/408/429              |
| `"semantic_failure"`  | Non-recoverable data problem — retrying immediately won't help | Invalid metadata shape, checksum mismatch, schema parse failure |

Transient failures are retried aggressively with exponential backoff. Semantic failures skip backoff and return to the normal poll cadence — the assumption is that a malformed registry is a publisher-side bug that will be fixed before the next scheduled check.

---

### 9.6 Background Update Check

`check_for_registry_update(state)` in `registry.py` follows these steps:

1. Fetch `metadata_url`. Network error or 5xx/408/429 → `"transient_failure"`.
2. Parse and validate metadata fields (`version`, `checksum`, `download_url`). Invalid shape → `"semantic_failure"`.
3. Short-circuit if `remote_version == state.registry_version` → `"success"`.
4. Fetch the full registry from `download_url`. Network error → `"transient_failure"`.
5. Validate `sha256(body) == expected_checksum`. Mismatch → `"semantic_failure"`.
6. Parse registry entries. Schema error → `"semantic_failure"`.
7. Rebuild indexes and allowlist, swap atomically into `AppState` (see §9.7).
8. Persist pair to disk (non-fatal on failure, see §9.8).
9. Return `"success"`.

---

### 9.7 In-Memory Hot-Swap

When a registry update is applied (step 7 above), three `AppState` attributes are replaced simultaneously:

- `state.indexes` — the new `RegistryIndexes` (all lookup maps rebuilt from the new entries)
- `state.allowlist` — new `frozenset[str]` built from the new registry entries + `extra_allowed_domains`
- `state.registry_version` — updated to the remote version string

**Why this is safe without a lock:**

Both `RegistryIndexes` and `frozenset` are immutable once constructed. Python's GIL makes the combined attribute assignment effectively atomic at the interpreter level. Any request already in-flight that holds a reference to the old `state.allowlist` or `state.indexes` continues to work against those objects for the duration of that request — the objects themselves never change. New requests arriving after the assignment pick up the fresh data immediately.

The allowlist is always reset to the registry baseline on each successful update. Any domains that were dynamically expanded at runtime (via `allowlist_expansion = "discovered"`) are not carried forward into the new allowlist — they will be re-accumulated as pages are fetched under the new registry. Domains stored in the `discovered_domains` cache column are restored at the next server restart via `load_discovered_domains()`.

---

### 9.8 Atomic Persistence of Local Registry Pair

`save_registry_to_disk()` in `registry.py` writes both files with crash-safe semantics using write-to-temp-then-rename: each file is written and fsynced to a `.tmp` sibling, then renamed into place with `os.replace()`, followed by an fsync on the parent directory. Temp files are cleaned up in a `finally` block.

Crash-safety guarantees:

| Failure point                                    | Effect on disk                | Next startup behaviour                            |
| ------------------------------------------------ | ----------------------------- | ------------------------------------------------- |
| Crash during temp write                          | Destination files untouched   | Load previous valid pair                          |
| Crash after registry rename, before state rename | Registry updated, state stale | Checksum mismatch → auto-setup or exit with error |
| Crash after both renames                         | Both files updated            | Load new pair normally                            |

`_fsync_directory()` is a no-op on Windows (`sys.platform == "win32"` guard) since Windows does not support `fsync` on directory handles. The write-then-rename guarantee still holds; only the directory entry durability is weaker.

---

### 9.9 Scheduling Policy

Registry update checks run differently depending on transport mode:

**stdio mode** — checks once at startup if `registry_check_is_due()` returns True, then exits. The process is typically short-lived (one agent session), so a polling loop would be wasteful.

**HTTP mode** — loops indefinitely. Before the first check, consults `registry_check_is_due()`: if the registry was checked recently (e.g. auto-setup just ran), sleeps for `poll_interval_hours` before the first check; otherwise checks immediately. The poll interval after a successful check is controlled by `registry.poll_interval_hours` (default 24h, configurable). Transient failures are retried with exponential backoff; semantic failures return to the normal poll cadence without backoff.

Backoff parameters (currently hardcoded, not configurable):

- `INITIAL_BACKOFF = 60s`
- `MAX_BACKOFF = 3600s`
- `MAX_TRANSIENT_BACKOFF_ATTEMPTS = 8`
- jitter: `backoff × random.uniform(0.8, 1.2)` — prevents thundering herd if multiple instances share the same registry URL

If consecutive transient failures reach `MAX_TRANSIENT_BACKOFF_ATTEMPTS`, the circuit breaker fires: the failure counter and backoff are reset, and the scheduler sleeps for the full `poll_interval_hours` before trying again.

```
Outcome → sleep before next attempt
─────────────────────────────────────────────────────────
success                          poll_interval_hours × 3600
semantic_failure                 poll_interval_hours × 3600
transient (attempt < 8)          backoff × jitter  (then backoff doubles)
transient (attempt = 8, reset)   poll_interval_hours × 3600
```

---

## 10. Configuration

Configuration is loaded from `procontext.yaml` (searched in current directory, then the platform config directory via `platformdirs.user_config_dir("procontext")`). All values have defaults — the config file is optional.

```yaml
data_dir: "" # default: platformdirs.user_data_dir("procontext"); registry path root; override via PROCONTEXT__DATA_DIR

server:
  transport: stdio # stdio | http
  host: "127.0.0.1" # HTTP mode only
  port: 8080 # HTTP mode only
  auth_enabled: false # HTTP mode only — default false
  auth_key: "" # HTTP mode only — used only when auth_enabled=true; if empty, auto-generated at startup

registry:
  metadata_url: "https://procontexthq.github.io/registry_metadata.json"
  poll_interval_hours: 24 # How often to check for a new registry version

cache:
  ttl_hours: 24
  # db_path: platform-specific default via platformdirs.user_data_dir("procontext") / "cache.db" (independent from data_dir override)
  cleanup_interval_hours: 6

fetcher:
  ssrf_private_ip_check: true # block private/internal IPs; strongly recommended
  ssrf_domain_check: true # enforce domain allowlist; set false only in isolated environments
  allowlist_expansion: "registry" # "registry" = fixed at startup | "discovered" = expand from fetched content
  extra_allowed_domains: # always trusted, merged at startup regardless of depth
    - github.com
    - githubusercontent.com
  connect_timeout_seconds: 5.0 # TCP connection timeout; fail fast so .md probes fall back quickly
  request_timeout_seconds: 30.0 # per-request read timeout for documentation fetches

resolver:
  fuzzy_score_cutoff: 70 # minimum rapidfuzz score (0–100) for a fuzzy match to count
  fuzzy_max_results: 5 # maximum number of fuzzy candidates returned

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
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

class ServerSettings(BaseModel):
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8080
    auth_enabled: bool = False  # HTTP mode only — default false
    auth_key: str = ""  # HTTP mode only — used when auth_enabled=true; if empty, auto-generated

class RegistrySettings(BaseModel):
    metadata_url: str = "https://procontexthq.github.io/registry_metadata.json"
    poll_interval_hours: int = 24

class CacheSettings(BaseModel):
    ttl_hours: int = 24
    db_path: str = _DEFAULT_DB_PATH  # platformdirs.user_data_dir("procontext") / "cache.db" (independent from data_dir override)
    cleanup_interval_hours: int = 6

class FetcherSettings(BaseModel):
    ssrf_private_ip_check: bool = True
    ssrf_domain_check: bool = True
    allowlist_expansion: Literal["registry", "discovered"] = "registry"
    extra_allowed_domains: list[str] = ["github.com", "githubusercontent.com"]
    connect_timeout_seconds: float = 5.0
    request_timeout_seconds: float = 30.0

class ResolverSettings(BaseModel):
    fuzzy_score_cutoff: int = 70
    fuzzy_max_results: int = 5

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

    data_dir: str = _DEFAULT_DATA_DIR  # platformdirs.user_data_dir("procontext")
    server: ServerSettings = ServerSettings()
    registry: RegistrySettings = RegistrySettings()
    cache: CacheSettings = CacheSettings()
    fetcher: FetcherSettings = FetcherSettings()
    resolver: ResolverSettings = ResolverSettings()
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
async def search_page_handler(url: str, query: str, state: AppState) -> dict:
    url_hash = sha256_hex(url)
    log = structlog.get_logger().bind(tool="search_page", url_hash=url_hash)

    log.info("cache_check")
    page = await state.cache.get_page(url_hash)

    if page is not None and not page.stale:
        log.info("cache_hit")
    elif page is not None:
        log.info("cache_hit_stale")
    else:
        log.info("cache_miss_fetching", url=url)
        content = await state.fetcher.fetch(url, state.allowlist)
        log.info("fetch_complete", content_length=len(content))
        ...
```

**Key log events and their fields**:

| Event                         | Fields                                                                               |
| ----------------------------- | ------------------------------------------------------------------------------------ |
| `server_started`              | `transport`, `version`, `registry_entries`, `registry_version`                       |
| `registry_loaded`             | `source` (`disk`), `version`, `entries`, `path` — `version` comes from `registry-state.json` |
| `registry_updated`            | `version`, `entries`                                                                 |
| `registry_local_pair_invalid` | `reason`, `path_registry`, `path_state`                                              |
| `registry_persist_failed`     | `version`, `error`                                                                   |
| `cache_hit`                   | `tool`, `library_id` or `url_hash`                                                   |
| `cache_miss_fetching`         | `tool`, `url`                                                                        |
| `fetch_complete`              | `url`, `status_code`, `content_length`                                               |
| `fetch_failed`                | `url`, `error`, `status_code`                                                        |
| `ssrf_blocked`                | `url`, `reason`                                                                      |
| `stale_refresh_started`       | `key`                                                                                |
| `stale_refresh_complete`      | `key`                                                                                |
| `stale_refresh_failed`        | `key`, `error`                                                                       |
| `cache_read_error`            | `key`                                                                                |
| `cache_write_error`           | `key`                                                                                |
