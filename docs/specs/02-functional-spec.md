# Pro-Context: Functional Specification

> **Document**: 02-functional-spec.md
> **Status**: Final
> **Last Updated**: 2026-02-12

---

## 1. Problem Statement

AI coding agents (Claude Code, Cursor, Windsurf, etc.) frequently hallucinate API details when working with third-party libraries. They generate code using deprecated methods, incorrect parameter names, and outdated patterns because their training data has a knowledge cutoff.

Existing MCP documentation servers either:
- Return too much irrelevant content (5,000+ tokens, 65% accuracy)
- Require vendor lock-in to a centralized service
- Lack version awareness, returning docs for the wrong library version
- Cannot be self-hosted for offline or private use

**Pro-Context** solves this by providing an open-source, self-hostable MCP server that delivers focused, version-accurate library documentation to AI agents with high token efficiency.

---

## 2. Target Users

### 2.1 Individual Developer

- Uses Claude Code, Cursor, or similar AI coding agent
- Works with Python libraries (LangChain, FastAPI, Pydantic, etc.)
- Wants accurate, up-to-date documentation injected into agent context
- Runs Pro-Context locally via stdio transport
- Zero configuration required

### 2.2 Development Team

- 3-20 developers sharing an AI-assisted development environment
- Deploys Pro-Context as a shared service via HTTP transport
- Wants shared documentation cache (one fetch benefits all)
- Needs API key authentication and usage tracking
- May have internal/private library documentation

### 2.3 Enterprise (Future)

- Large organization with custom documentation sources
- Requires audit logging and access controls
- Deploys via Docker in private infrastructure
- Needs custom source adapters for internal docs

---

## 3. User Stories

### US-1: Resolve a Library

> As a developer using Claude Code, when I ask "look up LangChain docs", the agent should be able to identify the correct library, version, and available documentation sources.

**Acceptance criteria:**
- Agent calls `resolve-library` with a natural language query
- Server returns canonical library ID, available versions, and default version
- Fuzzy matching handles typos (e.g., "langchan" → "langchain")
- Language filter narrows results (e.g., `language: "python"`)

### US-2: Get Documentation for a Topic

> As a developer, when I ask "how do I use streaming with LangChain chat models", the agent should get focused, relevant documentation — not an entire page dump.

**Acceptance criteria:**
- Agent calls `get-docs` with library ID, topic, and optional version
- Server returns focused markdown content (<3,000 tokens typical)
- Response includes source URL, version, last-updated timestamp, and confidence score
- If cached and fresh, response is <500ms
- If JIT fetch required, response is <3s

### US-3: Search Across Documentation

> As a developer, when I ask "find all places LangChain mentions retry logic", the agent should search across the library's documentation and return ranked results.

**Acceptance criteria:**
- Agent calls `search-docs` with library ID and search query
- Server returns ranked results with title, snippet, relevance score, and URL
- Results are ordered by relevance (BM25 ranking)
- Maximum result count is configurable (default: 5)

### US-4: Get Code Examples

> As a developer, when I ask "show me examples of FastAPI dependency injection", the agent should return runnable code examples.

**Acceptance criteria:**
- Agent calls `get-examples` with library ID and topic
- Server returns code blocks extracted from documentation
- Each example includes title, code, language identifier, and source URL
- Examples are runnable (not fragments or pseudocode where possible)

### US-5: List Available Libraries

> As a developer, I want to know which libraries Pro-Context can provide docs for.

**Acceptance criteria:**
- Agent calls `list-libraries` with optional language and category filters
- Server returns list of available libraries with IDs, names, descriptions, and versions
- Includes both curated (known-libraries registry) and previously-cached libraries

### US-6: Team Deployment with API Keys

> As a team lead, I want to deploy Pro-Context as a shared service so all team members benefit from cached documentation.

**Acceptance criteria:**
- Server starts in HTTP mode with `transport: http`
- API keys are required for all requests
- Admin CLI (`pro-context-admin`) can create, list, and revoke keys
- Each key has configurable rate limits
- Shared cache means one developer's fetch benefits all others

