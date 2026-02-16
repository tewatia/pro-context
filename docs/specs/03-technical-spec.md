# Pro-Context: Technical Specification

> **Document**: 03-technical-spec.md
> **Status**: Draft v2
> **Last Updated**: 2026-02-16
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
- [4. Source Adapter Interface](#4-source-adapter-interface)
  - [4.1 Interface Definition](#41-interface-definition)
  - [4.2 Adapter Chain Execution](#42-adapter-chain-execution)
  - [4.3 Adapter Implementations](#43-adapter-implementations)
- [5. Cache Architecture](#5-cache-architecture)
  - [5.1 Two-Tier Cache Design](#51-two-tier-cache-design)
  - [5.2 Cache Domains](#52-cache-domains)
  - [5.3 Cache Manager](#53-cache-manager)
  - [5.4 Page Cache](#54-page-cache)
  - [5.5 Cache Key Strategy](#55-cache-key-strategy)
  - [5.6 Cache Invalidation Signals](#56-cache-invalidation-signals)
  - [5.7 Background Refresh](#57-background-refresh)
- [6. Search Engine Design](#6-search-engine-design)
  - [6.1 Document Chunking Strategy](#61-document-chunking-strategy)
  - [6.2 BM25 Search Implementation](#62-bm25-search-implementation)
  - [6.3 Cross-Library Search](#63-cross-library-search)
  - [6.4 Incremental Indexing](#64-incremental-indexing)
  - [6.5 Ranking and Token Budgeting](#65-ranking-and-token-budgeting)
- [7. Token Efficiency Strategy](#7-token-efficiency-strategy)
  - [7.1 Target Metrics](#71-target-metrics)
  - [7.2 Techniques](#72-techniques)
  - [7.3 Token Counting](#73-token-counting)
- [8. Transport Layer](#8-transport-layer)
  - [8.1 stdio Transport (Local Mode)](#81-stdio-transport-local-mode)
  - [8.2 Streamable HTTP Transport (HTTP Mode)](#82-streamable-http-transport-http-mode)
- [9. Authentication and API Key Management](#9-authentication-and-api-key-management)
  - [9.1 Key Generation](#91-key-generation)
  - [9.2 Key Validation Flow](#92-key-validation-flow)
  - [9.3 Admin CLI](#93-admin-cli)
- [10. Rate Limiting Design](#10-rate-limiting-design)
  - [10.1 Token Bucket Algorithm](#101-token-bucket-algorithm)
  - [10.2 Rate Limit Headers](#102-rate-limit-headers)
  - [10.3 Per-Key Overrides](#103-per-key-overrides)
- [11. Security Model](#11-security-model)
  - [11.1 Input Validation](#111-input-validation)
  - [11.2 SSRF Prevention](#112-ssrf-prevention)
  - [11.3 Secret Redaction](#113-secret-redaction)
  - [11.4 Content Sanitization](#114-content-sanitization)
- [12. Observability](#12-observability)
  - [12.1 Structured Logging](#121-structured-logging)
  - [12.2 Key Metrics](#122-key-metrics)
  - [12.3 Health Check](#123-health-check)
- [13. Extensibility Points](#13-extensibility-points)
  - [13.1 Adding a New Language](#131-adding-a-new-language)
  - [13.2 Adding a New Documentation Source](#132-adding-a-new-documentation-source)
  - [13.3 Adding a New Tool](#133-adding-a-new-tool)
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
│  │  │       Source Adapters            │   │             │
│  │  │  ┌────────┐ ┌───────┐ ┌───────┐ │   │             │
│  │  │  │llms.txt│ │GitHub │ │Custom │ │   │             │
│  │  │  │Adapter │ │Adapter│ │Adapter│ │   │             │
│  │  │  └────────┘ └───────┘ └───────┘ │   │             │
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
│  │  │ (pino) │ │        │ │              │  │           │
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
  │    ├─ 1. Fuzzy match against known-libraries registry
  │    ├─ 2. If no match → query PyPI API
  │    ├─ 3. If still no match → return empty results
  │    └─ 4. Return ranked matches with { libraryId, name, languages, relevance }
  │
  ├─ get-library-info("langchain-ai/langchain")
  │    │
  │    ├─ 1. Look up libraryId in registry (exact match)
  │    ├─ 2. If not found → attempt package registry resolution
  │    ├─ 3. Resolve version (latest stable if omitted)
  │    ├─ 4. Fetch TOC via adapter chain (llms.txt → GitHub → Custom)
  │    ├─ 5. Extract availableSections from TOC
  │    ├─ 6. Apply sections filter if specified
  │    ├─ 7. Cache TOC, add to session resolved list
  │    └─ 8. Return { libraryId, versions, sources, toc, availableSections }
  │
  ├─ get-docs([{libraryId: "langchain-ai/langchain", version: "0.3.14"}], "chat models")
  │    │
  │    ├─ 1. For each library: resolve version
  │    ├─ 2. Cache lookup: memory LRU → SQLite
  │    │    ├─ HIT (fresh) → use cached content
  │    │    ├─ HIT (stale) → use cached + trigger background refresh
  │    │    └─ MISS → continue to step 3
  │    ├─ 3. Adapter chain: llms.txt → GitHub → Custom
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
| Language | TypeScript | 5.x (strict) | Type safety, MCP SDK is TS-first |
| Runtime | Node.js | 20+ LTS | Native fetch, web crypto, stable |
| MCP SDK | `@modelcontextprotocol/sdk` | latest | Official SDK, maintained by protocol authors |
| Schema validation | Zod | 3.x | Required by MCP SDK, excellent TS integration |
| Persistent cache | SQLite via `better-sqlite3` | 11.x | Zero-config, embedded, fast, synchronous API |
| In-memory cache | `lru-cache` | 10.x | O(1) get/set, configurable size limits |
| HTTP client | Native `fetch` (Node 20+) | — | Built-in, no dependency needed |
| Search/ranking | BM25 via SQLite FTS5 | — | FTS5 for indexing + custom BM25 scoring; no embedding dependency |
| Logging | `pino` | 9.x | Structured JSON, low overhead, redaction support |
| Testing | `vitest` | 2.x | Fast, TS-native, ESM support |
| Build | `tsup` | 8.x | Fast bundling, ESM + CJS output |
| Lint + Format | Biome | 1.x | All-in-one, fast, no config overhead |
| YAML parsing | `yaml` | 2.x | Config file parsing |

### Dependency Justification

- **No vector database**: BM25 handles keyword-heavy documentation search well without requiring an embedding model. Vector search (FTS5 + embeddings) is deferred to a future phase to avoid OpenAI/Ollama dependency.
- **No Redis**: SQLite provides sufficient persistence for cache. No external infrastructure needed.
- **No Express/Fastify**: MCP SDK handles HTTP transport internally. No web framework needed.
- **`better-sqlite3` over `sql.js`**: Synchronous API is simpler; native bindings are faster. Acceptable trade-off: requires native compilation.

---

## 3. Data Models

### 3.1 Core Types

```typescript
// ===== Library Types =====

interface LibraryMatch {
  /** Canonical identifier (e.g., "langchain-ai/langchain") */
  libraryId: string;
  /** Human-readable name (e.g., "LangChain") */
  name: string;
  /** Brief description */
  description: string;
  /** Languages this library is available in */
  languages: string[];
  /** Match relevance score (0-1) */
  relevance: number;
}

interface Library {
  /** Canonical identifier (e.g., "langchain-ai/langchain") */
  id: string;
  /** Human-readable name (e.g., "LangChain") */
  name: string;
  /** Brief description */
  description: string;
  /** Languages this library is available in */
  languages: string[];
  /** Package name in registry (e.g., "langchain" on PyPI) */
  packageName: string;
  /** Documentation site URL */
  docsUrl: string | null;
  /** GitHub repository URL */
  repoUrl: string | null;
  /** Available versions (most recent first) */
  versions: string[];
  /** Recommended default version (latest stable) */
  defaultVersion: string;
}

// ===== TOC Types =====

interface TocEntry {
  /** Page title */
  title: string;
  /** Page URL (can be passed to read-page) */
  url: string;
  /** One-sentence description */
  description: string;
  /** Section grouping (e.g., "Getting Started", "API Reference") */
  section: string;
}

interface LibraryInfo {
  libraryId: string;
  name: string;
  /** Informational metadata — not used for routing or validation */
  languages: string[];
  defaultVersion: string;
  availableVersions: string[];
  sources: string[];
  toc: TocEntry[];
  availableSections: string[];
  filteredBySections?: string[];
}

// ===== Documentation Types =====

interface DocResult {
  /** Which library this content is from */
  libraryId: string;
  /** Documentation content in markdown */
  content: string;
  /** URL where documentation was fetched from */
  source: string;
  /** Exact version of documentation */
  version: string;
  /** When documentation was last fetched/verified */
  lastUpdated: string; // ISO 8601
  /** Relevance confidence (0-1) */
  confidence: number;
  /** Whether result was served from cache */
  cached: boolean;
  /** Whether cached content may be outdated */
  stale: boolean;
  /** Related pages the agent can explore */
  relatedPages: RelatedPage[];
}

interface RelatedPage {
  title: string;
  url: string;
  description: string;
}

interface DocChunk {
  /** Chunk identifier */
  id: string;
  /** Library this chunk belongs to */
  libraryId: string;
  /** Library version */
  version: string;
  /** Section title/heading */
  title: string;
  /** Chunk content in markdown */
  content: string;
  /** Hierarchical section path (e.g., "Getting Started > Chat Models > Streaming") */
  sectionPath: string;
  /** Approximate token count */
  tokenCount: number;
  /** Source URL */
  sourceUrl: string;
}

interface SearchResult {
  /** Which library this result is from */
  libraryId: string;
  /** Section/page title */
  title: string;
  /** Relevant text excerpt */
  snippet: string;
  /** BM25 relevance score (0-1 normalized) */
  relevance: number;
  /** Source URL — use read-page to fetch full content */
  url: string;
  /** Documentation section path */
  section: string;
}

// ===== Page Types =====

interface PageResult {
  /** Page content in markdown */
  content: string;
  /** Page title */
  title: string;
  /** Canonical URL */
  url: string;
  /** Total page content length in estimated tokens */
  totalTokens: number;
  /** Token offset this response starts from */
  offset: number;
  /** Number of tokens in this response */
  tokensReturned: number;
  /** Whether more content exists beyond this response */
  hasMore: boolean;
  /** Whether page was served from cache */
  cached: boolean;
}

// ===== Error Types =====

type ErrorCode =
  | "LIBRARY_NOT_FOUND"
  | "VERSION_NOT_FOUND"
  | "TOPIC_NOT_FOUND"
  | "PAGE_NOT_FOUND"
  | "URL_NOT_ALLOWED"
  | "INVALID_CONTENT"
  | "SOURCE_UNAVAILABLE"
  | "REGISTRY_TIMEOUT"
  | "RATE_LIMITED"
  | "INDEXING_IN_PROGRESS"
  | "AUTH_REQUIRED"
  | "AUTH_INVALID"
  | "INTERNAL_ERROR";

interface ProContextError {
  /** Machine-readable error code */
  code: ErrorCode;
  /** Human-readable error description */
  message: string;
  /** Whether the error can be resolved by retrying or changing input */
  recoverable: boolean;
  /** Actionable suggestion for the user/agent */
  suggestion: string;
  /** Seconds to wait before retrying (if applicable) */
  retryAfter?: number;
}
```

### 3.2 Cache Types

```typescript
interface CacheEntry {
  /** Cache key */
  key: string;
  /** Library identifier */
  libraryId: string;
  /** Library version */
  version: string;
  /** Topic hash (for get-docs cache) or URL (for page cache) */
  identifier: string;
  /** Cached content */
  content: string;
  /** Source URL */
  sourceUrl: string;
  /** Content SHA-256 hash (for freshness checking) */
  contentHash: string;
  /** When this entry was created */
  fetchedAt: string; // ISO 8601
  /** When this entry expires */
  expiresAt: string; // ISO 8601
  /** Name of the adapter that produced this content */
  adapter: string;
}

interface PageCacheEntry {
  /** Page URL (cache key) */
  url: string;
  /** Full page content in markdown */
  content: string;
  /** Page title */
  title: string;
  /** Total content length in estimated tokens */
  totalTokens: number;
  /** Content SHA-256 hash */
  contentHash: string;
  /** When this page was fetched */
  fetchedAt: string; // ISO 8601
  /** When this entry expires */
  expiresAt: string; // ISO 8601
}

interface CacheStats {
  /** Number of entries in memory cache */
  memoryEntries: number;
  /** Memory cache size in bytes */
  memoryBytes: number;
  /** Number of entries in SQLite cache */
  sqliteEntries: number;
  /** Cache hit rate (0-1) */
  hitRate: number;
}
```

### 3.3 Auth Types (HTTP Mode)

```typescript
interface ApiKey {
  /** Unique key identifier (UUID) */
  id: string;
  /** Display name for the key */
  name: string;
  /** SHA-256 hash of the actual key (never store plaintext) */
  keyHash: string;
  /** Key prefix for display (first 8 chars) */
  keyPrefix: string;
  /** Per-key rate limit (requests per minute, null = use default) */
  rateLimitPerMinute: number | null;
  /** When this key was created */
  createdAt: string; // ISO 8601
  /** When this key was last used */
  lastUsedAt: string | null; // ISO 8601
  /** Total number of requests made with this key */
  requestCount: number;
  /** Whether this key is active */
  active: boolean;
}
```

### 3.4 Configuration Types

```typescript
interface ProContextConfig {
  server: {
    transport: "stdio" | "http";
    port: number;
    host: string;
  };
  cache: {
    directory: string;
    maxMemoryMB: number;
    maxMemoryEntries: number;
    defaultTTLHours: number;
    cleanupIntervalMinutes: number;
  };
  sources: {
    llmsTxt: { enabled: boolean };
    github: { enabled: boolean; token: string };
    custom: CustomSource[];
  };
  libraryOverrides: Record<string, LibraryOverride>;
  rateLimit: {
    maxRequestsPerMinute: number;
    burstSize: number;
  };
  logging: {
    level: "debug" | "info" | "warn" | "error";
    format: "json" | "pretty";
  };
  security: {
    cors: { origins: string[] };
    urlAllowlist: string[];
  };
}

// Note: PRO_CONTEXT_DEBUG=true is a shorthand env var that sets logging.level to "debug"
// See functional spec section 12 for full env var override table

interface CustomSource {
  name: string;
  type: "url" | "file" | "github";
  url?: string;
  path?: string;
  libraryId: string;
  ttlHours?: number;
}

interface LibraryOverride {
  docsUrl?: string;
  source?: string;
  ttlHours?: number;
}
```

---

## 4. Source Adapter Interface

### 4.1 Interface Definition

```typescript
interface SourceAdapter {
  /** Unique adapter name (e.g., "llms-txt", "github", "custom") */
  readonly name: string;

  /** Priority order (lower = higher priority) */
  readonly priority: number;

  /**
   * Check if this adapter can serve documentation for the given library.
   * Should be cheap (no network requests if possible).
   */
  canHandle(library: Library): Promise<boolean>;

  /**
   * Fetch the table of contents for the given library.
   * Returns structured TOC entries parsed from llms.txt, GitHub /docs/, etc.
   */
  fetchToc(library: Library, version: string): Promise<TocEntry[] | null>;

  /**
   * Fetch a single documentation page and return markdown content.
   * Used by read-page and internally by get-docs for JIT content fetching.
   */
  fetchPage(url: string): Promise<RawPageContent | null>;

  /**
   * Check if the cached version is still fresh.
   * Uses SHA comparison, ETags, or Last-Modified headers.
   * Returns true if cache is still valid (no refetch needed).
   */
  checkFreshness(library: Library, cached: CacheEntry): Promise<boolean>;
}

interface RawPageContent {
  /** Page content in markdown */
  content: string;
  /** Page title (extracted from first heading or URL) */
  title: string;
  /** Canonical source URL */
  sourceUrl: string;
  /** Content SHA-256 hash */
  contentHash: string;
  /** ETag header value (if available) */
  etag?: string;
  /** Last-Modified header value (if available) */
  lastModified?: string;
}
```

### 4.2 Adapter Chain Execution

```typescript
class AdapterChain {
  private adapters: SourceAdapter[]; // sorted by priority

  async fetchToc(library: Library, version: string): Promise<TocEntry[]> {
    const errors: Error[] = [];

    for (const adapter of this.adapters) {
      if (!(await adapter.canHandle(library))) continue;

      try {
        const result = await adapter.fetchToc(library, version);
        if (result !== null) return result;
      } catch (error) {
        errors.push(error);
      }
    }

    throw new AllAdaptersFailedError(errors);
  }

  async fetchPage(url: string): Promise<RawPageContent> {
    const errors: Error[] = [];

    for (const adapter of this.adapters) {
      try {
        const result = await adapter.fetchPage(url);
        if (result !== null) return result;
      } catch (error) {
        errors.push(error);
      }
    }

    throw new AllAdaptersFailedError(errors);
  }
}
```

### 4.3 Adapter Implementations

#### llms.txt Adapter

```
canHandle(library):
  1. Check if library.docsUrl is set
  2. Return true if docsUrl is not null

fetchToc(library, version):
  1. Fetch {library.docsUrl}/llms.txt
  2. If 404, return null
  3. Parse markdown: extract ## headings as sections, list items as entries
  4. For each entry: extract title, URL, description
  5. Return TocEntry[]

fetchPage(url):
  1. Try {url}.md first (Mintlify pattern — returns clean markdown)
  2. If .md fails, fetch the URL directly
  3. If HTML response, convert to markdown (strip nav, headers, footers)
  4. Extract title from first heading
  5. Return { content, title, sourceUrl, contentHash }

checkFreshness(library, cached):
  1. HEAD request to source URL
  2. Compare ETag or Last-Modified headers
  3. If no headers available, compare content SHA
  4. Return true if cache is still valid
```

#### GitHub Adapter

```
canHandle(library):
  1. Check if library.repoUrl is set and is a GitHub URL
  2. Return true if valid GitHub repo

fetchToc(library, version):
  1. Resolve version to git tag via GitHub API
  2. Fetch /docs/ directory listing from repo
  3. If /docs/ exists → create TocEntry per file, using directories as sections
  4. If no /docs/ → parse README.md headings as TOC entries
  5. Generate GitHub raw URLs for each entry
  6. Return TocEntry[]

fetchPage(url):
  1. Fetch the raw file from GitHub at the resolved version tag
  2. Return as markdown { content, title, sourceUrl, contentHash }

checkFreshness(library, cached):
  1. GET commit SHA for the version tag from GitHub API
  2. Compare against cached SHA
  3. Return true if SHA matches (content unchanged)
```

#### Custom Adapter

```
canHandle(library):
  1. Check if library.id matches any custom source config
  2. Return true if match found

fetchToc(library, version):
  1. Determine source type (url, file, github)
  2. For "url": fetch URL, parse as llms.txt format
  3. For "file": read local file, parse as llms.txt format
  4. For "github": delegate to GitHub adapter logic
  5. Return TocEntry[]

fetchPage(url):
  1. Determine source type from URL/path
  2. For "url": fetch URL content
  3. For "file": read local file
  4. Return { content, title, sourceUrl, contentHash }

checkFreshness(library, cached):
  1. For "url": HEAD request + ETag/Last-Modified
  2. For "file": Check file modification time
  3. For "github": Compare commit SHA
  4. Return true if cache is still valid
```

---

## 5. Cache Architecture

### 5.1 Two-Tier Cache Design

```
Query → Memory LRU (Tier 1) → SQLite (Tier 2) → Source Adapters
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
| **TOC** | `toc:{libraryId}:{version}` | Parsed TocEntry[] | 24 hours |
| **Docs/Chunks** | `doc:{libraryId}:{version}:{topicHash}` | BM25-matched content | 24 hours |
| **Pages** | `page:{urlHash}` | Full page markdown | 24 hours |

Pages are cached separately because they're shared across tools — `read-page` and `get-docs` both benefit from cached pages.

### 5.3 Cache Manager

```typescript
class CacheManager {
  private memory: LRUCache<string, CacheEntry>;
  private sqlite: SqliteCache;

  async get(key: string): Promise<CacheEntry | null> {
    // Tier 1: Memory
    const memResult = this.memory.get(key);
    if (memResult && !this.isExpired(memResult)) {
      return memResult;
    }

    // Tier 2: SQLite
    const sqlResult = await this.sqlite.get(key);
    if (sqlResult && !this.isExpired(sqlResult)) {
      // Promote to memory cache
      this.memory.set(key, sqlResult);
      return sqlResult;
    }

    // Return stale entry if exists (caller decides whether to use it)
    return sqlResult ?? memResult ?? null;
  }

  async set(key: string, entry: CacheEntry): Promise<void> {
    // Write to both tiers
    this.memory.set(key, entry);
    await this.sqlite.set(key, entry);
  }

  async invalidate(key: string): Promise<void> {
    this.memory.delete(key);
    await this.sqlite.delete(key);
  }
}
```

### 5.4 Page Cache

Pages fetched by `read-page` are cached in full. Offset-based reads serve slices from the cached page without re-fetching.

```typescript
class PageCache {
  private memory: LRUCache<string, PageCacheEntry>;
  private sqlite: SqlitePageCache;

  async getPage(url: string): Promise<PageCacheEntry | null> {
    // Same two-tier pattern as CacheManager
  }

  async getSlice(url: string, offset: number, maxTokens: number): Promise<PageResult | null> {
    const page = await this.getPage(url);
    if (!page) return null;

    // Estimate character positions from token counts (1 token ≈ 4 chars)
    const startChar = offset * 4;
    const maxChars = maxTokens * 4;
    const slice = page.content.substring(startChar, startChar + maxChars);
    const tokensReturned = Math.ceil(slice.length / 4);

    return {
      content: slice,
      title: page.title,
      url,
      totalTokens: page.totalTokens,
      offset,
      tokensReturned,
      hasMore: startChar + maxChars < page.content.length,
      cached: true,
    };
  }
}
```

### 5.5 Cache Key Strategy

```
TOC key:  SHA-256("toc:" + libraryId + ":" + version)
Doc key:  SHA-256("doc:" + libraryId + ":" + version + ":" + normalizedTopic)
Page key: SHA-256("page:" + url)
```

### 5.6 Cache Invalidation Signals

| Signal | Trigger | Action |
|--------|---------|--------|
| TTL expiry | Automatic | Entry marked stale; served with `stale: true` |
| SHA mismatch | `checkFreshness()` on read | Refetch from source, update cache |
| Version change | PyPI/npm shows new version | Old version cache untouched; new version fetched on demand |
| Manual invalidation | Admin CLI command | Delete entry from both tiers |
| Cleanup job | Scheduled (configurable interval) | Delete all expired entries from SQLite |

### 5.7 Background Refresh

When a stale cache entry is served, a background refresh is triggered:

```
1. Return stale content immediately (with stale: true)
2. Spawn background task:
   a. Fetch fresh content from adapter chain
   b. Compare content hash with cached
   c. If changed → update cache entry
   d. If unchanged → update expiresAt timestamp only
```

---

## 6. Search Engine Design

### 6.1 Document Chunking Strategy

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

### 6.2 BM25 Search Implementation

BM25 (Best Match 25) is used for keyword-based relevance ranking.

**Parameters:**
- `k1 = 1.5` (term frequency saturation)
- `b = 0.75` (document length normalization)

**Index structure:**

```
For each chunk:
  1. Tokenize content (lowercase, strip punctuation)
  2. Compute term frequencies (TF)
  3. Store in inverted index: term → [(chunkId, TF), ...]

Global:
  - Document count (N)
  - Average document length (avgDL)
  - Document frequencies (DF): term → count of docs containing term
```

**Query execution:**

```
1. Tokenize query
2. For each query term:
   a. Look up inverted index → get matching chunks with TF
   b. Compute IDF: log((N - DF + 0.5) / (DF + 0.5) + 1)
   c. For each matching chunk:
      - Compute BM25 score: IDF * (TF * (k1 + 1)) / (TF + k1 * (1 - b + b * DL/avgDL))
3. Sum BM25 scores across query terms for each chunk
4. Sort by total score (descending)
5. Normalize scores to 0-1 range
6. Return top N results
```

### 6.3 Cross-Library Search

When `search-docs` is called without `libraryIds`, it searches across all indexed content. The BM25 index contains chunks from all libraries, each tagged with their `libraryId`. Results are ranked globally — a highly relevant chunk from library A ranks above a marginally relevant chunk from library B.

The `searchedLibraries` field in the response lists which libraries had indexed content at query time, so the agent knows the search scope.

### 6.4 Incremental Indexing

Pages are indexed for BM25 as they're fetched — by `get-docs` (JIT fetch), `get-library-info` (TOC fetch), and `read-page` (page fetch). The search index grows organically as the agent uses Pro-Context. There is no upfront bulk indexing step.

### 6.5 Ranking and Token Budgeting

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

## 7. Token Efficiency Strategy

### 7.1 Target Metrics

| Metric | Target | Benchmark |
|--------|--------|-----------|
| Avg tokens per response (get-docs) | <3,000 | Deepcon: 2,365 |
| Accuracy | >85% | Deepcon: 90% |
| Tokens per correct answer | <3,529 | Deepcon: 2,628 |

### 7.2 Techniques

1. **Focused chunking**: Split docs into small, self-contained sections (target: 500 tokens/chunk)
2. **Relevance ranking**: BM25 ensures only relevant chunks are returned
3. **Token budgeting**: `maxTokens` parameter caps response size (default: 5,000 for get-docs, 10,000 for read-page)
4. **Snippet generation**: `search-docs` returns snippets (~100 tokens each), not full content
5. **Section targeting**: Use heading hierarchy to find the most specific relevant section
6. **Offset-based reading**: `read-page` returns slices of large pages, avoiding re-sending content the agent has already seen
7. **TOC section filtering**: `get-library-info` with `sections` parameter returns only relevant sections of large TOCs

### 7.3 Token Counting

Approximate token count using character count / 4. This is sufficient for budgeting purposes — exact token counts are model-specific and not needed.

---

## 8. Transport Layer

### 8.1 stdio Transport (Local Mode)

```typescript
// src/index.ts
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server({ name: "pro-context", version: "1.0.0" }, {
  capabilities: {
    tools: {},
    resources: { subscribe: false },
    prompts: {},
  },
});

// Register tools, resources, prompts...

const transport = new StdioServerTransport();
await server.connect(transport);
```

**Characteristics:**
- Zero configuration
- No authentication required
- Single-user (one client connection)
- Communication via stdin/stdout
- Process lifecycle managed by MCP client

### 8.2 Streamable HTTP Transport (HTTP Mode)

```typescript
// src/index.ts (HTTP mode)
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

const server = new Server({ name: "pro-context", version: "1.0.0" }, {
  capabilities: {
    tools: {},
    resources: { subscribe: false },
    prompts: {},
  },
});

// Register tools, resources, prompts...

const transport = new StreamableHTTPServerTransport({
  sessionIdGenerator: () => crypto.randomUUID(),
});

// HTTP server setup with auth middleware
import { createServer } from "node:http";

const httpServer = createServer(async (req, res) => {
  // Auth middleware
  if (!authenticateRequest(req)) {
    res.writeHead(401);
    res.end(JSON.stringify({ code: "AUTH_REQUIRED", message: "..." }));
    return;
  }

  // Rate limit middleware
  if (!rateLimitCheck(req)) {
    res.writeHead(429);
    res.end(JSON.stringify({ code: "RATE_LIMITED", message: "..." }));
    return;
  }

  // Delegate to MCP transport
  await transport.handleRequest(req, res);
});

httpServer.listen(config.server.port, config.server.host);
```

**Characteristics:**
- Requires API key authentication
- Multi-user (concurrent connections)
- Shared documentation cache across all users
- Supports Streamable HTTP as per MCP spec (2025-11-25)
- Per-key rate limiting
- CORS configuration

---

## 9. Authentication and API Key Management

### 9.1 Key Generation

```
1. Generate 32 random bytes using crypto.randomBytes()
2. Encode as base64url → this is the API key (43 chars)
3. Compute SHA-256 hash of the key
4. Store only the hash + prefix (first 8 chars) in SQLite
5. Return the full key to the admin (shown once, never stored)
```

**Key format**: `pc_` prefix + 40 chars base64url = `pc_aBcDeFgH...` (43 chars total)

### 9.2 Key Validation Flow

```
1. Extract Bearer token from Authorization header
2. Compute SHA-256 hash of the provided token
3. Look up hash in api_keys table
4. If found and active → authenticated
5. If found but inactive → AUTH_INVALID
6. If not found → AUTH_INVALID
7. Update last_used_at and request_count
```

### 9.3 Admin CLI

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

The admin CLI is a separate entry point (`src/auth/admin-cli.ts`) that operates directly on the SQLite database.

---

## 10. Rate Limiting Design

### 10.1 Token Bucket Algorithm

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

### 10.2 Rate Limit Headers

HTTP responses include rate limit headers:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1707700000
```

### 10.3 Per-Key Overrides

API keys can have custom rate limits:

```sql
-- api_keys table includes rate_limit_per_minute column
-- NULL means use default from config
SELECT rate_limit_per_minute FROM api_keys WHERE key_hash = ?;
```

---

## 11. Security Model

### 11.1 Input Validation

All inputs are validated at the MCP boundary using Zod schemas before any processing:

```typescript
const GetDocsInput = z.object({
  libraries: z.array(z.object({
    libraryId: z.string().min(1).max(200).regex(/^[a-zA-Z0-9\-_./]+$/),
    version: z.string().max(50).optional(),
  })).min(1).max(10),
  topic: z.string().min(1).max(500),
  maxTokens: z.number().int().min(500).max(10000).default(5000),
});

const ReadPageInput = z.object({
  url: z.string().url().max(2000),
  maxTokens: z.number().int().min(500).max(50000).default(10000),
  offset: z.number().int().min(0).default(0),
});
```

### 11.2 SSRF Prevention

URL fetching is restricted to known documentation domains:

```typescript
const DEFAULT_ALLOWLIST = [
  "github.com",
  "raw.githubusercontent.com",
  "pypi.org",
  "registry.npmjs.org",
  "*.readthedocs.io",
  "*.github.io",
];

function isAllowedUrl(url: string, allowlist: string[]): boolean {
  const parsed = new URL(url);
  return allowlist.some(pattern => matchDomain(parsed.hostname, pattern));
}
```

- No fetching of private IPs (127.0.0.1, 10.x, 192.168.x, etc.)
- No fetching of file:// URLs
- URLs must come from resolved TOCs, search results, relatedPages, or configured allowlist
- Custom sources in config are added to the allowlist
- **Dynamic expansion**: When an llms.txt file is fetched, all URLs in it are added to the session allowlist

### 11.3 Secret Redaction

Pino logger is configured with redaction paths:

```typescript
const logger = pino({
  redact: {
    paths: [
      "req.headers.authorization",
      "config.sources.github.token",
      "*.apiKey",
      "*.token",
    ],
    censor: "[REDACTED]",
  },
});
```

### 11.4 Content Sanitization

Documentation content is treated as untrusted text:

- No `eval()` or dynamic `import()` of documentation content
- HTML content is sanitized before markdown conversion (future HTML adapter)
- No execution of code examples
- Content stored in SQLite uses parameterized queries (no SQL injection)

---

## 12. Observability

### 12.1 Structured Logging

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
  "adapter": null,
  "duration": 3,
  "tokenCount": 1250,
  "status": "success"
}
```

### 12.2 Key Metrics

| Metric | Description | Exposed Via |
|--------|-------------|-------------|
| Cache hit rate | % of requests served from cache | health resource |
| Cache tier distribution | memory vs SQLite vs miss | health resource |
| Adapter success rate | % of successful fetches per adapter | health resource |
| Average latency | Per-tool response time | logs |
| Avg tokens per response | Token efficiency tracking | logs |
| Error rate | % of requests returning errors | health resource |
| Rate limit rejections | Count of rate-limited requests | logs |

### 12.3 Health Check

The `pro-context://health` resource returns:

```json
{
  "status": "healthy | degraded | unhealthy",
  "uptime": 3600,
  "cache": { "memoryEntries": 142, "memoryBytes": 52428800, "sqliteEntries": 1024, "hitRate": 0.87 },
  "adapters": {
    "llms-txt": { "status": "available", "lastSuccess": "...", "errorCount": 0 },
    "github": { "status": "available", "rateLimitRemaining": 4850 }
  },
  "version": "1.0.0"
}
```

Status determination:
- `healthy`: All adapters available, cache functional
- `degraded`: Some adapters unavailable, or cache hit rate < 50%
- `unhealthy`: All adapters unavailable, or cache corrupted

---

## 13. Extensibility Points

### 13.1 Adding a New Language

1. **Create registry resolver**: `src/registry/{language}-resolver.ts`
   - Implement version resolution for the language's package registry
   - Follow the same interface as `pypi-resolver.ts`

2. **Add known libraries**: Add entries to `src/registry/known-libraries.ts`
   - Each entry includes `languages: ["{language}"]` and language-specific metadata

3. **No changes required in**: adapters, cache, search, tools, config
   - Adapters work by URL — they don't care about the language
   - Cache is keyed by libraryId + version — language-agnostic
   - Search indexes content — language-agnostic

### 13.2 Adding a New Documentation Source

1. **Create adapter**: `src/adapters/{source-name}.ts`
   - Implement the `SourceAdapter` interface (canHandle, fetchToc, fetchPage, checkFreshness)
   - Define `priority` relative to existing adapters

2. **Register adapter**: Add to the adapter chain in `src/adapters/chain.ts`

3. **No changes required in**: tools, cache, search, config schema (unless source-specific config is needed)

### 13.3 Adding a New Tool

1. **Create tool handler**: `src/tools/{tool-name}.ts`
   - Define Zod input/output schemas
   - Implement handler function

2. **Register tool**: Add to server setup in `src/server.ts`

3. **No changes required in**: adapters, cache, search, other tools

---

## 14. Database Schema

### 14.1 SQLite Tables

```sql
-- Documentation cache (chunks from get-docs)
CREATE TABLE IF NOT EXISTS doc_cache (
  key TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,
  version TEXT NOT NULL,
  identifier TEXT NOT NULL,
  content TEXT NOT NULL,
  source_url TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  adapter TEXT NOT NULL,
  fetched_at TEXT NOT NULL,       -- ISO 8601
  expires_at TEXT NOT NULL,       -- ISO 8601
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_doc_cache_library ON doc_cache(library_id, version);
CREATE INDEX IF NOT EXISTS idx_doc_cache_expires ON doc_cache(expires_at);

-- Page cache (full pages from read-page)
CREATE TABLE IF NOT EXISTS page_cache (
  url_hash TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  total_tokens INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_page_cache_expires ON page_cache(expires_at);

-- TOC cache
CREATE TABLE IF NOT EXISTS toc_cache (
  key TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,
  version TEXT NOT NULL,
  toc_json TEXT NOT NULL,          -- JSON array of TocEntry
  available_sections TEXT NOT NULL, -- JSON array of section names
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_toc_cache_library ON toc_cache(library_id, version);

-- Search index (BM25 term index)
CREATE TABLE IF NOT EXISTS search_chunks (
  id TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,
  version TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  section_path TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  source_url TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_search_chunks_library ON search_chunks(library_id, version);

-- FTS5 virtual table for full-text search (wraps search_chunks)
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
  title,
  content,
  section_path,
  content='search_chunks',
  content_rowid='rowid',
  tokenize='porter unicode61'
);

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

-- Library metadata cache
CREATE TABLE IF NOT EXISTS library_metadata (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  languages TEXT NOT NULL,           -- JSON array
  package_name TEXT NOT NULL,
  docs_url TEXT,
  repo_url TEXT,
  versions TEXT NOT NULL,            -- JSON array
  default_version TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_library_metadata_package ON library_metadata(package_name);

-- Session state (resolved libraries in current session)
CREATE TABLE IF NOT EXISTS session_libraries (
  library_id TEXT NOT NULL PRIMARY KEY,
  name TEXT NOT NULL,
  languages TEXT NOT NULL,           -- JSON array (informational metadata)
  version TEXT NOT NULL,
  resolved_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 14.2 Database Initialization

```typescript
function initializeDatabase(db: Database): void {
  db.pragma("journal_mode = WAL");        // Write-Ahead Logging for concurrency
  db.pragma("busy_timeout = 5000");       // 5s timeout for lock contention
  db.pragma("synchronous = NORMAL");      // Balance durability vs performance
  db.pragma("foreign_keys = ON");

  // Run CREATE TABLE statements...
}
```

### 14.3 Cleanup Job

```typescript
function cleanupExpiredEntries(db: Database): void {
  const now = new Date().toISOString();
  db.prepare("DELETE FROM doc_cache WHERE expires_at < ?").run(now);
  db.prepare("DELETE FROM page_cache WHERE expires_at < ?").run(now);
  db.prepare("DELETE FROM toc_cache WHERE expires_at < ?").run(now);
  db.prepare("DELETE FROM library_metadata WHERE expires_at < ?").run(now);
  // FTS5 content sync handled by triggers
}
```

The cleanup job runs on the configured interval (`cache.cleanupIntervalMinutes`, default: 60 minutes).

---

## 15. Fuzzy Matching

Library name resolution uses Levenshtein distance for fuzzy matching:

```typescript
function findClosestMatches(query: string, candidates: Library[]): LibraryMatch[] {
  const normalized = query.toLowerCase().replace(/[^a-z0-9]/g, "");
  const results: LibraryMatch[] = [];

  for (const candidate of candidates) {
    const normalizedName = candidate.name.toLowerCase().replace(/[^a-z0-9]/g, "");
    const normalizedId = candidate.id.toLowerCase().replace(/[^a-z0-9]/g, "");

    const nameDist = levenshteinDistance(normalized, normalizedName);
    const idDist = levenshteinDistance(normalized, normalizedId);
    const bestDist = Math.min(nameDist, idDist);

    if (bestDist <= 3) { // Max edit distance: 3
      results.push({
        libraryId: candidate.id,
        name: candidate.name,
        description: candidate.description,
        languages: candidate.languages,
        relevance: 1 - (bestDist / Math.max(normalized.length, 1)),
      });
    }
  }

  return results.sort((a, b) => b.relevance - a.relevance);
}
```

This handles common typos like "langchan" → "langchain", "fasapi" → "fastapi", "pydanctic" → "pydantic". Returns all matches ranked by relevance, not just the best one.
