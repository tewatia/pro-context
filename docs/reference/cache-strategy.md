# Pro-Context: Caching Strategy

> **Document**: docs/reference/cache-strategy.md
> **Last Updated**: 2026-02-20
> **Audience**: Developers implementing or debugging the cache layer
> **Related spec**: `docs/specs/03-technical-spec.md` — Sections 3.2, 5, 14.1

---

## Table of Contents

- [1. Why Caching?](#1-why-caching)
- [2. Two-Tier Architecture](#2-two-tier-architecture)
- [3. What Gets Cached (Three Domains)](#3-what-gets-cached-three-domains)
- [4. Data Structures](#4-data-structures)
- [5. Tier 1: In-Memory Cache (AsyncTTLCache)](#5-tier-1-in-memory-cache-asyncttlcache)
- [6. Tier 2: SQLite Cache](#6-tier-2-sqlite-cache)
- [7. Cache Keys](#7-cache-keys)
- [8. TTL Strategy](#8-ttl-strategy)
- [9. Freshness Checking](#9-freshness-checking)
- [10. Stale-While-Revalidate (Background Refresh)](#10-stale-while-revalidate-background-refresh)
- [11. Cache Invalidation](#11-cache-invalidation)
- [12. Read Flow](#12-read-flow)
- [13. Write Flow](#13-write-flow)
- [14. Page Cache: Offset-Based Slicing](#14-page-cache-offset-based-slicing)
- [15. Configuration](#15-configuration)

---

## 1. Why Caching?

Pro-Context fetches documentation from third-party llms.txt files over HTTP. Without caching, every tool call (get-docs, get-library-info, read-page) would trigger a live HTTP fetch. This creates three problems:

**Latency**: HTTP fetches take 100ms–3s depending on network conditions and documentation site responsiveness. Agents call tools repeatedly during a session — a cold-fetch for every call would make the server feel sluggish.

**Reliability**: If a documentation site is temporarily down, the tool fails. With a cache, previously fetched content is served even when the source is unavailable.

**Redundancy**: The same documentation is fetched many times — same library by different users in HTTP mode, same page via different tools (get-docs fetches a page, then read-page requests the same page), same content across sessions. Caching eliminates the repetition.

The cache is the primary reason Pro-Context can meet its latency SLOs:

| Tool | Cache hit | No cache |
|------|-----------|----------|
| `get-library-info` | <50ms | <3s |
| `get-docs` | <100ms | <5s |
| `read-page` | <50ms | <3s |

---

## 2. Two-Tier Architecture

Pro-Context uses a two-tier cache: a bounded in-memory cache (Tier 1) backed by an unbounded SQLite cache (Tier 2).

```
Request
  │
  ▼
┌─────────────────────────────────┐
│  Tier 1: In-Memory Cache        │  AsyncTTLCache (LRU + TTL)
│  ~500 entries max               │  Sub-millisecond access
│  Evicts least-recently-used     │  Lost on server restart
│  entries when full              │
└────────────────┬────────────────┘
                 │ miss
                 ▼
┌─────────────────────────────────┐
│  Tier 2: SQLite Cache           │  Persistent (survives restart)
│  Unlimited entries              │  <10ms access
│  Evicts via scheduled cleanup   │  WAL mode for concurrent reads
│  (TTL-based deletion)           │
└────────────────┬────────────────┘
                 │ miss
                 ▼
┌─────────────────────────────────┐
│  llms.txt Fetcher               │  HTTP GET to documentation source
│  (network call)                 │  100ms–3s
│                                 │  Result stored in both tiers
└─────────────────────────────────┘
```

**Why two tiers?**

- Memory alone: Fast but lost on restart and bounded (can't hold everything). In HTTP mode (long-running server), the server restarts infrequently but the memory cache would miss everything across restarts.
- SQLite alone: Persistent but ~10x slower than memory. Fine for cache misses that hit SQLite, but not acceptable for hot entries requested many times.
- Both together: Hot entries stay in memory (sub-ms). Warm entries survive restarts via SQLite. Cold entries fetch from the network.

**Promotion**: When a request hits Tier 2 (SQLite) but not Tier 1 (memory), the entry is promoted to memory. This means a frequently-accessed entry that wasn't in memory (e.g., after a restart) will warm back into memory automatically after first access.

---

## 3. What Gets Cached (Three Domains)

The cache stores three distinct types of content, each with its own cache table and access pattern:

| Domain | What it stores | Key format | Shared by tools |
|--------|----------------|------------|-----------------|
| **TOC** | Parsed table of contents from a library's llms.txt | `toc:{libraryId}` | `get-library-info` |
| **Doc/Chunks** | BM25-ranked documentation content for a topic query | `doc:{libraryId}:{topicHash}` | `get-docs` |
| **Pages** | Full markdown content of a single documentation page | `page:{urlHash}` | `read-page`, `get-docs` |

**Why three separate domains?**

Each domain has a different access pattern and serves different tools:

- **TOC** is always the first thing fetched for a library. It's lightweight (just links and descriptions, no full content) and accessed frequently — every `get-library-info` call and every `get-docs` call needs the TOC to know which pages exist.

- **Doc/Chunks** are BM25-ranked results for a specific `(library, topic)` pair. These are per-topic, so the same library can have many doc cache entries — one per distinct topic the agent has asked about. These are medium-sized (a few hundred tokens of ranked content).

- **Pages** are full page content fetched by `read-page`. Pages are expensive (can be 10,000+ tokens) and are shared — if `get-docs` fetches a page to rank its chunks, and then the agent calls `read-page` on the same URL, the page cache serves the second request instantly without re-fetching.

---

## 4. Data Structures

### CacheEntry (doc_cache, toc_cache)

```python
@dataclass
class CacheEntry:
    key: str           # Cache key (SHA-256 hash)
    library_id: str    # Which library this content belongs to
    identifier: str    # Topic hash (get-docs) or URL (pages)
    content: str       # The cached content (markdown)
    source_url: str    # Where the content was fetched from
    content_hash: str  # SHA-256 hash of content (for freshness checking)
    fetched_at: datetime   # When first cached
    expires_at: datetime   # When TTL expires
    etag: str | None = None          # ETag header from source (if available)
    last_modified: str | None = None # Last-Modified header (if available)
```

### PageCacheEntry (page_cache)

```python
@dataclass
class PageCacheEntry:
    url: str           # Page URL (the cache key)
    content: str       # Full page content in markdown
    title: str         # Page title (from first # heading)
    total_tokens: int  # Total content length in estimated tokens
    content_hash: str  # SHA-256 hash (for freshness checking)
    fetched_at: datetime
    expires_at: datetime
    etag: str | None = None
    last_modified: str | None = None
```

The `etag` and `last_modified` fields are stored so that subsequent freshness checks can use a cheap HEAD request instead of re-fetching the full content. See [Section 9](#9-freshness-checking).

---

## 5. Tier 1: In-Memory Cache (AsyncTTLCache)

### The problem with off-the-shelf options

`cachetools.TTLCache` provides LRU eviction + TTL expiry, but it uses `threading.Lock` internally. Using `threading.Lock` in an asyncio application blocks the entire event loop while the lock is held. This is safe but prevents any other coroutine from running during that time.

`aiocache` is async-safe but has no LRU bounding — the cache can grow unbounded in memory.

**Solution**: A thin `AsyncTTLCache` wrapper around `cachetools.TTLCache` that uses `asyncio.Lock` only where needed.

### Why individual get/set don't need a lock

In asyncio's cooperative multitasking model, a coroutine only yields control at `await` points. A plain `dict.__setitem__` or `dict.__getitem__` (which TTLCache uses internally) contains no `await`. Therefore, it cannot be interrupted mid-operation by another coroutine. Individual reads and writes to the TTLCache are effectively atomic.

### Where a lock IS needed: cache stampede

The dangerous pattern is: check cache → miss → fetch from network → store result. This sequence crosses an `await` boundary (the network fetch). Multiple concurrent coroutines can all miss the same key, all trigger a network fetch, and all race to store the result. No data corruption happens (last write wins), but N network fetches happen instead of 1.

`AsyncTTLCache.get_or_set()` prevents this with a **per-key asyncio.Lock** and **double-checked locking**:

```python
async def get_or_set(self, key: str, fetch_fn) -> any:
    # Fast path: check without lock
    if key in self._cache:
        return self._cache[key]

    # Slow path: acquire per-key lock to serialize concurrent misses
    if key not in self._locks:
        self._locks[key] = asyncio.Lock()
    async with self._locks[key]:
        # Double-check: another coroutine may have filled it while we waited
        if key in self._cache:
            return self._cache[key]
        # We're the first — fetch and store
        result = await fetch_fn()
        self._cache[key] = result
        return result
```

**Double-check**: After acquiring the lock, the cache is checked again. If another coroutine fetched the same key while this one was waiting for the lock, the result is already there — no need to fetch again.

**Per-key locks**: Using a single global lock would serialize all cache misses, even for unrelated keys. Per-key locks let concurrent misses for different keys proceed in parallel.

### LRU eviction

TTLCache evicts the least-recently-used entry when `maxsize` is reached. This ensures memory stays bounded even if many distinct library/topic combinations are queried.

Default limits: 500 entries for the doc cache, 200 entries for the page cache (pages are larger). These are configurable.

---

## 6. Tier 2: SQLite Cache

### Tables

Three tables mirror the three cache domains:

```
doc_cache    — TOC entries + doc/chunk entries
page_cache   — Full page content
toc_cache    — Library table of contents
```

Each table has:
- The content itself
- `fetched_at` and `expires_at` timestamps (ISO 8601)
- `content_hash` for SHA-256 freshness comparison
- `etag` and `last_modified` for HTTP-level freshness
- `stale` flag (0 or 1) — set to 1 by registry updates (see [Section 11](#11-cache-invalidation))
- Indexes on `expires_at` and `stale` for efficient cleanup queries

### WAL mode

The database runs in WAL (Write-Ahead Logging) mode:

```sql
PRAGMA journal_mode = WAL
```

WAL allows concurrent reads and a single writer simultaneously. Without WAL, any write would block all reads. In HTTP mode (multiple concurrent tool calls), this matters — a background refresh writing to the cache should not block other requests reading from it.

### Persistence across restarts

SQLite survives server restarts. After a restart:
- The in-memory cache (Tier 1) is empty
- First requests for each library will hit SQLite (Tier 2) — fast, no network needed
- SQLite entries are promoted back into memory as they're accessed (warming the memory cache organically)

This means restarts don't produce a cold-start penalty in terms of latency — the SQLite tier keeps things fast.

### Cleanup job

A background job runs on a configurable interval (default: 60 minutes) to delete expired entries from SQLite:

```python
async def cleanup_expired_entries(db: aiosqlite.Connection) -> None:
    now = datetime.now().isoformat()
    await db.execute("DELETE FROM doc_cache WHERE expires_at < ?", (now,))
    await db.execute("DELETE FROM page_cache WHERE expires_at < ?", (now,))
    await db.execute("DELETE FROM toc_cache WHERE expires_at < ?", (now,))
    await db.commit()
```

The memory cache (TTLCache) evicts expired entries automatically. SQLite doesn't — it needs explicit cleanup.

---

## 7. Cache Keys

All cache keys are SHA-256 hashes of a domain-prefixed string. Hashing serves two purposes:
1. Fixed, predictable key length regardless of input length
2. No risk of special characters in a URL causing key collisions

```
TOC key:  SHA-256("toc:" + libraryId)
          → "toc:langchain" → "a3f9c2..."

Doc key:  SHA-256("doc:" + libraryId + ":" + normalizedTopic)
          → "doc:langchain:chat models" → "7b2e81..."

Page key: SHA-256("page:" + url)
          → "page:https://python.langchain.com/docs/..." → "c4d1a7..."
```

The domain prefix (`toc:`, `doc:`, `page:`) prevents accidental collisions between domains (e.g., if a libraryId happened to equal a URL hash).

---

## 8. TTL Strategy

All cache entries default to a **24-hour TTL**.

| Domain | TTL | Reasoning |
|--------|-----|-----------|
| TOC | 24 hours | Library TOCs change infrequently. A 24-hour window is acceptable; stale-while-revalidate handles cases where docs update mid-day. |
| Doc/Chunks | 24 hours | Same reasoning as TOC. |
| Pages | 24 hours | Full pages are the most expensive to re-fetch. Longer TTLs reduce redundant fetches. |

**Per-library overrides**: The configuration supports per-library TTL overrides for libraries that update documentation more frequently:

```yaml
library_overrides:
  openai:
    ttl_hours: 6    # OpenAI updates API docs frequently
  numpy:
    ttl_hours: 72   # NumPy docs are very stable
```

**What happens when TTL expires**: The entry is not deleted immediately. It is **served with `stale: true`** and a background refresh is triggered. The entry stays in the cache until either the refresh succeeds (updating the entry and resetting the TTL) or the maximum stale age (7 days) is reached, after which it is invalidated.

This is the stale-while-revalidate pattern — see [Section 10](#10-stale-while-revalidate-background-refresh).

---

## 9. Freshness Checking

When a background refresh runs for a stale entry, Pro-Context tries to avoid re-fetching the full content if it hasn't changed. There are three levels of freshness checking, tried in order:

### Level 1: ETag comparison

ETag is an HTTP header that represents the "version" of a resource. If the source returns an ETag, the server stores it in the `CacheEntry.etag` field. On refresh, a HEAD request is sent with `If-None-Match: {stored_etag}`. If the server returns `304 Not Modified`, the content hasn't changed — only `expires_at` is updated, no re-fetch needed.

```
Client → HEAD /llms.txt
         If-None-Match: "abc123"

Server ← 304 Not Modified         (content unchanged, ~100 bytes)
       OR
Server ← 200 OK + new ETag + body (content changed, full content)
```

### Level 2: Last-Modified comparison

If no ETag is available, the `Last-Modified` header is used instead, stored in `CacheEntry.last_modified`. A HEAD request with `If-Modified-Since: {stored_date}` checks if the content has changed since it was cached.

### Level 3: Content hash comparison

If neither ETag nor Last-Modified is available (some static file hosts don't send these), the full content is re-fetched and its SHA-256 hash is compared with `CacheEntry.content_hash`. If the hash matches, the content hasn't changed — update `expires_at` only. If the hash differs, update the cache entry with the new content.

Level 3 is the least efficient (requires a full GET) but works for any HTTP server. Most well-maintained documentation sites send at least `Last-Modified`.

---

## 10. Stale-While-Revalidate (Background Refresh)

The stale-while-revalidate pattern is the core of Pro-Context's freshness model:

**Principle**: Serve stale content immediately. Refresh in the background. Never make the caller wait for a network fetch just because the TTL expired.

```
TTL expired? → YES → Serve cached content with { stale: true }
                     ↓
                     Spawn background task:
                     1. check_freshness() — cheap HEAD request
                        → unchanged → extend expires_at → done
                        → changed (or error) → re-fetch full content
                     2. Re-fetch from llmsTxtUrl
                     3. Compare content_hash
                        → same → update expires_at only
                        → different → update full cache entry + reset TTL

TTL expired? → NO → Serve cached content with { stale: false }
```

### Handling refresh failures

If the background refresh fails (network error, documentation site down, HTTP 500):

1. **Continue serving stale content** with `stale: true` — better than returning an error
2. **Log a warning** with error details and next retry timestamp
3. **Retry on the next request** — the stale entry stays in cache and triggers another background refresh attempt next time it's requested (with exponential backoff after repeated failures)
4. **Maximum stale age: 7 days** — after 7 days without a successful refresh, the entry is invalidated. The next request will block on a fresh fetch. If that also fails, `SOURCE_UNAVAILABLE` error is returned.

### What `stale: true` means to the agent

The `stale` flag is surfaced to the MCP client in tool responses:

- `stale: false` — content is fresh (within TTL). Use confidently.
- `stale: true` — content is past TTL but could not yet be refreshed. In practice, documentation rarely changes day-to-day, so stale content is usually still accurate. The agent can:
  - Use the content as-is (appropriate most of the time)
  - Surface a note to the user ("documentation may be slightly outdated")
  - Decline to use it if absolute freshness is required (rare)

---

## 11. Cache Invalidation

Cache entries are invalidated through six distinct signals:

| Signal | Trigger | Action |
|--------|---------|--------|
| **TTL expiry** | `expires_at` timestamp passes | Entry served as stale; background refresh triggered |
| **Content hash mismatch** | Background refresh re-fetches and SHA-256 differs | Cache entry replaced with new content, TTL reset |
| **ETag / Last-Modified mismatch** | HEAD request in `check_freshness()` returns 200 (not 304) | Full re-fetch triggered |
| **Registry URL change** | Weekly registry update changes a library's `llmsTxtUrl` | All cache entries for that library marked `stale = 1` in a single batched UPDATE |
| **Manual invalidation** | Admin CLI command | Entry deleted from both memory and SQLite immediately |
| **Cleanup job** | Scheduled (every 60 minutes by default) | Expired entries deleted from SQLite |

### Registry URL change invalidation

When the weekly registry update is applied and a library's `llmsTxtUrl` has changed, the cached content (fetched from the old URL) is no longer valid. Pro-Context handles this with a bulk database update:

```sql
-- All cache entries for the affected library are marked stale atomically
UPDATE doc_cache SET stale = 1 WHERE library_id IN (?) -- batched
UPDATE page_cache SET stale = 1 WHERE library_id IN (?)
UPDATE toc_cache  SET stale = 1 WHERE library_id IN (?)
```

This runs in a single transaction. Stale entries continue to be served immediately (no service disruption) while background refreshes re-fetch from the new URL.

Only `llmsTxtUrl` changes trigger invalidation. Changes to other registry fields (name, description, etc.) don't affect cached documentation content.

---

## 12. Read Flow

This is the complete path a cache lookup takes, from an incoming tool call to the response.

```
Tool call: get-docs("langchain", "streaming")
  │
  ▼
Compute cache key:
  SHA-256("doc:langchain:" + normalize("streaming"))
  → "7b2e81..."
  │
  ▼
Tier 1: Memory check
  cache.get("7b2e81...")
  │
  ├─ HIT (not expired) → return entry, stale: false
  │
  ├─ HIT (expired) → return entry, stale: true
  │                   → spawn background refresh
  │
  └─ MISS → continue to Tier 2
  │
  ▼
Tier 2: SQLite check
  SELECT * FROM doc_cache WHERE key = "7b2e81..."
  │
  ├─ HIT (not expired) → promote to memory, return entry, stale: false
  │
  ├─ HIT (expired) → promote to memory, return entry, stale: true
  │                   → spawn background refresh
  │
  └─ MISS → continue to network
  │
  ▼
Network fetch:
  GET {library.llmsTxtUrl}
  Parse → BM25 rank → extract relevant chunks
  │
  ▼
Store in both tiers:
  memory.set("7b2e81...", entry)
  await sqlite.set("7b2e81...", entry)
  │
  ▼
Return entry, stale: false
```

Note that when an expired entry is found in either tier, it is returned immediately — the caller does not wait for the background refresh. This is what makes stale-while-revalidate effective for latency.

---

## 13. Write Flow

After a successful network fetch, the result is written to both cache tiers simultaneously (memory is synchronous, SQLite is awaited):

```python
async def set(self, key: str, entry: CacheEntry) -> None:
    self.memory.set(key, entry)        # synchronous, in-memory
    await self.sqlite.set(key, entry)  # async, persisted to disk
```

Both writes happen before the response is returned to the caller, so the next request for the same key will always hit the cache.

### Write on promotion

When a Tier 2 (SQLite) hit is promoted to Tier 1 (memory), the write is to memory only — no round-trip to SQLite needed:

```python
# Found in SQLite → promote to memory
self.memory.set(key, sql_result)
return sql_result
```

---

## 14. Page Cache: Offset-Based Slicing

The page cache has a special capability: `read-page` supports pagination via `offset` and `maxTokens`. Rather than re-fetching the page for each "next page" request, the full page content is cached once and slices are served from the cache.

```python
async def get_slice(self, url: str, offset: int, max_tokens: int) -> PageResult | None:
    page = await self.get_page(url)  # Full page from cache
    if not page:
        return None

    # Token → character position (1 token ≈ 4 chars)
    start_char = offset * 4
    max_chars = max_tokens * 4
    slice_content = page.content[start_char : start_char + max_chars]

    return PageResult(
        content=slice_content,
        total_tokens=page.total_tokens,
        offset=offset,
        tokens_returned=len(slice_content) // 4,
        has_more=start_char + max_chars < len(page.content),
        cached=True,
    )
```

**Example**: An agent reads a 15,000-token page in three calls:

```
read-page(url, offset=0, maxTokens=5000)   → returns tokens 0–5000   (fetches, caches)
read-page(url, offset=5000, maxTokens=5000) → returns tokens 5000–10000 (cache hit, slice)
read-page(url, offset=10000, maxTokens=5000) → returns tokens 10000–15000 (cache hit, slice)
```

Only the first call hits the network. The subsequent two serve from the cached full-page content. The `has_more: false` on the third call tells the agent it has reached the end.

The page is stored with `cached: true` in the response to distinguish it from a live fetch.

---

## 15. Configuration

All cache behaviour is controlled through `config.yaml`:

```yaml
cache:
  directory: "~/.local/share/pro-context"  # SQLite database location
  max_memory_mb: 256                        # Soft limit on memory cache size
  max_memory_entries: 500                   # Hard limit on memory cache entries
  default_ttl_hours: 24                     # Default TTL for all cache entries
  cleanup_interval_minutes: 60             # How often to run the SQLite cleanup job

library_overrides:
  # Override TTL for specific libraries
  openai:
    ttl_hours: 6
  numpy:
    ttl_hours: 72
```

**Environment variable override**: `PRO_CONTEXT_DEBUG=true` sets logging level to debug, which includes verbose cache hit/miss logging (useful for debugging cache behaviour).

**Health resource**: The `pro-context://health` MCP resource exposes current cache statistics:

```json
{
  "cache": {
    "memoryEntries": 142,
    "memoryBytes": 52428800,
    "sqliteEntries": 1024,
    "hitRate": 0.87
  }
}
```

A `hitRate` consistently below 0.5 in HTTP mode (long-running server) suggests the cache is being evicted too aggressively — consider increasing `max_memory_entries`.