### US-7: Version-Specific Documentation

> As a developer, I need documentation for a specific library version, not just "latest".

**Acceptance criteria:**
- All tools accept an optional `version` parameter
- Version resolves to exact release via PyPI (Python) or npm (JS/TS)
- If version is omitted, server uses latest stable version
- Cached documentation is version-specific (v0.2 and v0.3 stored separately)

### US-8: Graceful Degradation

> As a developer, I expect useful responses even when documentation sources are temporarily unavailable.

**Acceptance criteria:**
- If primary source (llms.txt) fails, server falls back to GitHub adapter
- If all sources fail but cache exists, stale cache is served with a warning
- If library is unknown, server returns fuzzy suggestions
- Error responses include actionable recovery suggestions

---

## 4. MCP Tool Definitions

### 4.1 `resolve-library`

Resolves a natural language library query to a canonical library identifier.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Library name or natural language query (e.g., 'langchain', 'python fastapi', 'pydantic v2')"
    },
    "language": {
      "type": "string",
      "enum": ["python", "javascript", "typescript"],
      "description": "Programming language filter. Optional — omit to search all languages. Note: Python is fully supported; JS/TS values are accepted for forward-compatibility but have limited registry support until Phase 6."
    }
  },
  "required": ["query"]
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "Canonical library identifier (e.g., 'langchain-ai/langchain')"
    },
    "name": {
      "type": "string",
      "description": "Human-readable library name"
    },
    "description": {
      "type": "string",
      "description": "Brief library description"
    },
    "language": {
      "type": "string",
      "description": "Programming language"
    },
    "versions": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Available versions (most recent first)"
    },
    "defaultVersion": {
      "type": "string",
      "description": "Recommended version (latest stable)"
    },
    "sources": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Available documentation sources (e.g., ['llms.txt', 'github'])"
    }
  }
}
```

**Behavior:**
1. Fuzzy-match `query` against known library registry
2. If no match, attempt resolution via PyPI (Python) or npm (JS/TS) registry
3. If still no match, return error with fuzzy suggestions
4. Fetch available versions from package registry
5. Determine available documentation sources (llms.txt, GitHub)
6. Return canonical ID with metadata

**Error cases:**
- Unknown library → `{ code: "LIBRARY_NOT_FOUND", message: "Library 'langchan' not found.", suggestion: "Did you mean 'langchain'?", recoverable: true }`
- Registry timeout → `{ code: "REGISTRY_TIMEOUT", message: "Could not reach PyPI registry.", suggestion: "Try again or specify the library ID directly.", recoverable: true, retryAfter: 5 }`

---

### 4.2 `get-docs`

Retrieves focused documentation for a specific topic within a library.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "Canonical library ID from resolve-library (e.g., 'langchain-ai/langchain')"
    },
    "topic": {
      "type": "string",
      "description": "Documentation topic (e.g., 'chat models', 'streaming', 'dependency injection')"
    },
    "version": {
      "type": "string",
      "description": "Library version. Defaults to latest stable if omitted."
    },
    "maxTokens": {
      "type": "number",
      "description": "Maximum tokens to return. Default: 5000. Range: 500-10000.",
      "default": 5000,
      "minimum": 500,
      "maximum": 10000
    }
  },
  "required": ["libraryId", "topic"]
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "content": {
      "type": "string",
      "description": "Documentation content in markdown format"
    },
    "source": {
      "type": "string",
      "description": "URL where documentation was fetched from"
    },
    "version": {
      "type": "string",
      "description": "Exact version of documentation returned"
    },
    "lastUpdated": {
      "type": "string",
      "format": "date-time",
      "description": "When this documentation was last fetched/verified"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "Relevance confidence score (1.0 = exact match, 0.0 = no match)"
    },
    "cached": {
      "type": "boolean",
      "description": "Whether this result was served from cache"
    },
    "stale": {
      "type": "boolean",
      "description": "Whether the cached content may be outdated"
    }
  }
}
```

