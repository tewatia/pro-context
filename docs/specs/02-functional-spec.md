# Pro-Context: Functional Specification

> **Document**: 02-functional-spec.md
> **Status**: Draft v2
> **Last Updated**: 2026-02-13
> **Depends on**: 01-competitive-analysis.md

---

## 1. Problem Statement

AI coding agents (Claude Code, Cursor, Windsurf, etc.) hallucinate API details when working with third-party libraries. They generate code using deprecated methods, incorrect parameter names, and outdated patterns because their training data has a knowledge cutoff.

The competitive analysis (01-competitive-analysis.md) identified two core findings:

1. **Accuracy is the primary challenge.** The most popular MCP doc server (Context7) achieves only 59-65% accuracy. The best (Deepcon, 90%) uses a proprietary query-understanding model. No open-source solution achieves high accuracy.

2. **Two paradigms exist for documentation retrieval.** The "server decides" paradigm (Context7, Docfork, Deepcon) returns pre-selected chunks. The "agent decides" paradigm (mcpdoc) gives the agent a navigation index and lets it read what it needs. Neither paradigm alone is optimal — server-side search is efficient but accuracy-limited; agent navigation is more accurate but costs more tool calls.

**Pro-Context** is an open-source, self-hostable MCP server that combines both paradigms. It provides server-side search as a fast path for straightforward queries, and structured documentation navigation for cases where the agent needs to browse and reason about the content — the way a human developer uses docs.

**Pro-Context is a documentation retrieval service, not a project assistant.** It does not detect project dependencies, scan filesystems, or manage project state. The agent calling Pro-Context is responsible for understanding its environment and making the right requests. Pro-Context focuses on one thing: given a library and a query, return accurate documentation.

---

## 2. Target Users

### 2.1 Individual Developer

- Uses Claude Code, Cursor, Windsurf, or similar AI coding agent
- Works primarily with Python libraries (LangChain, FastAPI, Pydantic, etc.)
- Wants accurate, up-to-date documentation injected into agent context
- Runs Pro-Context locally via stdio transport
- The agent handles project awareness (reads `pyproject.toml`, etc.) and passes library names to Pro-Context

### 2.2 Development Team

