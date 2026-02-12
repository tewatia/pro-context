# Pro-Context: Technical Specification

> **Document**: 03-technical-spec.md
> **Status**: Final
> **Last Updated**: 2026-02-12

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
│  │  (5)    │  │  (4)     │  │  (3)       │             │
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
  │    ├─ 3. Fetch version list from PyPI
  │    ├─ 4. Determine available doc sources (llms.txt? GitHub?)
  │    └─ 5. Return { libraryId, versions, sources }
  │
  ├─ get-docs("langchain-ai/langchain", "chat models", "0.3.x")
  │    │
  │    ├─ 1. Resolve version: "0.3.x" → "0.3.14" via PyPI
  │    ├─ 2. Cache lookup: memory LRU → SQLite
  │    │    ├─ HIT (fresh) → return cached content
  │    │    ├─ HIT (stale) → return cached + trigger background refresh
  │    │    └─ MISS → continue to step 3
  │    ├─ 3. Adapter chain: llms.txt → GitHub → Custom
  │    │    ├─ llms.txt: fetch {docsUrl}/llms-full.txt
  │    │    ├─ If fails → GitHub: fetch /docs/ from repo
  │    │    └─ If fails → Custom: user-configured source
  │    ├─ 4. Chunk raw content into sections
  │    ├─ 5. Rank chunks by topic relevance (BM25)
  │    ├─ 6. Select top chunk(s) within maxTokens budget
  │    ├─ 7. Store in cache (memory + SQLite)
  │    └─ 8. Return { content, source, version, confidence }
  │
  └─ search-docs("langchain-ai/langchain", "retry logic")
       │
       ├─ 1. Check if library docs are indexed in search engine
       │    ├─ YES → proceed to step 2
       │    └─ NO → trigger JIT fetch + index, then proceed
       ├─ 2. Execute BM25 query against indexed chunks
       ├─ 3. Rank results by relevance score
       └─ 4. Return top N results with snippets
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

type Language = "python" | "javascript" | "typescript" | (string & {});

interface Library {
  /** Canonical identifier (e.g., "langchain-ai/langchain") */
  id: string;
  /** Human-readable name (e.g., "LangChain") */
  name: string;
  /** Brief description */
  description: string;
  /** Programming language */
  language: Language;
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
  /** Categories for filtering */
  categories: string[];
}

// ===== Documentation Types =====

interface DocResult {
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
  /** Name of the adapter that produced this result */
  adapter: string;
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
  /** Section/page title */
  title: string;
  /** Relevant text excerpt */
  snippet: string;
  /** BM25 relevance score (0-1 normalized) */
  relevance: number;
  /** Source URL */
  url: string;
  /** Documentation section path */
  section: string;
}

interface CodeExample {
  /** Example title or description */
  title: string;
  /** Code content */
  code: string;
  /** Programming language */
  language: string;
  /** URL where example was found */
  source: string;
  /** Brief explanation of what the example demonstrates */
  context: string;
}

// ===== Fetch Types =====

interface FetchOptions {
  /** Documentation topic to fetch */
  topic: string;
  /** Library version */
  version: string;
  /** Maximum tokens to return */
  maxTokens: number;
}

// ===== Error Types =====

type ErrorCode =
  | "LIBRARY_NOT_FOUND"
  | "VERSION_NOT_FOUND"
  | "TOPIC_NOT_FOUND"
  | "SOURCE_UNAVAILABLE"
  | "REGISTRY_TIMEOUT"
  | "RATE_LIMITED"
  | "INDEXING_IN_PROGRESS"
  | "AUTH_REQUIRED"
  | "AUTH_INVALID"
  | "MAX_TOKENS_EXCEEDED"
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
  /** Cache key: hash of (libraryId, version, topic) */
  key: string;
  /** Library identifier */
  libraryId: string;
  /** Library version */
  version: string;
  /** Topic hash */
  topicHash: string;
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

### 3.3 Auth Types (Cloud Mode)

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
  libraries: Record<string, LibraryOverride>;
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
// See functional spec section 10 for full env var override table

interface CustomSource {
  name: string;
  type: "url" | "file" | "github";
  url?: string;
  path?: string;
  libraryId: string;
  ttlHours?: number;
}

interface LibraryOverride {
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
   * Fetch documentation for the given library and topic.
   * Returns null if documentation cannot be found.
   */
  fetchDocs(library: Library, options: FetchOptions): Promise<RawDocContent | null>;

  /**
   * Check if the cached version is still fresh.
   * Uses SHA comparison, ETags, or Last-Modified headers.
   * Returns true if cache is still valid (no refetch needed).
   */
  checkFreshness(library: Library, cached: CacheEntry): Promise<boolean>;
}

interface RawDocContent {
  /** Raw documentation content (markdown) */
  content: string;
  /** Source URL */
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

