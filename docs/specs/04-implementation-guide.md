# Pro-Context: Implementation Guide

> **Document**: 04-implementation-guide.md
> **Status**: Final
> **Last Updated**: 2026-02-12

---

## 1. Project Structure

```
pro-context/
├── src/
│   ├── index.ts                    # Entry point, server bootstrap, transport selection
│   ├── server.ts                   # MCP server setup, tool/resource/prompt registration
│   ├── config/
│   │   ├── schema.ts               # Zod config schema + defaults
│   │   └── loader.ts               # Config file loading + env variable overrides
│   ├── tools/
│   │   ├── resolve-library.ts      # resolve-library tool handler
│   │   ├── get-docs.ts             # get-docs tool handler
│   │   ├── search-docs.ts          # search-docs tool handler
│   │   ├── get-examples.ts         # get-examples tool handler
│   │   └── list-libraries.ts       # list-libraries tool handler
│   ├── resources/
│   │   ├── library-resources.ts    # library://{id}/overview, changelog, api/{module} resources
│   │   └── health.ts               # pro-context://health resource
│   ├── prompts/
│   │   ├── migrate-code.ts         # migrate-code prompt template
│   │   ├── debug-with-docs.ts      # debug-with-docs prompt template
│   │   └── explain-api.ts          # explain-api prompt template
│   ├── adapters/
│   │   ├── types.ts                # SourceAdapter interface + RawDocContent type
│   │   ├── chain.ts                # AdapterChain: ordered execution with fallback
│   │   ├── llms-txt.ts             # llms.txt adapter implementation
│   │   ├── github.ts               # GitHub docs adapter implementation
│   │   └── custom.ts               # User-configured source adapter
│   ├── auth/
│   │   ├── api-keys.ts             # API key creation, validation, hashing
│   │   ├── middleware.ts            # HTTP auth middleware
│   │   └── admin-cli.ts            # CLI entry point for key management
│   ├── cache/
│   │   ├── memory.ts               # LRU in-memory cache wrapper
│   │   ├── sqlite.ts               # SQLite persistent cache operations
│   │   └── manager.ts              # Two-tier cache orchestrator
│   ├── search/
│   │   ├── chunker.ts              # Markdown → DocChunk[] chunking logic
│   │   ├── bm25.ts                 # BM25 scoring algorithm
│   │   └── engine.ts               # Search engine: index + query orchestration
│   ├── lib/
│   │   ├── logger.ts               # Pino logger setup with redaction
│   │   ├── errors.ts               # ProContextError class + factory functions
│   │   ├── rate-limiter.ts         # Token bucket rate limiter
│   │   ├── fuzzy-match.ts          # Levenshtein distance fuzzy matching
│   │   ├── tokens.ts               # Token count estimation utilities
│   │   └── url-validator.ts        # URL allowlist + SSRF prevention
│   └── registry/
│       ├── types.ts                # Library type + registry resolver interface
│       ├── known-libraries.ts      # Curated library registry (Python initially)
│       └── pypi-resolver.ts        # PyPI version/URL resolution
├── tests/
│   ├── unit/
│   │   ├── cache/
│   │   │   ├── memory.test.ts
│   │   │   ├── sqlite.test.ts
│   │   │   └── manager.test.ts
│   │   ├── search/
│   │   │   ├── chunker.test.ts
│   │   │   ├── bm25.test.ts
│   │   │   └── engine.test.ts
│   │   ├── adapters/
│   │   │   ├── llms-txt.test.ts
│   │   │   ├── github.test.ts
│   │   │   └── chain.test.ts
│   │   ├── lib/
│   │   │   ├── fuzzy-match.test.ts
│   │   │   ├── rate-limiter.test.ts
│   │   │   └── url-validator.test.ts
│   │   └── registry/
│   │       └── pypi-resolver.test.ts
│   ├── integration/
│   │   ├── adapter-cache.test.ts    # Adapter + cache integration
│   │   ├── search-pipeline.test.ts  # Fetch → chunk → index → search
│   │   └── auth-flow.test.ts        # API key auth end-to-end
│   └── e2e/
│       ├── stdio-server.test.ts     # Full MCP client ↔ server via stdio
│       └── http-server.test.ts      # Full MCP client ↔ server via HTTP
├── docs/
│   └── specs/
│       ├── 01-competitive-analysis.md
│       ├── 02-functional-spec.md
│       ├── 03-technical-spec.md
│       └── 04-implementation-guide.md
├── Dockerfile
├── docker-compose.yml
├── pro-context.config.yaml          # Default configuration
├── package.json
├── tsconfig.json
├── biome.json
├── vitest.config.ts
└── README.md
```