- 3-20 developers sharing an AI-assisted development environment
- Deploys Pro-Context as a shared service via Streamable HTTP transport
- Wants shared documentation cache (one developer's fetch benefits all)
- Needs API key authentication and usage tracking
- May have internal/private library documentation

### 2.3 Enterprise (Future)

- Large organization with custom documentation sources
- Requires audit logging and access controls
- Deploys via Docker in private infrastructure
- Needs custom source adapters for internal docs

---

## 3. Core Concepts

### 3.1 Two Retrieval Paths

Pro-Context offers agents two ways to access documentation:

```
┌──────────────────────────────────────────────────────┐
│  Agent asks: "How do I use streaming in LangChain?"  │
└──────────────┬───────────────────────┬───────────────┘
               │                       │
     ┌─────────▼──────────┐  ┌────────▼───────────────┐
     │  Fast Path          │  │  Navigation Path        │
     │  (server-decides)   │  │  (agent-decides)        │
     │                     │  │                          │
     │  get-docs            │  │  get-library-info       │
     │  (BM25 search,      │  │  (returns TOC)           │
     │   returns content)  │  │       ↓                  │
     │                     │  │  Agent reads TOC,        │
     │  1 tool call        │  │  picks relevant pages    │
     │  ~2-5s              │  │       ↓                  │
     │  Good for keyword   │  │  read-page (1-3x)       │
     │  queries            │  │                          │
     │                     │  │  2-4 tool calls          │
     │                     │  │  ~5-15s                  │
     │                     │  │  Good for conceptual     │
     │                     │  │  queries                 │
     └─────────────────────┘  └──────────────────────────┘
```

**The agent chooses which path to use.** For "ChatOpenAI constructor parameters", the fast path is ideal. For "how do I implement a custom retry strategy with LangChain", the navigation path gives better results because the agent can reason about which docs pages are relevant with its full conversation context.

Both paths share the same cache and source infrastructure.

### 3.2 Documentation Sources

Documentation is fetched from authoritative sources in priority order:

| Priority | Source | Content Type | Coverage |
|----------|--------|-------------|----------|
| 1 | **llms.txt** | LLM-optimized markdown, authored by library maintainers | Growing: 500+ sites, accelerating via Mintlify (10K+ companies) and Fern |
| 2 | **GitHub** | Raw markdown from /docs/, README.md | Near-universal for open-source libraries |
| 3 | **Custom** | User-configured URLs, local files | Enterprise/internal docs |

**llms.txt is the preferred source** because it is authored by the library maintainers, structured for LLM consumption, and delivered as clean markdown — no scraping or HTML parsing required. Where llms.txt is not available, the GitHub adapter provides a universal fallback.

The adapter chain is an internal implementation detail. Tools return consistent response shapes regardless of which source served the content. The agent never needs to know or care whether content came from llms.txt or GitHub.

### 3.3 The Table of Contents (TOC)

Every resolved library has a table of contents — a structured index of available documentation pages. This is the foundation of the navigation path.

**For libraries with llms.txt**: The TOC is the parsed llms.txt content — a list of pages with titles, URLs, and one-sentence descriptions.

**For libraries without llms.txt**: The TOC is generated from the GitHub repository structure — /docs/ directory listing, README.md sections, wiki pages.

The TOC is returned by `get-library-info` and also registered as an MCP resource for later access without tool calls.

---

## 4. User Stories

### US-1: Discover Libraries

> As a developer, when I ask "find LangChain", the agent should be able to discover matching libraries and their available languages.

**Acceptance criteria:**
- Agent calls `resolve-library` with a natural language query
- Server returns a ranked list of matching libraries with IDs, names, descriptions, and supported languages
- Fuzzy matching handles typos (e.g., "langchan" → "langchain")
- Optional language filter narrows results
- Results include all possible matches, not just the best one

### US-2: Get Library Details and Documentation Index

> As a developer, once a library is identified, the agent should be able to get its documentation index (TOC), available versions, and sources.

**Acceptance criteria:**
- Agent calls `get-library-info` with a specific libraryId
- Server returns TOC, available versions, available sources, and default version
- Agent can request specific TOC sections or the full TOC
- If library supports multiple languages and language is not specified, server returns an error asking for clarification
- TOC contains page titles, URLs, and descriptions suitable for agent navigation

### US-3: Quick Documentation Lookup (Fast Path)

> As a developer, when I ask "what are the parameters for FastAPI's Depends()", the agent should get a focused answer quickly.

**Acceptance criteria:**
- Agent calls `get-docs` with library ID, topic, and optional version
- Server searches indexed documentation using BM25
- Returns focused markdown content with source URL, version, confidence score
- Cached responses return in <500ms
- JIT fetch + index + search completes in <5s
- Response includes `relatedPages` — links to pages the agent can read for more depth

### US-4: Navigate Documentation (Navigation Path)

> As a developer, when I ask "how do I implement a custom retry strategy with LangChain", the agent should be able to browse the documentation and find the right pages.

**Acceptance criteria:**
- Agent receives TOC from `get-library-info` (or reads it from a resource)
- Agent reasons about which pages are relevant based on titles and descriptions
- Agent calls `read-page` with a specific documentation URL
- Server fetches the page, caches it, and returns clean markdown
- Agent can read pages progressively using offset/limit for long content
- Fetched pages are cached for subsequent requests

### US-5: Search Across Documentation

> As a developer, when I ask "find all places that mention retry logic", the agent should search across documentation and return ranked results with links.

**Acceptance criteria:**
- Agent calls `search-docs` with a search query
- Optionally scopes the search to specific libraries
- If no libraries specified, searches across all previously indexed content
- Returns ranked results with title, snippet, relevance score, and URL
- Each result URL can be passed to `read-page` for full content

### US-6: Version-Specific Documentation

> As a developer, I need documentation for a specific library version, not just "latest".

**Acceptance criteria:**
- `get-library-info`, `get-docs`, `search-docs`, and `read-page` accept an optional `version` parameter
- Version resolves to exact release via PyPI (Python) or npm (JS/TS)
- If version is omitted, server uses latest stable version
- Cached documentation is version-specific (v0.2 and v0.3 stored separately)

### US-7: Team Deployment with API Keys

> As a team lead, I want to deploy Pro-Context as a shared service so all team members benefit from cached documentation.

**Acceptance criteria:**
- Server starts in HTTP mode with `transport: http`
- API keys are required for all requests
- Admin CLI (`pro-context-admin`) can create, list, and revoke keys
- Each key has configurable rate limits
- Shared cache means one developer's fetch benefits all others

### US-8: Graceful Degradation

> As a developer, I expect useful responses even when documentation sources are temporarily unavailable.

**Acceptance criteria:**
- If primary source (llms.txt) fails, server falls back to GitHub adapter
- If all sources fail but cache exists, stale cache is served with a warning
- If library is unknown, server returns fuzzy suggestions
- Error responses include actionable recovery suggestions

---

## 5. MCP Tool Definitions

Pro-Context exposes **5 tools**. The tool set is designed to support both the fast path (server-decides) and the navigation path (agent-decides), with clean separation between discovery, detail retrieval, content access, and search.

### 5.1 `resolve-library`

Discovers libraries matching a natural language query. This is a pure discovery tool — it finds libraries, it does not fetch documentation content.

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
      "description": "Optional language filter (e.g., 'python', 'javascript'). Only needed to disambiguate when the same library name exists across languages."
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
    "results": {
      "type": "array",
      "items": {
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
          "languages": {
            "type": "array",
            "items": { "type": "string" },
            "description": "Languages this library is available in (e.g., ['python'], ['python', 'javascript'])"
          },
          "relevance": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Match relevance score"
          }
        }
      },
      "description": "Matching libraries, ranked by relevance. All possible matches are returned."
    }
  }
}
```

**Behavior:**
1. Fuzzy-match `query` against known library registry
2. If no match in registry, attempt resolution via PyPI/npm
3. If still no match, return empty results with fuzzy suggestions
4. If `language` is provided, filter results to that language
5. Return all matching libraries ranked by relevance score

**Error cases:**
- No matches found → empty `results` array (not an error — useful signal)
- Registry timeout → `REGISTRY_TIMEOUT` with retry advice

---

### 5.2 `get-library-info`

Returns detailed information about a specific library: TOC, available versions, documentation sources, and default version. This is the entry point to the navigation path.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "Canonical library ID from resolve-library (e.g., 'langchain-ai/langchain')"
    },
    "language": {
      "type": "string",
      "description": "Required if the library supports multiple languages. Specifies which language variant to fetch info for."
    },
    "version": {
      "type": "string",
      "description": "Specific version. Defaults to latest stable if omitted."
    },
    "sections": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Optional: only return TOC entries from these sections (e.g., ['Getting Started', 'API Reference']). If omitted, returns the full TOC."
    }
  },
  "required": ["libraryId"]
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "Canonical library identifier"
    },
    "name": {
      "type": "string",
      "description": "Human-readable library name"
    },
    "language": {
      "type": "string",
      "description": "Language for this info response"
    },
    "defaultVersion": {
      "type": "string",
      "description": "Latest stable version"
    },
    "availableVersions": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Recent available versions (most recent first, max 10)"
    },
    "sources": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Available documentation sources (e.g., ['llms.txt', 'github'])"
    },
    "toc": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": { "type": "string", "description": "Page title" },
          "url": { "type": "string", "description": "Page URL (can be passed to read-page)" },
          "description": { "type": "string", "description": "One-sentence description of the page" },
          "section": { "type": "string", "description": "Section grouping (e.g., 'Getting Started', 'API Reference')" }
        }
      },
      "description": "Table of contents — documentation pages available for this library. Use read-page to fetch any of these URLs."
    },
    "tocTruncated": {
      "type": "boolean",
      "description": "True if the TOC was filtered by sections parameter. Full TOC available via the library resource."
    }
  }
}
```