**Behavior:**
1. Look up library metadata (version resolution, source URLs)
2. Check cache (memory → SQLite) for matching (libraryId, version, topic)
3. If cached and fresh → return immediately
4. If cached but stale → return stale with `stale: true`, trigger background refresh
5. If not cached → fetch via adapter chain (llms.txt → GitHub → Custom)
6. Chunk fetched content, rank by topic relevance
7. Return top chunk(s) within `maxTokens` budget
8. Store in cache for future requests

**Error cases:**
- Library not found → `{ code: "LIBRARY_NOT_FOUND", ... }`
- Topic not found → `{ code: "TOPIC_NOT_FOUND", message: "No documentation found for 'nonexistent-topic' in langchain.", suggestion: "Try searching with search-docs for broader results.", recoverable: true }`
- All sources unavailable → serve stale cache or `{ code: "SOURCE_UNAVAILABLE", message: "All documentation sources are currently unavailable.", suggestion: "Try again later. Cached content may be available.", recoverable: true, retryAfter: 30 }`

---

### 4.3 `search-docs`

Searches across a library's indexed documentation.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "Canonical library ID"
    },
    "query": {
      "type": "string",
      "description": "Search query (e.g., 'how to use streaming with chat models')"
    },
    "version": {
      "type": "string",
      "description": "Library version. Defaults to latest stable."
    },
    "maxResults": {
      "type": "number",
      "description": "Maximum number of results. Default: 5. Range: 1-20.",
      "default": 5,
      "minimum": 1,
      "maximum": 20
    }
  },
  "required": ["libraryId", "query"]
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": { "type": "string", "description": "Section/page title" },
          "snippet": { "type": "string", "description": "Relevant text excerpt" },
          "relevance": { "type": "number", "minimum": 0, "maximum": 1, "description": "BM25 relevance score" },
          "url": { "type": "string", "description": "Source URL" },
          "section": { "type": "string", "description": "Documentation section path" }
        }
      }
    },
    "totalMatches": {
      "type": "number",
      "description": "Total number of matches found (may exceed maxResults)"
    },
    "query": {
      "type": "string",
      "description": "The search query as processed"
    }
  }
}
```

**Behavior:**
1. Verify library is known and has indexed documentation
2. If documentation not yet indexed, trigger JIT fetch and index
3. Execute BM25 search across indexed chunks
4. Rank results by relevance score
5. Return top N results with snippets

**Error cases:**
- Library not indexed → trigger fetch, return `{ code: "INDEXING_IN_PROGRESS", message: "Documentation is being fetched and indexed. Try again shortly.", recoverable: true, retryAfter: 10 }`
- No results → `{ results: [], totalMatches: 0, query: "..." }`

---

### 4.4 `get-examples`

Retrieves code examples for a specific API or pattern.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "Canonical library ID"
    },
    "topic": {
      "type": "string",
      "description": "API or pattern to find examples for (e.g., 'ChatOpenAI streaming', 'FastAPI middleware')"
    },
    "version": {
      "type": "string",
      "description": "Library version. Defaults to latest stable."
    },
    "maxExamples": {
      "type": "number",
      "description": "Maximum number of examples. Default: 3. Range: 1-10.",
      "default": 3,
      "minimum": 1,
      "maximum": 10
    }
  },
  "required": ["libraryId", "topic"]
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "examples": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": { "type": "string", "description": "Example title or description" },
          "code": { "type": "string", "description": "Code example" },
          "language": { "type": "string", "description": "Programming language (e.g., 'python', 'javascript')" },
          "source": { "type": "string", "description": "URL where example was found" },
          "context": { "type": "string", "description": "Brief explanation of what the example demonstrates" }
        }
      }
    },
    "topic": {
      "type": "string",
      "description": "The resolved topic"
    }
  }
}
```