---

## 2. Dependency List

### Production Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `@modelcontextprotocol/sdk` | `^1.x` | MCP server SDK — tool/resource/prompt registration, stdio + HTTP transport |
| `better-sqlite3` | `^11.x` | SQLite database — persistent cache, search index, API keys |
| `zod` | `^3.x` | Schema validation — config validation, tool input/output validation |
| `lru-cache` | `^10.x` | In-memory LRU cache — hot path for repeated queries |
| `pino` | `^9.x` | Structured logging — JSON format, redaction, correlation IDs |
| `yaml` | `^2.x` | YAML parsing — configuration file loading |

### Development Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `typescript` | `^5.x` | TypeScript compiler |
| `tsup` | `^8.x` | Build tool — fast bundling, ESM + CJS output |
| `vitest` | `^2.x` | Test runner — fast, TS-native, ESM support |
| `@biomejs/biome` | `^1.x` | Linter + formatter — all-in-one, fast |
| `@types/better-sqlite3` | `^7.x` | TypeScript types for better-sqlite3 |
| `@types/node` | `^20.x` | TypeScript types for Node.js |

### Notably Absent

| Package | Reason for Exclusion |
|---------|---------------------|
| Express/Fastify | MCP SDK handles HTTP transport internally |
| OpenAI/Ollama SDK | No vector search in initial version; BM25 is dependency-free |
| Redis | SQLite provides sufficient persistence; no external infra needed |
| cheerio/jsdom | No HTML scraping in initial version |
| undici | Node 20+ has native `fetch` |

---

## 3. Coding Conventions

### 3.1 Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Files | kebab-case | `fuzzy-match.ts`, `get-docs.ts` |
| Types/Interfaces | PascalCase | `Library`, `DocResult`, `SourceAdapter` |
| Functions | camelCase | `resolveLibrary`, `fetchDocs`, `checkFreshness` |
| Constants | UPPER_SNAKE_CASE | `DEFAULT_TTL_HOURS`, `MAX_TOKENS` |
| Config keys | camelCase (YAML) | `maxMemoryMB`, `defaultTTLHours` |
| Env vars | UPPER_SNAKE_CASE | `PRO_CONTEXT_PORT`, `PRO_CONTEXT_DEBUG` |
| Error codes | UPPER_SNAKE_CASE | `LIBRARY_NOT_FOUND`, `RATE_LIMITED` |

### 3.2 Error Handling Pattern

```typescript
// Use ProContextError for all user-facing errors
import { ProContextError, libraryNotFound } from "../lib/errors.js";

// Factory functions create typed errors
export function libraryNotFound(query: string, suggestion?: string): ProContextError {
  return new ProContextError({
    code: "LIBRARY_NOT_FOUND",
    message: `Library '${query}' not found.`,
    recoverable: true,
    suggestion: suggestion
      ? `Did you mean '${suggestion}'?`
      : "Check the library name and try again.",
  });
}

// In tool handlers, catch and convert errors
try {
  const result = await getDocsForLibrary(input);
  return result;
} catch (error) {
  if (error instanceof ProContextError) {
    return { error }; // Return structured error
  }
  logger.error({ error }, "Unexpected error in get-docs");
  return { error: internalError() };
}
```

### 3.3 Test Pattern

```typescript
// tests/unit/search/bm25.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { BM25Index } from "../../src/search/bm25.js";

describe("BM25Index", () => {
  let index: BM25Index;

  beforeEach(() => {
    index = new BM25Index();
  });

  it("should rank exact matches highest", () => {
    index.addDocument("1", "langchain chat models streaming");
    index.addDocument("2", "fastapi dependency injection middleware");

    const results = index.search("langchain chat models");

    expect(results[0].id).toBe("1");
    expect(results[0].score).toBeGreaterThan(results[1]?.score ?? 0);
  });
});
```