**Behavior:**
1. Look up `libraryId` in registry (exact match, no fuzzy matching)
2. If library supports multiple languages and `language` is not provided → return `LANGUAGE_REQUIRED` error listing available languages
3. Resolve version (if not specified, use latest stable)
4. Fetch available versions from package registry (cached for 1 hour)
5. Determine available documentation sources
6. Fetch and parse the TOC (source-agnostic — the adapter chain handles how)
7. If `sections` is specified, filter TOC entries to matching sections
8. Cache the TOC
9. Register `library://{libraryId}/toc` as an MCP resource
10. Add library to session resolved list
11. Return library metadata + TOC

**Error cases:**
- Library not found → `LIBRARY_NOT_FOUND`
- Language required → `LANGUAGE_REQUIRED` with available languages list
- Version not found → `VERSION_NOT_FOUND` with available versions
- No documentation sources found → returns metadata without TOC, with a note that no docs are indexed

---

### 5.3 `get-docs`

The **fast path** tool. Retrieves focused documentation for a specific topic using server-side search (BM25). Best for keyword-heavy queries where the server can match effectively.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "Canonical library ID from resolve-library"
    },
    "topic": {
      "type": "string",
      "description": "Documentation topic (e.g., 'chat models', 'streaming', 'dependency injection')"
    },
    "language": {
      "type": "string",
      "description": "Required if the library supports multiple languages."
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
    },
    "relatedPages": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": { "type": "string" },
          "url": { "type": "string" },
          "description": { "type": "string" }
        }
      },
      "description": "Other documentation pages that may be relevant. Use read-page to fetch them if the above content is insufficient."
    }
  }
}
```

**Behavior:**
1. Resolve version (if not specified, use latest stable)
2. Validate language if library supports multiple
3. Check cache (memory → SQLite) for matching (libraryId, language, version, topic)
4. If cached and fresh → return immediately
5. If cached but stale → return stale with `stale: true`, trigger background refresh
6. If not cached → fetch documentation via adapter chain, chunk into sections, index with BM25
7. Rank chunks by topic relevance, select top chunk(s) within `maxTokens` budget
8. Identify related pages from the TOC that the agent might want to read for more context
9. Store in cache
10. Return content + related pages

**The `relatedPages` field**: This bridges the fast path and the navigation path. If the server-side BM25 search returns content with low confidence (e.g., <0.6), the `relatedPages` give the agent a way to navigate further. The agent sees "here's what I found, but you might also want to read these pages" — and can use `read-page` to explore them.

**Error cases:**
- Library not found → `LIBRARY_NOT_FOUND`
- Language required → `LANGUAGE_REQUIRED`
- Topic not found → `TOPIC_NOT_FOUND` with suggestion to try `search-docs` or browse the TOC via `get-library-info`
- All sources unavailable → serve stale cache or `SOURCE_UNAVAILABLE`

---

### 5.4 `search-docs`

Searches across indexed documentation and returns ranked results with URLs. Optionally scoped to specific libraries, or searches across all previously indexed content.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Search query (e.g., 'retry logic', 'error handling middleware')"
    },
    "libraryIds": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Optional: restrict search to these libraries. If omitted, searches across all indexed content."
    },
    "language": {
      "type": "string",
      "description": "Optional language filter."
    },
    "version": {
      "type": "string",
      "description": "Library version. Only applicable when searching a single library. Defaults to latest stable."
    },
    "maxResults": {
      "type": "number",
      "description": "Maximum number of results. Default: 5. Range: 1-20.",
      "default": 5,
      "minimum": 1,
      "maximum": 20
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
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "libraryId": { "type": "string", "description": "Which library this result is from" },
          "title": { "type": "string", "description": "Section/page title" },
          "snippet": { "type": "string", "description": "Relevant text excerpt (~100 tokens)" },
          "relevance": { "type": "number", "minimum": 0, "maximum": 1, "description": "BM25 relevance score (normalized)" },
          "url": { "type": "string", "description": "Page URL — use read-page to fetch full content" },
          "section": { "type": "string", "description": "Documentation section path" }
        }
      }
    },
    "totalMatches": {
      "type": "number",
      "description": "Total matches found (may exceed maxResults)"
    },
    "searchedLibraries": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Library IDs that were searched"
    }
  }
}
```