  async fetchDocs(library: Library, options: FetchOptions): Promise<RawDocContent> {
    const errors: Error[] = [];

    for (const adapter of this.adapters) {
      if (!(await adapter.canHandle(library))) {
        continue;
      }

      try {
        const result = await adapter.fetchDocs(library, options);
        if (result !== null) {
          return result;
        }
      } catch (error) {
        errors.push(error);
        // Continue to next adapter
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

fetchDocs(library, options):
  1. Try fetching {library.docsUrl}/llms-full.txt
  2. If 404, try {library.docsUrl}/llms.txt
  3. If 404, return null
  4. Parse llms.txt format (markdown with structured sections)
  5. Return { content, sourceUrl, contentHash }

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

fetchDocs(library, options):
  1. Resolve version to git tag via GitHub API
  2. Try fetching /docs/ directory listing from repo
  3. If /docs/ exists, fetch README.md + relevant files
  4. If no /docs/, fetch root README.md
  5. Concatenate fetched content
  6. Return { content, sourceUrl, contentHash }

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

fetchDocs(library, options):
  1. Determine source type (url, file, github)
  2. For "url": fetch URL content
  3. For "file": read local file
  4. For "github": delegate to GitHub adapter with custom repo
  5. Return { content, sourceUrl, contentHash }

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
      24hr TTL (docs)        Configurable/library
```

### 5.2 Cache Manager

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

### 5.3 Cache Key Strategy

Cache keys are computed as:

```
key = SHA-256(libraryId + ":" + version + ":" + normalizedTopic)
```

Where `normalizedTopic` is the topic string lowercased and whitespace-normalized.

### 5.4 Cache Invalidation Signals

| Signal | Trigger | Action |
|--------|---------|--------|
| TTL expiry | Automatic | Entry marked stale; served with `stale: true` |
| SHA mismatch | `checkFreshness()` on read | Refetch from source, update cache |
| Version change | PyPI/npm shows new version | Old version cache untouched; new version fetched on demand |
| Manual invalidation | Admin CLI command | Delete entry from both tiers |
| Cleanup job | Scheduled (configurable interval) | Delete all expired entries from SQLite |

### 5.5 Background Refresh

When a stale cache entry is served, a background refresh is triggered:

```
1. Return stale content immediately (with stale: true)
2. Spawn background task:
   a. Fetch fresh content from adapter chain
   b. Compare content hash with cached
   c. If changed → update cache entry
   d. If unchanged → update expiresAt timestamp only
```

This ensures the user gets a fast response while the cache stays fresh.

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

### 6.3 Ranking and Token Budgeting

When returning results via `get-docs`, the system applies a token budget:

```
1. Rank all matching chunks by BM25 relevance
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
| Avg tokens per response | <3,000 | Deepcon: 2,365 |
| Accuracy | >85% | Deepcon: 90% |
| Tokens per correct answer | <3,529 | Deepcon: 2,628 |

### 7.2 Techniques

1. **Focused chunking**: Split docs into small, self-contained sections (target: 500 tokens/chunk)
2. **Relevance ranking**: BM25 ensures only relevant chunks are returned
3. **Token budgeting**: `maxTokens` parameter caps response size (default: 5,000)
4. **Code extraction**: `get-examples` returns only code blocks, not surrounding prose
5. **Snippet generation**: `search-docs` returns snippets (~100 tokens each), not full content
6. **Section targeting**: Use heading hierarchy to find the most specific relevant section

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

### 8.2 Streamable HTTP Transport (Cloud Mode)

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
  libraryId: z.string().min(1).max(200).regex(/^[a-zA-Z0-9\-_./]+$/),
  topic: z.string().min(1).max(500),
  version: z.string().max(50).optional(),
  maxTokens: z.number().int().min(500).max(10000).default(5000),
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
- No arbitrary user-provided URLs (only computed from library metadata)
- Custom sources in config are added to the allowlist

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
  "time": "2026-02-12T10:00:00.000Z",
  "correlationId": "abc-123-def",
  "tool": "get-docs",
  "libraryId": "langchain-ai/langchain",
  "version": "0.3.14",
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
  "status": "healthy" | "degraded" | "unhealthy",
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
   - Each entry includes `language: "{language}"` and language-specific metadata

3. **No changes required in**: adapters, cache, search, tools, config
   - Adapters work by URL — they don't care about the language
   - Cache is keyed by libraryId + version — language-agnostic
   - Search indexes content — language-agnostic

### 13.2 Adding a New Documentation Source

1. **Create adapter**: `src/adapters/{source-name}.ts`
   - Implement the `SourceAdapter` interface
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
-- Documentation cache
CREATE TABLE IF NOT EXISTS doc_cache (
  key TEXT PRIMARY KEY,
  library_id TEXT NOT NULL,
  version TEXT NOT NULL,
  topic_hash TEXT NOT NULL,
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
  language TEXT NOT NULL,
  package_name TEXT NOT NULL,
  docs_url TEXT,
  repo_url TEXT,
  versions TEXT NOT NULL,            -- JSON array
  default_version TEXT NOT NULL,
  categories TEXT NOT NULL DEFAULT '[]', -- JSON array
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_library_metadata_language ON library_metadata(language);
CREATE INDEX IF NOT EXISTS idx_library_metadata_package ON library_metadata(package_name);
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
  db.prepare("DELETE FROM library_metadata WHERE expires_at < ?").run(now);
  // FTS5 content sync handled by triggers
}
```

The cleanup job runs on the configured interval (`cache.cleanupIntervalMinutes`, default: 60 minutes).

---

## 15. Fuzzy Matching

Library name resolution uses Levenshtein distance for fuzzy matching:

```typescript
function findClosestMatch(query: string, candidates: string[]): string | null {
  const normalized = query.toLowerCase().replace(/[^a-z0-9]/g, "");
  let bestMatch: string | null = null;
  let bestDistance = Infinity;

  for (const candidate of candidates) {
    const normalizedCandidate = candidate.toLowerCase().replace(/[^a-z0-9]/g, "");
    const distance = levenshteinDistance(normalized, normalizedCandidate);

    if (distance < bestDistance && distance <= 3) { // Max edit distance: 3
      bestDistance = distance;
      bestMatch = candidate;
    }
  }

  return bestMatch;
}
```

This handles common typos like "langchan" → "langchain", "fasapi" → "fastapi", "pydanctic" → "pydantic".