**Behavior:**
1. Fetch documentation for the given topic (reuses `get-docs` pipeline)
2. Extract code blocks (fenced code blocks in markdown)
3. Filter for relevant examples (match against topic keywords)
4. Add context from surrounding prose
5. Return up to `maxExamples` examples

**Error cases:**
- No examples found → `{ examples: [], topic: "..." }`
- Library not found → standard `LIBRARY_NOT_FOUND` error

---

### 4.5 `list-libraries`

Lists available libraries with optional filtering.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "language": {
      "type": "string",
      "enum": ["python", "javascript", "typescript"],
      "description": "Filter by programming language. Note: Python is fully supported; JS/TS are accepted for forward-compatibility but have limited registry support until Phase 6."
    },
    "category": {
      "type": "string",
      "description": "Filter by category (e.g., 'ai', 'web', 'data', 'testing')"
    }
  },
  "required": []
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "libraries": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "name": { "type": "string" },
          "description": { "type": "string" },
          "language": { "type": "string" },
          "versions": { "type": "array", "items": { "type": "string" } },
          "categories": { "type": "array", "items": { "type": "string" } }
        }
      }
    },
    "total": {
      "type": "number",
      "description": "Total number of libraries matching the filter"
    }
  }
}
```

**Behavior:**
1. Query known-libraries registry with filters
2. Include any previously-cached libraries not in the curated registry
3. Return sorted list (alphabetical by name)

---

## 5. MCP Resource Definitions

Resources provide read-only data that agents can access without tool calls.

### 5.1 `library://{libraryId}/overview`

**URI Template**: `library://{libraryId}/overview`
**MIME Type**: `text/markdown`
**Description**: Library overview including description, installation instructions, quick-start guide, and links.

**Content structure:**
```markdown
# {Library Name}

{Description}

## Installation
{Installation instructions}

## Quick Start
{Minimal usage example}

## Links
- Documentation: {docs URL}
- Repository: {repo URL}
- Package: {PyPI/npm URL}
```

### 5.2 `library://{libraryId}/changelog`

**URI Template**: `library://{libraryId}/changelog`
**MIME Type**: `text/markdown`
**Description**: Recent changes, release notes, and migration guides for the library.

### 5.3 `library://{libraryId}/api/{module}`

**URI Template**: `library://{libraryId}/api/{module}`
**MIME Type**: `text/markdown`
**Description**: API reference for a specific module within the library.

### 5.4 `pro-context://health`

**URI**: `pro-context://health`
**MIME Type**: `application/json`
**Description**: Server health status including cache statistics, adapter availability, and uptime.

**Content structure:**
```json
{
  "status": "healthy",
  "uptime": 3600,
  "cache": {
    "memoryEntries": 142,
    "memoryBytes": 52428800,
    "sqliteEntries": 1024,
    "hitRate": 0.87
  },
  "adapters": {
    "llms-txt": { "status": "available", "lastSuccess": "2026-02-12T10:00:00Z" },
    "github": { "status": "available", "lastSuccess": "2026-02-12T09:55:00Z", "rateLimitRemaining": 4850 }
  },
  "version": "1.0.0"
}
```

---

## 6. MCP Prompt Templates

Prompt templates provide reusable patterns that agents can invoke with parameters.

### 6.1 `migrate-code`

**Name**: `migrate-code`
**Description**: Generate a migration plan for upgrading library code between versions.

**Arguments:**
| Name | Required | Description |
|------|----------|-------------|
| `libraryId` | Yes | Library to migrate |
| `fromVersion` | Yes | Current version |
| `toVersion` | Yes | Target version |
| `codeSnippet` | No | Code to migrate (if provided, generates specific migration) |

**Template:**
```
You are helping migrate code from {libraryId} version {fromVersion} to {toVersion}.

First, use the get-docs tool to fetch the changelog and migration guide for {libraryId} version {toVersion}.

Then analyze the breaking changes between {fromVersion} and {toVersion}.

{#if codeSnippet}
Migrate the following code:
```
{codeSnippet}
```
{/if}

Provide:
1. A list of breaking changes that affect this code
2. The migrated code with explanations for each change
3. Any new features in {toVersion} that could improve this code
```