**Behavior:**
1. If `libraryIds` provided, validate each exists and has indexed content
2. If no `libraryIds`, search across all content in the index (only previously fetched/indexed content — this is not a global search)
3. If documentation not yet indexed for a specified library, trigger JIT fetch + index, return `INDEXING_IN_PROGRESS`
4. Execute BM25 search across relevant indexed chunks
5. Rank results by relevance score
6. Return top N results with snippets, URLs, and library attribution

**Important**: `search-docs` only searches content that has been previously fetched and indexed. It does not proactively index libraries. If the agent searches for "retry" without specifying libraries, it searches across whatever content Pro-Context has already cached from prior `get-docs`, `get-library-info`, or `read-page` calls. The `searchedLibraries` field in the response makes this explicit.

**Error cases:**
- Specified library not indexed → `INDEXING_IN_PROGRESS` with `retryAfter`
- No results → empty results array (not an error)

---

### 5.5 `read-page`

The **navigation path** tool. Fetches a specific documentation page URL and returns its content as markdown. Supports offset-based reading for long pages.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "Documentation page URL to fetch. Must be from a resolved library's TOC, a search result, or a relatedPages entry."
    },
    "maxTokens": {
      "type": "number",
      "description": "Maximum tokens to return. Default: 10000.",
      "default": 10000,
      "minimum": 500,
      "maximum": 50000
    },
    "offset": {
      "type": "number",
      "description": "Token offset to start reading from. Use this to continue reading a previously truncated page. Default: 0 (start of page).",
      "default": 0,
      "minimum": 0
    }
  },
  "required": ["url"]
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "content": {
      "type": "string",
      "description": "Page content in markdown format"
    },
    "title": {
      "type": "string",
      "description": "Page title"
    },
    "url": {
      "type": "string",
      "description": "Canonical URL of the fetched page"
    },
    "totalTokens": {
      "type": "number",
      "description": "Total page content length in estimated tokens"
    },
    "offset": {
      "type": "number",
      "description": "Token offset this response starts from"
    },
    "tokensReturned": {
      "type": "number",
      "description": "Number of tokens in this response"
    },
    "hasMore": {
      "type": "boolean",
      "description": "Whether more content exists beyond this response. If true, call read-page again with offset = offset + tokensReturned."
    },
    "cached": {
      "type": "boolean",
      "description": "Whether this page was served from cache"
    }
  }
}
```

**Behavior:**
1. Validate URL against the allowlist (see Security, Section 9)
2. Check page cache for this URL
3. If cached → serve from cache (applying offset/maxTokens)
4. If not cached → fetch the URL, convert to markdown if needed, cache the full page
5. Apply offset: skip to the specified token position
6. Apply maxTokens: return up to `maxTokens` tokens from the offset position
7. Set `hasMore` to true if content remains beyond offset + maxTokens
8. Index the page content for BM25 search (background)
9. Return content with position metadata

**Offset-based reading**: When a page exceeds `maxTokens`, the response includes `hasMore: true` and position metadata. The agent can call `read-page` again with `offset` set to `offset + tokensReturned` to continue reading. The server caches the full page on first fetch, so subsequent offset reads are served from cache without re-fetching.

**URL allowlist**: `read-page` does not fetch arbitrary URLs. It only fetches URLs that:
- Appear in a resolved library's TOC
- Are returned by `search-docs` results
- Are returned as `relatedPages` by `get-docs`
- Are from domains in the configured allowlist
- Match documentation domains from the known-libraries registry

This prevents SSRF while allowing flexible navigation within documentation.

**Error cases:**
- URL not in allowlist → `URL_NOT_ALLOWED` with suggestion to resolve the library first
- URL returns 404 → `PAGE_NOT_FOUND`
- URL returns non-documentation content → `INVALID_CONTENT`
- Offset beyond content length → empty content with `hasMore: false`

---

## 6. MCP Resource Definitions

Resources provide data that agents can access without tool calls.

### 6.1 `pro-context://health`

**URI**: `pro-context://health`
**MIME Type**: `application/json`
**Description**: Server health status.

```json
{
  "status": "healthy",
  "uptime": 3600,
  "cache": {
    "memoryEntries": 142,
    "sqliteEntries": 1024,
    "hitRate": 0.87
  },
  "adapters": {
    "llms-txt": { "status": "available", "lastSuccess": "2026-02-12T10:00:00Z" },
    "github": { "status": "available", "rateLimitRemaining": 4850 }
  },
  "version": "1.0.0"
}
```

### 6.2 `pro-context://session/resolved-libraries`

**URI**: `pro-context://session/resolved-libraries`
**MIME Type**: `application/json`
**Description**: Libraries resolved in the current session. Gives agents recall of what they've already looked up without repeating tool calls.