### 3.4 Module Pattern

- Each file exports a single primary class/function + supporting types
- Avoid default exports — use named exports exclusively
- Import with `.js` extension for ESM compatibility
- Keep files focused: one concern per file

### 3.5 Async Pattern

- Use `async/await` for all asynchronous operations
- `better-sqlite3` is synchronous — no async wrapper needed for DB operations
- Network fetches use native `fetch` with `AbortController` for timeouts

---

## 4. Implementation Phases

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
   - `src/lib/url-validator.ts` — URL allowlist checking, SSRF prevention (block private IPs)

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

**Goal**: Source adapter interface, library registry (PyPI), llms.txt adapter, GitHub adapter, two-tier cache, `resolve-library` tool, `get-docs` tool.

**Verification gate**: `resolve-library("langchain")` returns correct metadata; `get-docs` for LangChain returns current documentation from llms.txt.

#### Files to Create (in order)

1. **Registry**
   - `src/registry/types.ts` — `Library` type, `RegistryResolver` interface
   - `src/registry/known-libraries.ts` — Curated registry of Python libraries with metadata (langchain, fastapi, pydantic, httpx, sqlalchemy, django, flask, pytest, numpy, pandas, etc.)
   - `src/registry/pypi-resolver.ts` — Fetch versions + metadata from PyPI JSON API
   - `src/lib/fuzzy-match.ts` — Levenshtein distance implementation + `findClosestMatch()`

2. **Source Adapters**
   - `src/adapters/types.ts` — `SourceAdapter` interface, `RawDocContent` type
   - `src/adapters/chain.ts` — `AdapterChain` class: ordered adapter execution with fallback
   - `src/adapters/llms-txt.ts` — Fetch `llms-full.txt` / `llms.txt` from library docs site
   - `src/adapters/github.ts` — Fetch docs from GitHub repo (/docs/, README.md)
   - `src/adapters/custom.ts` — User-configured sources (URL, file, GitHub)

3. **Cache**
   - `src/cache/sqlite.ts` — SQLite cache: init DB, get/set/delete operations, cleanup
   - `src/cache/memory.ts` — LRU cache wrapper with TTL
   - `src/cache/manager.ts` — Two-tier cache orchestrator: memory → SQLite → miss

4. **Tools**
   - `src/tools/resolve-library.ts` — Resolve library name to canonical ID + metadata
   - `src/tools/get-docs.ts` — Fetch documentation via cache → adapter chain → chunk → return

5. **Registration**
   - Update `src/server.ts` — Register `resolve-library` and `get-docs` tools

6. **Tests**
   - `tests/unit/registry/pypi-resolver.test.ts` — Mock PyPI API responses
   - `tests/unit/lib/fuzzy-match.test.ts` — Levenshtein distance + matching
   - `tests/unit/adapters/llms-txt.test.ts` — Mock fetch responses
   - `tests/unit/adapters/github.test.ts` — Mock GitHub API responses
   - `tests/unit/adapters/chain.test.ts` — Fallback behavior
   - `tests/unit/cache/memory.test.ts` — LRU operations + TTL
   - `tests/unit/cache/sqlite.test.ts` — SQLite CRUD + cleanup
   - `tests/unit/cache/manager.test.ts` — Two-tier promotion + stale handling
   - `tests/integration/adapter-cache.test.ts` — Full fetch → cache → serve flow

#### Phase 2 Verification Checklist

- [ ] `resolve-library("langchain")` returns `{ libraryId: "langchain-ai/langchain", ... }`
- [ ] `resolve-library("langchan")` returns fuzzy suggestion: "Did you mean 'langchain'?"
- [ ] `resolve-library("fastapi")` returns correct FastAPI metadata
- [ ] `get-docs("langchain-ai/langchain", "chat models")` returns markdown content
- [ ] Content comes from llms.txt when available
- [ ] If llms.txt unavailable, falls back to GitHub
- [ ] Second request for same content is served from cache (check logs for cache hit)
- [ ] Cache SQLite file is created at configured path
- [ ] Version resolution works: `version: "0.3.x"` resolves to exact version

---

### Phase 3: Search & Discovery