### 6.2 `debug-with-docs`

**Name**: `debug-with-docs`
**Description**: Debug an issue using current library documentation.

**Arguments:**
| Name | Required | Description |
|------|----------|-------------|
| `libraryId` | Yes | Library where the issue occurs |
| `errorMessage` | Yes | Error message or description of the issue |
| `codeSnippet` | No | Code that produces the error |

**Template:**
```
You are debugging an issue with {libraryId}.

Error: {errorMessage}

{#if codeSnippet}
Code:
```
{codeSnippet}
```
{/if}

Steps:
1. Use search-docs to find documentation related to this error
2. Use get-docs to fetch relevant API documentation
3. Use get-examples to find correct usage patterns

Based on the documentation, identify:
1. The root cause of the error
2. The correct API usage
3. A fixed version of the code
```

### 6.3 `explain-api`

**Name**: `explain-api`
**Description**: Explain a library API with current documentation and examples.

**Arguments:**
| Name | Required | Description |
|------|----------|-------------|
| `libraryId` | Yes | Library containing the API |
| `apiName` | Yes | API to explain (class, function, module) |
| `version` | No | Specific version |

**Template:**
```
Explain the {apiName} API from {libraryId}{#if version} (version {version}){/if}.

Steps:
1. Use get-docs to fetch the API documentation for {apiName}
2. Use get-examples to find usage examples
3. If relevant, use search-docs to find related APIs

Provide:
1. What {apiName} does and when to use it
2. Complete parameter/argument documentation
3. Return value documentation
4. At least 2 practical examples
5. Common pitfalls or gotchas
```

---

## 7. Documentation Source Priority and Fallback

When fetching documentation, adapters are tried in priority order:

```
Request → [1] llms.txt → [2] GitHub → [3] Custom → [Error with suggestions]
              │              │             │
              ▼              ▼             ▼
         Best quality   Authoritative   User-defined
         (LLM-optimized) (raw but fresh) (flexible)
```

### Priority 1: llms.txt Adapter

- Checks `{docsUrl}/llms.txt` and `{docsUrl}/llms-full.txt`
- Content is purpose-built for LLM consumption (concise, structured)
- Best token efficiency
- Growing adoption (Anthropic, Vercel, Cloudflare, etc.)

### Priority 2: GitHub Adapter

- Fetches from library's GitHub repository
- Sources: `/docs/` directory, `README.md`, wiki pages
- Raw but authoritative — comes directly from the library authors
- Requires chunking and relevance filtering (raw docs can be large)

### Priority 3: Custom Adapter

- User-configured sources in `pro-context.config.yaml`
- Supports local file paths, private URLs, custom registries
- For enterprise/internal documentation

### Fallback Chain

```
1. Try primary adapter for the library
2. If unavailable → try next adapter in chain
3. If all adapters fail but cache exists → serve stale cache with warning
4. If no cache exists → return error with fuzzy suggestions and recovery advice
```

---

## 8. Version Resolution Behavior

### Resolution Rules

1. **Explicit version**: If user provides `version: "0.3.14"`, use exactly that
2. **Version range**: If user provides `version: "0.3.x"`, resolve to latest patch (e.g., `0.3.14`)
3. **No version**: Resolve to latest stable release via package registry (PyPI/npm)
4. **Invalid version**: Return error with available versions listed

### Package Registry Integration

| Language | Registry | Resolution |
|----------|----------|------------|
| Python | PyPI | `GET https://pypi.org/pypi/{package}/json` → extract versions |
| JavaScript | npm | `GET https://registry.npmjs.org/{package}` → extract versions |
| TypeScript | npm | Same as JavaScript |

### Version Caching