```json
{
  "libraries": [
    { "id": "langchain-ai/langchain", "name": "LangChain", "language": "python", "version": "0.3.14" },
    { "id": "pydantic/pydantic", "name": "Pydantic", "language": "python", "version": "2.10.0" }
  ]
}
```

This resource is updated whenever `get-library-info` is called. It accumulates across the session — libraries are added but never removed.

### 6.3 `library://{libraryId}/toc`

**URI Template**: `library://{libraryId}/toc`
**MIME Type**: `text/markdown`
**Description**: Table of contents for a specific library. Contains the same TOC data returned by `get-library-info`, but accessible as a resource for libraries that have already been resolved.

This resource is dynamically registered after `get-library-info` is called for a library.

The TOC resource is formatted as markdown with links the agent can follow via `read-page`:

```markdown
# LangChain Documentation

## Getting Started
- [Introduction](https://docs.langchain.com/docs/introduction) — Overview of LangChain's architecture and concepts
- [Installation](https://docs.langchain.com/docs/installation) — How to install LangChain and its dependencies
- [Quick Start](https://docs.langchain.com/docs/quickstart) — Build your first LangChain application

## Chat Models
- [Chat Models Overview](https://docs.langchain.com/docs/chat-models) — Working with chat-based language models
- [Streaming](https://docs.langchain.com/docs/streaming) — Stream responses token by token
...
```

### 6.4 Dynamic Resource Registration

When the server resolves a library (via `get-library-info`), it:

1. Registers `library://{libraryId}/toc` as a new resource
2. Updates `pro-context://session/resolved-libraries`
3. Emits a `notifications/resources/list_changed` notification per MCP spec
4. MCP clients that support resource subscriptions will see the new resource

---

## 7. MCP Prompt Templates

Prompt templates provide reusable workflows that agents can invoke. Updated to reference the current tool set.

### 7.1 `migrate-code`

**Name**: `migrate-code`
**Description**: Generate a migration plan for upgrading library code between versions.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `libraryId` | Yes | Library to migrate |
| `fromVersion` | Yes | Current version |
| `toVersion` | Yes | Target version |
| `codeSnippet` | No | Code to migrate |

**Template:**
```
You are helping migrate code from {libraryId} version {fromVersion} to {toVersion}.

Steps:
1. Use get-library-info to get the documentation index for {libraryId}
2. Look for changelog, migration guide, or "what's new" pages in the TOC
3. Use read-page to fetch the relevant migration/changelog pages
4. If specific APIs in the code snippet need investigation, use get-docs or search-docs

{#if codeSnippet}
Migrate the following code:
```
{codeSnippet}
```
{/if}

Provide:
1. A list of breaking changes between {fromVersion} and {toVersion} that affect this code
2. The migrated code with explanations for each change
3. Any new features in {toVersion} that could improve this code
```

### 7.2 `debug-with-docs`

**Name**: `debug-with-docs`
**Description**: Debug an issue using current library documentation.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `libraryId` | Yes | Library where the issue occurs |
| `errorMessage` | Yes | Error message or description |
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
1. Use search-docs to find documentation related to this error message or the APIs involved
2. Use read-page on the most relevant search results to understand correct usage
3. If needed, use get-library-info to browse the TOC for related topics

Based on the documentation, identify:
1. The root cause of the error
2. The correct API usage (with documentation source)
3. A fixed version of the code
```

### 7.3 `explain-api`

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
1. Use get-docs to fetch documentation for {apiName}
2. If the result has low confidence or is incomplete, use the relatedPages or get-library-info TOC to find more specific pages
3. Use read-page on relevant pages to get complete API documentation
4. If needed, use search-docs to find related APIs or usage patterns

Provide:
1. What {apiName} does and when to use it
2. Complete parameter/argument documentation
3. Return value documentation
4. At least 2 practical examples from the documentation
5. Common pitfalls or gotchas
```

---

## 8. Documentation Source Adapter Chain

The adapter chain is an internal implementation detail. It determines how documentation is fetched, but does not affect tool interfaces or response shapes. All tools return consistent responses regardless of which adapter served the content.

### 8.1 Priority Order

```
Request
  │
  ▼
[1] llms.txt ──── Best quality. Authored by library maintainers, structured for LLMs.
  │                Checks: {docsUrl}/llms.txt
  │ fail
  ▼
[2] GitHub ────── Universal fallback. Raw but authoritative.
  │                Fetches: /docs/ directory, README.md
  │ fail
  ▼
[3] Custom ────── User-configured. For internal/private docs.
  │                Sources: URLs, local files, private GitHub repos
  │ fail
  ▼
[4] Stale Cache ─ Last resort. Serves expired cache with stale: true warning.
  │ fail
  ▼
[Error] ───────── LIBRARY_NOT_FOUND or SOURCE_UNAVAILABLE with recovery suggestions.
```

### 8.2 Adapter Contract

Each adapter implements a uniform interface. The server calls adapters in priority order until one succeeds. The adapter contract:

- `canHandle(library)` — can this adapter serve docs for this library?
- `fetchToc(library, version)` — return a structured TOC (array of {title, url, description, section})
- `fetchPage(url)` — fetch a single page, return markdown content
- `checkFreshness(library, cached)` — is the cached content still valid?