**Goal**: Document chunking, BM25 search indexing, `search-docs` tool, `get-examples` tool, `list-libraries` tool, library resources.

**Verification gate**: Search returns relevant results; examples contain code blocks; library resources are accessible.

#### Files to Create (in order)

1. **Search Engine**
   - `src/search/chunker.ts` — Markdown → `DocChunk[]`: heading-aware splitting, token budgets, section path extraction
   - `src/search/bm25.ts` — BM25 algorithm: tokenization, inverted index, IDF computation, query scoring
   - `src/search/engine.ts` — Search engine orchestrator: index management, query execution, result formatting

2. **Tools**
   - `src/tools/search-docs.ts` — Search indexed docs, trigger JIT indexing if needed
   - `src/tools/get-examples.ts` — Extract code blocks from docs, filter by topic
   - `src/tools/list-libraries.ts` — List available libraries from registry + cache

3. **Resources**
   - `src/resources/library-resources.ts` — `library://{id}/overview`, `library://{id}/changelog`, `library://{id}/api/{module}` resources

4. **Update get-docs**
   - Update `src/tools/get-docs.ts` — Integrate chunker: fetch raw docs → chunk → rank by topic → return best chunks within token budget

5. **Registration**
   - Update `src/server.ts` — Register `search-docs`, `get-examples`, `list-libraries` tools + resources

6. **Tests**
   - `tests/unit/search/chunker.test.ts` — Heading detection, chunk sizing, section paths
   - `tests/unit/search/bm25.test.ts` — Ranking correctness, edge cases
   - `tests/unit/search/engine.test.ts` — Index + query orchestration
   - `tests/integration/search-pipeline.test.ts` — Fetch → chunk → index → search → results

#### Phase 3 Verification Checklist

- [ ] `search-docs("langchain-ai/langchain", "streaming")` returns ranked results
- [ ] Results include title, snippet, relevance score, URL
- [ ] BM25 ranks exact keyword matches higher than tangential mentions
- [ ] `get-examples("langchain-ai/langchain", "ChatOpenAI")` returns code blocks
- [ ] Examples include `language: "python"` identifier
- [ ] `list-libraries()` returns known libraries
- [ ] `list-libraries({ language: "python" })` filters correctly
- [ ] `get-docs` now returns focused chunks (not raw full docs)
- [ ] Average token count per `get-docs` response is <3,000
- [ ] `library://langchain-ai/langchain/overview` resource returns content

---

### Phase 4: Cloud Mode & Authentication

**Goal**: Streamable HTTP transport, API key authentication, per-key rate limiting, admin CLI, CORS.

**Verification gate**: HTTP mode works with API key; rate limiting kicks in at configured threshold; unauthorized requests are rejected with proper error.

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

**Verification gate**: Full e2e test passes — Claude Code connects, resolves library, gets docs, searches. Docker image builds and runs.

#### Files to Create (in order)

1. **Prompts**
   - `src/prompts/migrate-code.ts` — Migration prompt template
   - `src/prompts/debug-with-docs.ts` — Debug prompt template
   - `src/prompts/explain-api.ts` — API explanation prompt template

2. **Registration**
   - Update `src/server.ts` — Register prompt templates

3. **Docker**
   - `Dockerfile` — Multi-stage build: install deps → compile TS → slim runtime image
   - `docker-compose.yml` — Easy local cloud-mode testing with volume mount for cache

4. **E2E Tests**
   - `tests/e2e/stdio-server.test.ts` — Full MCP client ↔ server via stdio: resolve → get-docs → search
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
- [ ] E2E stdio test: client connects → resolve-library → get-docs → search-docs → all succeed
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
| Fuzzy match | Edit distance, no match, exact match | — | Nothing (pure logic) |
| Rate limiter | Token bucket math, burst, refill | — | Time (use fake timers) |
| URL validator | Allowlist, SSRF blocks | — | Nothing (pure logic) |
| Memory cache | Get/set/delete, TTL, LRU eviction | — | Nothing |
| SQLite cache | CRUD, cleanup, expiry | — | Nothing (use in-memory SQLite) |
| Cache manager | Tier promotion, stale handling | Adapter + cache flow | Network fetches |
| llms.txt adapter | Parse llms.txt format, handle 404 | Full fetch → cache | HTTP responses |
| GitHub adapter | Parse repo structure, handle rate limit | Full fetch → cache | HTTP responses |
| Adapter chain | Fallback on failure, priority order | Full chain with cache | HTTP responses |
| PyPI resolver | Version parsing, latest detection | — | HTTP responses |
| API key auth | Hash validation, key format | Create → auth → revoke | Nothing (use test SQLite) |
| Search engine | Index + query orchestration | Fetch → chunk → index → search | HTTP responses |
| Tool handlers | Input validation, output format | — | Core engine (mock adapters) |