- Version lists are cached for 1 hour (versions don't change frequently)
- Documentation is cached per exact version (v0.2.5 and v0.3.0 are separate cache entries)

---

## 9. Error Messages and Recovery Flows

### Error Response Format

Every error follows a consistent structure:

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable description of what went wrong.",
  "recoverable": true,
  "suggestion": "Actionable advice for what to do next.",
  "retryAfter": 5
}
```

### Error Catalog

| Code | Message | Suggestion | Recoverable |
|------|---------|-----------|-------------|
| `LIBRARY_NOT_FOUND` | Library '{query}' not found. | Did you mean '{suggestion}'? | Yes |
| `VERSION_NOT_FOUND` | Version '{version}' not found for {library}. Available: {versions}. | Use one of the available versions. | Yes |
| `TOPIC_NOT_FOUND` | No documentation found for '{topic}' in {library}. | Try searching with search-docs for broader results. | Yes |
| `SOURCE_UNAVAILABLE` | All documentation sources are currently unavailable. | Try again later. Cached content may be available. | Yes |
| `REGISTRY_TIMEOUT` | Could not reach {registry} registry. | Try again or specify the library ID directly. | Yes |
| `RATE_LIMITED` | Rate limit exceeded. | Try again after {retryAfter} seconds. | Yes |
| `INDEXING_IN_PROGRESS` | Documentation is being fetched and indexed. | Try again shortly. | Yes |
| `AUTH_REQUIRED` | Authentication required for this endpoint. | Provide a valid API key via Authorization header. | Yes |
| `AUTH_INVALID` | Invalid or revoked API key. | Check your API key or contact your administrator. | Yes |
| `MAX_TOKENS_EXCEEDED` | Requested content exceeds maximum token limit. | Reduce maxTokens or narrow your topic. | Yes |
| `INTERNAL_ERROR` | An internal error occurred. | This has been logged. Try again. | Yes |

### Recovery Flows

**Network failure:**
```
Source fetch fails → Retry 2x with exponential backoff (1s, 3s)
  → If all retries fail and cache exists → Serve stale cache with stale: true
  → If no cache → Return SOURCE_UNAVAILABLE with suggestion
```

**Unknown library with typo:**
```
resolve-library("langchan") → No exact match
  → Fuzzy match against registry → Find "langchain" (distance: 1)
  → Return LIBRARY_NOT_FOUND with suggestion: "Did you mean 'langchain'?"
```

**Partial documentation:**
```
llms.txt fetch returns partial content → Log warning
  → Return what was fetched with confidence < 1.0
  → Trigger background retry via GitHub adapter
```

---

## 10. Configuration Surface Area

### Configuration File: `pro-context.config.yaml`

```yaml
# Server configuration
server:
  transport: stdio             # "stdio" | "http"
  port: 3100                   # HTTP port (only for http transport)
  host: "127.0.0.1"           # HTTP bind address

# Cache configuration
cache:
  directory: "~/.pro-context/cache"  # SQLite database location
  maxMemoryMB: 100             # In-memory LRU cache size limit
  maxMemoryEntries: 500        # In-memory LRU max entries
  defaultTTLHours: 24          # Default cache TTL
  cleanupIntervalMinutes: 60   # Expired entry cleanup frequency

# Documentation source configuration
sources:
  llmsTxt:
    enabled: true              # Enable llms.txt adapter
  github:
    enabled: true              # Enable GitHub adapter
    token: ""                  # GitHub personal access token (optional, increases rate limit)
  custom: []                   # User-defined sources (see below)

# Per-library overrides
libraries:
  langchain:
    source: "https://python.langchain.com/llms.txt"
    ttlHours: 12
  fastapi:
    source: "https://fastapi.tiangolo.com/llms.txt"
    ttlHours: 48

# Rate limiting (HTTP mode only)
rateLimit:
  maxRequestsPerMinute: 60     # Default per-key rate limit
  burstSize: 10                # Token bucket burst size

# Logging
logging:
  level: "info"                # "debug" | "info" | "warn" | "error"
  format: "json"               # "json" | "pretty"