Adapters are responsible for source-specific concerns (parsing llms.txt format, using GitHub API, reading local files). The server and tools never see these details.

### 8.3 Custom Sources

Custom sources are configured in `pro-context.config.yaml`:

```yaml
sources:
  custom:
    - name: "internal-sdk"
      type: "url"                # "url" | "file" | "github"
      url: "https://internal.docs.company.com/sdk/llms.txt"
      libraryId: "company/internal-sdk"
    - name: "local-docs"
      type: "file"
      path: "/path/to/docs/llms.txt"
      libraryId: "local/my-library"
```

Custom sources follow the same adapter contract.

---

## 9. Security

### 9.1 URL Allowlist (SSRF Prevention)

`read-page` fetches URLs provided by the agent. To prevent SSRF:

**Default allowlist:**
- `github.com`, `raw.githubusercontent.com`
- `*.github.io`
- `pypi.org`, `registry.npmjs.org`
- `*.readthedocs.io`
- Documentation domains from the known-libraries registry
- Domains from any llms.txt file the server has fetched

**Always blocked:**
- Private IPs (127.0.0.1, 10.x, 172.16-31.x, 192.168.x)
- `file://` URLs
- Non-HTTP(S) protocols

**Dynamic allowlist expansion:**
When the server fetches an llms.txt file, all URLs in that file are added to the session allowlist. This means if LangChain's llms.txt links to `docs.langchain.com/some/page`, that URL becomes fetchable via `read-page` — without the user needing to configure it.

Custom source domains from config are also added to the allowlist.

### 9.2 Input Validation

All tool inputs are validated with Zod schemas at the MCP boundary:
- `libraryId`: alphanumeric + `-_./`, max 200 chars
- `topic`, `query`: max 500 chars
- `url`: must be valid URL, must pass allowlist check
- `version`: max 50 chars
- Numeric parameters: validated against min/max ranges

### 9.3 Authentication (HTTP Mode)

- API keys use `pc_` prefix + 40 chars base64url
- Keys are stored as SHA-256 hashes (never plaintext)
- Bearer token authentication via `Authorization` header
- Admin CLI for key creation, listing, revocation

### 9.4 Rate Limiting (HTTP Mode)

- Token bucket algorithm per API key
- Configurable capacity and refill rate
- Rate limit headers in responses (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`)
- Per-key rate limit overrides

---

## 10. Version Resolution

### 10.1 Resolution Rules

1. **Explicit version** (`version: "0.3.14"`): Use exactly that version
2. **Version range** (`version: "0.3.x"`): Resolve to latest patch via package registry
3. **No version**: Resolve to latest stable release
4. **Invalid version**: Return `VERSION_NOT_FOUND` with available versions

### 10.2 Language Resolution Rules

1. **Library supports one language**: Language parameter is optional, ignored if provided
2. **Library supports multiple languages**: Language parameter is required. If omitted, return `LANGUAGE_REQUIRED` error listing available languages
3. **Language filter on resolve-library**: Optional — only used to narrow discovery results

### 10.3 Package Registry Integration

| Language | Registry | API |
|----------|----------|-----|
| Python | PyPI | `GET https://pypi.org/pypi/{package}/json` |
| JavaScript (future) | npm | `GET https://registry.npmjs.org/{package}` |

### 10.4 Version → Documentation URL Mapping

Different documentation sites handle versioning differently:

| Pattern | Example | Libraries |
|---------|---------|-----------|
| Version in URL path | `docs.pydantic.dev/2.10/llms.txt` | Pydantic |
| "latest" URL always current | `docs.langchain.com/llms.txt` | LangChain |
| Subdomain per version | `v3.fastapi.tiangolo.com/` | Some projects |
| No versioned docs | Single version only | Many smaller libs |

The known-libraries registry stores the URL pattern for each library. For libraries not in the registry, the server falls back to the latest/default documentation URL.

### 10.5 Version Caching

- Version lists: cached for 1 hour (versions change infrequently)
- Documentation content: cached per exact version (v0.2.5 and v0.3.0 are separate entries)
- TOC: cached per version, refreshed when version list changes

---

## 11. Error Handling

### 11.1 Error Response Format

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable description.",
  "recoverable": true,
  "suggestion": "Actionable advice for what to do next.",
  "retryAfter": 5
}
```

### 11.2 Error Catalog

| Code | Trigger | Suggestion |
|------|---------|-----------|
| `LIBRARY_NOT_FOUND` | Unknown library ID | Did you mean '{suggestion}'? Use resolve-library to discover libraries. |
| `LANGUAGE_REQUIRED` | Multi-language library, no language specified | Available languages: {list}. Specify the language parameter. |
| `VERSION_NOT_FOUND` | Invalid version | Available versions: {list} |
| `TOPIC_NOT_FOUND` | BM25 search finds nothing for topic | Try search-docs for broader results, or browse the TOC via get-library-info. |
| `PAGE_NOT_FOUND` | read-page URL returns 404 | Check the URL or use get-library-info to refresh the TOC. |
| `URL_NOT_ALLOWED` | read-page URL fails allowlist check | Resolve the library first with get-library-info, or add the domain to your config. |
| `SOURCE_UNAVAILABLE` | All adapters fail, no cache | Try again later. |
| `REGISTRY_TIMEOUT` | PyPI/npm unreachable | Try again or specify the library ID directly. |
| `RATE_LIMITED` | Token bucket exhausted | Try again after {retryAfter} seconds. |
| `INDEXING_IN_PROGRESS` | Docs being fetched/indexed | Try again in {retryAfter} seconds. |
| `AUTH_REQUIRED` | Missing API key (HTTP mode) | Provide API key via Authorization header. |
| `AUTH_INVALID` | Bad/revoked API key | Check your API key. |
| `INVALID_CONTENT` | Fetched URL is not documentation | URL does not appear to contain documentation. |
| `INTERNAL_ERROR` | Unexpected server error | This has been logged. Try again. |

### 11.3 Recovery Flows

**Network failure:**
```
Source fetch fails → Retry 2x with exponential backoff (1s, 3s)
  → All retries fail + cache exists → Serve stale cache (stale: true)
  → No cache → SOURCE_UNAVAILABLE