### 5.3 What NOT to Test

- MCP SDK internals (trust the SDK)
- SQLite engine behavior (trust better-sqlite3)
- Pino logging output format (trust pino)
- External API response formats beyond what we parse
- Exact token count accuracy (approximation is fine)

### 5.4 Test Configuration

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/index.ts", "src/auth/admin-cli.ts"],
      thresholds: {
        statements: 80,
        branches: 75,
        functions: 80,
        lines: 80,
      },
    },
    testTimeout: 10000,
    hookTimeout: 10000,
  },
});
```

---

## 6. CI/CD and Docker Deployment

### 6.1 Dockerfile

```dockerfile
# Stage 1: Build
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json biome.json ./
COPY src/ src/
RUN npm run build

# Stage 2: Production
FROM node:20-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY --from=builder /app/dist/ dist/
COPY pro-context.config.yaml ./

# Create cache directory
RUN mkdir -p /data/cache

ENV PRO_CONTEXT_TRANSPORT=http
ENV PRO_CONTEXT_PORT=3100
ENV PRO_CONTEXT_CACHE_DIR=/data/cache

EXPOSE 3100
CMD ["node", "dist/index.js"]
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
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run lint
      - run: npm run build
      - run: npm test -- --coverage
```

### 6.4 Package.json Scripts

```json
{
  "scripts": {
    "build": "tsup src/index.ts src/auth/admin-cli.ts --format esm --dts",
    "dev": "tsx watch src/index.ts",
    "start": "node dist/index.js",
    "lint": "biome check .",
    "lint:fix": "biome check --write .",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "admin": "tsx src/auth/admin-cli.ts"
  },
  "bin": {
    "pro-context": "./dist/index.js",
    "pro-context-admin": "./dist/admin-cli.js"
  }
}
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

### Phase 9: Project-Scoped Context ("Cabinets")

**Concept:** Teams can define a set of libraries relevant to their project. Queries are scoped to the project's library set for better relevance.

**New files:**
- `src/projects/types.ts` — Project/cabinet data model
- `src/projects/manager.ts` — CRUD for project-scoped library sets
- `src/tools/manage-project.ts` — Tool for agents to manage project context

### Phase 10: Prometheus Metrics

**New files:**
- `src/lib/metrics.ts` — Prometheus metric definitions
- Metrics endpoint at `/metrics` in HTTP mode

**New dependency:** `prom-client`

---

## 8. Quick Reference: MCP Client Configuration

### Claude Code (stdio)

```bash
claude mcp add pro-context -- node /path/to/pro-context/dist/index.js
```

### Claude Code (HTTP)

```json
{
  "mcpServers": {
    "pro-context": {
      "url": "http://localhost:3100/mcp",
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
      "command": "node",
      "args": ["/path/to/pro-context/dist/index.js"]
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
npm install

# Build
npm run build

# Run tests
npm test

# Start in development mode (auto-reload)
npm run dev

# Test with Claude Code
claude mcp add pro-context -- node /path/to/pro-context/dist/index.js
```

### Adding a New Library to the Registry

1. Edit `src/registry/known-libraries.ts`
2. Add entry with `id`, `name`, `description`, `language`, `packageName`, `docsUrl`, `repoUrl`, `categories`
3. Run tests: `npm test`
4. Build: `npm run build`

### Adding a New Source Adapter

1. Create `src/adapters/{name}.ts` implementing `SourceAdapter`
2. Register in `src/adapters/chain.ts` with appropriate priority
3. Add tests in `tests/unit/adapters/{name}.test.ts`
4. Add integration test if the adapter has external dependencies
5. Run full test suite: `npm test`