# Security (HTTP mode only)
security:
  cors:
    origins: ["*"]             # Allowed CORS origins
  urlAllowlist: []             # Additional allowed documentation domains
```

### Environment Variable Overrides

Every config key can be overridden via environment variables:

| Config Key | Environment Variable | Example |
|-----------|---------------------|---------|
| `server.transport` | `PRO_CONTEXT_TRANSPORT` | `http` |
| `server.port` | `PRO_CONTEXT_PORT` | `3100` |
| `cache.directory` | `PRO_CONTEXT_CACHE_DIR` | `/data/cache` |
| `sources.github.token` | `PRO_CONTEXT_GITHUB_TOKEN` | `ghp_xxx` |
| `logging.level` | `PRO_CONTEXT_LOG_LEVEL` | `debug` |
| `logging.level` | `PRO_CONTEXT_DEBUG=true` | Shorthand for `debug` level |

### Custom Source Configuration

```yaml
sources:
  custom:
    - name: "internal-sdk"
      type: "url"              # "url" | "file" | "github"
      url: "https://internal.docs.company.com/sdk/llms.txt"
      libraryId: "company/internal-sdk"
      ttlHours: 6
    - name: "local-docs"
      type: "file"
      path: "/path/to/docs/llms.txt"
      libraryId: "local/my-library"
```

---

## 11. Language Extensibility Model

Pro-Context is designed to be language-agnostic at the data model level, with language-specific behavior isolated in registries and adapters.

### Current Support

- **Python**: Full support via PyPI registry, Python-ecosystem llms.txt sites, GitHub repos

### Extension Points for New Languages

1. **Registry Resolver**: Add `npm-resolver.ts` for JavaScript/TypeScript, `cargo-resolver.ts` for Rust, etc.
   - Each resolver implements the same interface: `resolve(query) → Library`
   - Resolvers are registered in `known-libraries.ts` with a `language` field

2. **Known Libraries**: Add entries to `known-libraries.ts` with `language: "javascript"` etc.
   - Library entries include language-specific metadata (package registry URL, docs URL)

3. **Adapter Behavior**: Adapters are language-agnostic — they fetch documentation by URL regardless of language
   - The adapter chain works identically for Python, JS, Rust, etc.

4. **Version Resolution**: Language-specific registries provide version lists
   - Python: PyPI API
   - JavaScript/TypeScript: npm API
   - Future: crates.io (Rust), pkg.go.dev (Go), etc.

### Data Model Language Field

```typescript
type Language = "python" | "javascript" | "typescript" | string;
```

The `Language` type uses a union with `string` to allow new languages without code changes. Known languages get special registry integration; unknown languages fall back to GitHub-only resolution.

---

## 12. Source Extensibility Model

New documentation sources can be added by implementing the `SourceAdapter` interface.

### Current Adapters

| Adapter | Source | Priority | Notes |
|---------|--------|----------|-------|
| `llms-txt` | `{docsUrl}/llms.txt` | 1 (highest) | Best quality, LLM-optimized |
| `github` | GitHub repository | 2 | Raw but authoritative |
| `custom` | User-configured | 3 | Flexible, enterprise use |

### Adding a New Adapter

To add a new documentation source (e.g., HTML doc site scraper):

1. Create `src/adapters/html-docs.ts`
2. Implement the `SourceAdapter` interface:
   - `canHandle(library)` → Can this adapter serve docs for this library?
   - `fetchDocs(library, options)` → Fetch and return documentation
   - `checkFreshness(library, cached)` → Is the cached version still current?
3. Register the adapter in the adapter chain with a priority number
4. No changes needed to tools, cache, search, or any other component

### Future Adapter Candidates

| Adapter | Source | Priority | Phase |
|---------|--------|----------|-------|
| HTML scraper | Documentation websites | 4 | Future |
| PyPI description | PyPI package page | 5 | Future |
| ReadTheDocs | ReadTheDocs sites | 3.5 | Future |
| Local filesystem | Local markdown files | 2.5 | Future |