```

**Unknown library with typo:**
```
resolve-library("langchan") → Fuzzy match (Levenshtein distance ≤ 3)
  → Returns results with "langchain" ranked first
```

**Low-confidence get-docs result:**
```
get-docs returns content with confidence < 0.5
  → Response includes relatedPages from TOC
  → Agent can use read-page to explore related pages for better content
```

---

## 12. Configuration

### 12.1 Configuration File: `pro-context.config.yaml`

```yaml
# Server
server:
  transport: stdio             # "stdio" | "http"
  port: 3100                   # HTTP port (http transport only)
  host: "127.0.0.1"           # HTTP bind address

# Cache
cache:
  directory: "~/.pro-context/cache"
  maxMemoryMB: 100
  maxMemoryEntries: 500
  defaultTTLHours: 24
  cleanupIntervalMinutes: 60

# Documentation sources
sources:
  llmsTxt:
    enabled: true
  github:
    enabled: true
    token: ""                  # GitHub PAT (optional, increases rate limit from 60 to 5000/hr)
  custom: []

# Per-library overrides
libraryOverrides:
  langchain:
    docsUrl: "https://docs.langchain.com"
    ttlHours: 12
  fastapi:
    docsUrl: "https://fastapi.tiangolo.com"
    source: "github"           # Force GitHub adapter
    ttlHours: 48

# Rate limiting (HTTP mode only)
rateLimit:
  maxRequestsPerMinute: 60
  burstSize: 10

# Logging
logging:
  level: "info"                # "debug" | "info" | "warn" | "error"
  format: "json"               # "json" | "pretty"

# Security (HTTP mode only)
security:
  cors:
    origins: ["*"]
  urlAllowlist: []             # Additional allowed domains for read-page
```

### 12.2 Environment Variable Overrides

| Config Key | Environment Variable | Example |
|-----------|---------------------|---------|
| `server.transport` | `PRO_CONTEXT_TRANSPORT` | `http` |
| `server.port` | `PRO_CONTEXT_PORT` | `3100` |
| `cache.directory` | `PRO_CONTEXT_CACHE_DIR` | `/data/cache` |
| `sources.github.token` | `PRO_CONTEXT_GITHUB_TOKEN` | `ghp_xxx` |
| `logging.level` | `PRO_CONTEXT_LOG_LEVEL` | `debug` |
| — | `PRO_CONTEXT_DEBUG=true` | Shorthand for `debug` level |

---

## 13. Language and Source Extensibility

### 13.1 Language Extensibility

Pro-Context is language-agnostic at the data model level. Language-specific behavior is isolated in registry resolvers.

**Current**: Python (PyPI registry)
**Future**: JavaScript/TypeScript (npm), Rust (crates.io), Go (pkg.go.dev)

Adding a new language requires:
1. A registry resolver (e.g., `npm-resolver.ts`) that implements version resolution
2. Known-library entries with the new language
3. No changes to adapters, cache, search, tools, or config

### 13.2 Source Extensibility

New documentation sources are added by implementing the adapter contract (Section 8.2):
- `canHandle(library)` — can this adapter serve docs for this library?
- `fetchToc(library, version)` — fetch the table of contents
- `fetchPage(url)` — fetch a single documentation page
- `checkFreshness(library, cached)` — is the cache still valid?

Current adapters: llms-txt, github, custom

Future adapter candidates:
- HTML scraper (for docs sites without llms.txt or GitHub source)
- ReadTheDocs adapter
- PyPI long-description adapter

---

## 14. Design Decisions and Rationale

### D1: `read-page` replaces `get-examples`

**Decision**: Dropped the `get-examples` tool in favor of `read-page`.

**Rationale**: `get-examples` was a specialized content extraction tool — it fetched docs, found code blocks, and returned them. But modern AI agents are excellent at extracting code examples from documentation they read. What agents cannot do without a tool is navigate to a specific URL. `read-page` enables the entire navigation paradigm (the key insight from the competitive analysis), while `get-examples` solved a problem the agent can solve itself.

### D2: `resolve-library` is pure discovery, `get-library-info` provides depth

**Decision**: Split the original `resolve-library` (which returned metadata + TOC) into two tools: `resolve-library` for discovery and `get-library-info` for detail retrieval.

**Rationale**: The original design overloaded resolve-library as both a search tool and an info-fetching tool. This created ambiguity: should it return all matches or just the best one? Should it include the TOC? The split gives each tool a single responsibility. `resolve-library` answers "what libraries match this query?" and `get-library-info` answers "tell me about this specific library." The extra tool call is a minor cost compared to the clarity gained. The agent always knows what it's getting.

### D3: `get-docs` includes `relatedPages`

**Decision**: The `get-docs` response includes links to related documentation pages.

**Rationale**: This bridges the fast path and navigation path. When BM25 returns a low-confidence result, the agent can see related pages and use `read-page` to explore them. Without this, the agent would need to call `get-library-info` to get the TOC, then reason about which pages to read. `relatedPages` provides a natural "continue exploring" affordance.

### D4: `search-docs` returns references, not content

**Decision**: Search results contain snippets and URLs, not full page content.

**Rationale**: Search is for narrowing. The agent scans search results to identify promising pages, then uses `read-page` to get full content for the most relevant ones. Returning full content for 5 search results would be 5x the tokens — most of which would be irrelevant. The snippet is enough for the agent to judge relevance.

### D5: Project detection is the agent's responsibility

**Decision**: Pro-Context does not scan project files, detect dependencies, or manage project state.

**Rationale**: AI coding agents already have filesystem access — they can read `pyproject.toml`, `requirements.txt`, `package.json`, etc. Duplicating this capability in the server adds complexity, couples Pro-Context to specific project formats, and creates a fuzzy boundary of responsibility. Pro-Context is a documentation retrieval service. The agent handles environment awareness and passes library names to Pro-Context. This separation keeps the server focused and testable.

### D6: Dynamic URL allowlist via llms.txt

**Decision**: When the server fetches an llms.txt file, all URLs listed in it are added to the session allowlist.

**Rationale**: llms.txt files contain curated links to documentation pages. These links are trustworthy because they come from the library's official documentation site. Automatically allowing them means the agent can navigate any page referenced in the TOC without the user needing to configure domains manually. This is essential for the navigation path to work without friction.

### D7: `read-page` supports offset-based reading

**Decision**: `read-page` accepts an `offset` parameter for progressive reading of long pages, with the server caching the full page on first fetch.

**Rationale**: Some documentation pages exceed reasonable context budgets (10K+ tokens). Without offset support, the agent would either need to raise `maxTokens` (wasting context on content it has already seen) or miss the later portions of the page entirely. Offset-based reading lets the agent "scroll" through long pages efficiently. The server caches the full page on first fetch, so offset reads are served from cache without re-fetching. This aligns with the competitive analysis finding that modern agents can read progressively, like humans scrolling through docs.

### D8: `search-docs` supports cross-library search

**Decision**: `search-docs` does not require a library ID. It can search across all indexed content, optionally scoped to specific libraries.

**Rationale**: Developers often don't know which library implements a concept. "How do I handle retries?" could be in LangChain, httpx, or tenacity. Cross-library search lets the agent find the right page without knowing the library upfront. The important caveat is that this searches only previously indexed content — it's not a global search engine. The `searchedLibraries` field in the response makes this explicit so the agent knows the scope.

### D9: No `llms-full.txt` support

**Decision**: Pro-Context does not fetch or use `llms-full.txt` files.

**Rationale**: `llms-full.txt` can be enormous (Cloudflare: 3.7M tokens). It doesn't fit in a context window and must be chunked/indexed entirely before any search is possible. The per-page pattern (llms.txt index + read individual pages) is more aligned with the agent navigation paradigm and more efficient: pages are fetched and indexed on demand as the agent reads them. BM25 search quality improves organically as more pages are accessed. The upfront cost of downloading and indexing a multi-megabyte file for a single query is not justified.

---

## 15. Open Questions

### Q1: How should the known-libraries registry be structured and maintained?

The registry maps library names to metadata (docs URL, GitHub repo, supported languages, URL patterns for versioned docs). This is a critical data structure — the quality of `resolve-library` depends on it. Should this be a static JSON file shipped with Pro-Context? A community-maintained repository? Auto-populated from PyPI metadata?

**Lean**: Start with a curated JSON file covering the top 200 Python libraries. Allow community contributions via PRs. Augment with live PyPI lookups for libraries not in the registry.

### Q2: Should `get-docs` require a prior `get-library-info` call?

Currently `get-docs` takes a `libraryId` and can trigger JIT fetching if the library hasn't been resolved yet. Should it instead require that `get-library-info` has been called first (ensuring the TOC and index exist), or should it work standalone for the fast-path use case where the agent already knows the library ID?

**Lean**: `get-docs` should work standalone. Requiring a prior call adds friction to the fast path. If the library hasn't been indexed yet, `get-docs` triggers JIT fetch internally. The agent shouldn't need to worry about server-side state.

### Q3: What is the right token estimation strategy for offset/limit?

Token counts are approximate. Different tokenizers produce different counts. Should Pro-Context use a specific tokenizer (tiktoken cl100k, etc.), a character-based heuristic (chars/4), or let the agent specify its tokenizer?

**Lean**: Use a simple character-based heuristic (1 token ≈ 4 characters) for offset/limit calculations. This is fast, requires no external dependencies, and is accurate enough for pagination purposes. Exact token counts only matter at the agent's context window boundary, which the agent manages itself.
