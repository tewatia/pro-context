# Pro-Context: Functional Specification

> **Document**: 02-functional-spec.md
> **Status**: Draft v3
> **Last Updated**: 2026-02-16
> **Depends on**: 01-competitive-analysis.md

---

## Table of Contents

- [1. Problem Statement](#1-problem-statement)
- [2. Target Users](#2-target-users)
  - [2.1 Individual Developer](#21-individual-developer)
  - [2.2 Development Team](#22-development-team)
- [3. Core Concepts](#3-core-concepts)
  - [3.1 Two Retrieval Paths](#31-two-retrieval-paths)
  - [3.2 Documentation Sources](#32-documentation-sources)
  - [3.3 The Table of Contents (TOC)](#33-the-table-of-contents-toc)
- [4. User Stories](#4-user-stories)
  - [US-1: Discover Libraries](#us-1-discover-libraries)
  - [US-2: Get Library Details and Documentation Index](#us-2-get-library-details-and-documentation-index)
  - [US-3: Quick Documentation Lookup (Fast Path)](#us-3-quick-documentation-lookup-fast-path)
  - [US-4: Navigate Documentation (Navigation Path)](#us-4-navigate-documentation-navigation-path)
  - [US-5: Search Across Documentation](#us-5-search-across-documentation)
  - [US-6: Version-Specific Documentation](#us-6-version-specific-documentation)
  - [US-7: Team Deployment with API Keys](#us-7-team-deployment-with-api-keys)
  - [US-8: Graceful Degradation](#us-8-graceful-degradation)
- [5. MCP Tool Definitions](#5-mcp-tool-definitions)
  - [5.1 resolve-library](#51-resolve-library)
  - [5.2 get-library-info](#52-get-library-info)
  - [5.3 get-docs](#53-get-docs)
  - [5.4 search-docs](#54-search-docs)
  - [5.5 read-page](#55-read-page)
- [6. MCP Resource Definitions](#6-mcp-resource-definitions)
  - [6.1 pro-context://health](#61-pro-contexthealth)
  - [6.2 pro-context://session/resolved-libraries](#62-pro-contextsessionresolved-libraries)
  - [6.3 Why TOC Is a Tool, Not a Resource](#63-why-toc-is-a-tool-not-a-resource)
  - [6.4 Session Resource Updates](#64-session-resource-updates)
- [7. MCP Prompt Templates](#7-mcp-prompt-templates)
  - [7.1 migrate-code](#71-migrate-code)
  - [7.2 debug-with-docs](#72-debug-with-docs)
  - [7.3 explain-api](#73-explain-api)
- [8. Documentation Fetching](#8-documentation-fetching)
  - [8.1 Fetching Flow](#81-fetching-flow)
  - [8.2 Custom Documentation Sources](#82-custom-documentation-sources)
- [9. Security](#9-security)
  - [9.1 URL Allowlist (SSRF Prevention)](#91-url-allowlist-ssrf-prevention)
  - [9.2 Input Validation](#92-input-validation)
  - [9.3 Authentication (HTTP Mode)](#93-authentication-http-mode)
  - [9.4 Rate Limiting (HTTP Mode)](#94-rate-limiting-http-mode)
- [10. Version Resolution](#10-version-resolution)
  - [10.1 Resolution Rules](#101-resolution-rules)
  - [10.2 Language Handling](#102-language-handling)
  - [10.3 Package Registry Integration](#103-package-registry-integration)
  - [10.4 Version → Documentation URL Mapping](#104-version--documentation-url-mapping)
  - [10.5 Version Caching](#105-version-caching)
- [11. Error Handling](#11-error-handling)
  - [11.1 Error Response Format](#111-error-response-format)
  - [11.2 Error Catalog](#112-error-catalog)
  - [11.3 Recovery Flows](#113-recovery-flows)
- [12. Configuration](#12-configuration)
  - [12.1 Configuration File](#121-configuration-file-pro-contextconfigyaml)
  - [12.2 Environment Variable Overrides](#122-environment-variable-overrides)
- [13. Language and Source Extensibility](#13-language-and-source-extensibility)
  - [13.1 Language Extensibility](#131-language-extensibility)
  - [13.2 Source Extensibility](#132-source-extensibility)
- [14. Design Decisions and Rationale](#14-design-decisions-and-rationale)
- [15. Open Questions](#15-open-questions)

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

**The agent chooses which path to use.** For "ChatOpenAI constructor parameters", the fast path is ideal — the agent can call `get-docs` directly without prior resolution. For "how do I implement a custom retry strategy with LangChain", the navigation path gives better results because the agent can reason about which docs pages are relevant with its full conversation context.

Both paths share the same cache and source infrastructure.

### 3.2 Documentation Sources

**All documentation is served as llms.txt format.** The builder system (see `docs/builder/`) normalizes all sources at build time:

| Original Source     | Builder Processing                               | Runtime                                   |
| ------------------- | ------------------------------------------------ | ----------------------------------------- |
| **Native llms.txt** | Validated and indexed as-is                      | Fetched directly from source              |
| **GitHub docs/**    | Converted to llms.txt format (TOC + markdown)    | Fetched from builder-generated llms.txt   |
| **GitHub README**   | Converted to llms.txt format (TOC from headings) | Fetched from builder-generated llms.txt   |
| **Custom sources**  | User provides llms.txt URL in local registry     | Fetched directly from user-configured URL |

**Key insight:** The builder guarantees that every library in the registry has a valid `llmsTxtUrl`. The MCP server is a simple fetch-parse-cache layer with no source-specific logic. This architectural shift moves complexity from runtime (critical path) to build time (weekly background job).

The agent never needs to know or care how the llms.txt was created - whether it's native, builder-generated, or custom. All tools return consistent responses.

### 3.3 The Table of Contents (TOC)

Every resolved library has a table of contents — a structured index of available documentation pages. This is the foundation of the navigation path.

**For libraries with llms.txt**: The TOC is the parsed llms.txt content — a list of pages with titles, URLs, and one-sentence descriptions.

**For libraries without llms.txt**: The TOC is generated from the GitHub repository structure — /docs/ directory listing, README.md sections, wiki pages.

The TOC is returned by `get-library-info`. It is accessed exclusively via tool calls, not as a standalone MCP resource (see D10 for rationale).

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

> As a developer, once a library is identified, the agent should be able to get its documentation index (TOC) and sources.

**Acceptance criteria:**

- Agent calls `get-library-info` with a specific libraryId
- Server returns TOC, available sources, and library metadata
- Agent can request specific TOC sections or the full TOC
- For multi-language libraries, the TOC includes all language-specific sections and the agent navigates to the relevant ones
- TOC contains page titles, URLs, and descriptions suitable for agent navigation

### US-3: Quick Documentation Lookup (Fast Path)

> As a developer, when I ask "what are the parameters for FastAPI's Depends()", the agent should get a focused answer quickly.

**Acceptance criteria:**

- Agent calls `get-docs` with one or more libraries and a topic
- Server searches indexed documentation using BM25
- Returns focused markdown content with source URL, confidence score
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

### US-6: Team Deployment with API Keys

> As a team lead, I want to deploy Pro-Context as a shared service so all team members benefit from cached documentation.

**Acceptance criteria:**

- Server starts in HTTP mode with `transport: http`
- API keys are required for all requests
- Admin CLI (`pro-context-admin`) can create, list, and revoke keys
- Each key has configurable rate limits
- Shared cache means one developer's fetch benefits all others

### US-7: Graceful Degradation

> As a developer, I expect useful responses even when documentation sources are temporarily unavailable.

**Acceptance criteria:**

- If llms.txt fetch fails, server returns recoverable error (agent can retry)
- If fetch fails but cache exists, stale cache is served with a warning
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
      "description": "Optional language filter (e.g., 'python', 'javascript'). Narrows results to DocSources that list this language. Purely a convenience filter — not required."
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

1. Fuzzy-match `query` against curated library registry (in-memory, no network calls)
2. Apply language filter if provided
3. Return all matching libraries ranked by relevance score
4. If no matches found, return empty `results` array

**Registry-only approach**: Pro-Context uses a curated, pre-validated registry of libraries with working documentation. Unknown libraries return "not found" immediately — no runtime package registry queries, no speculative URL probing. This ensures high-confidence matches and eliminates false positives. The registry is updated weekly via automated build script.

**If library not in registry**: Users have two options:

1. **Add to `manual_overrides.yaml`** — Add the library to the builder's manual overrides file and trigger a registry rebuild (see `docs/builder/05-discovery-pipeline.md`)
2. **Submit a PR** — Request addition to the curated registry for all users

**Error cases:**

- Registry load failure → `INTERNAL_ERROR` (should not happen — registry is bundled with package)

---

### 5.2 `get-library-info`

Returns detailed information about a specific library: TOC and documentation sources. This is the entry point to the navigation path.

This tool does not require a prior `resolve-library` call. If the agent already knows the `libraryId` (from a previous session, from user input, from context), it can call `get-library-info` directly.

**Input Schema:**

```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "Canonical library ID (e.g., 'langchain-ai/langchain'). Can be obtained from resolve-library or known ahead of time."
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
    "languages": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Languages this library is available in (informational metadata)"
    },
    "sources": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Documentation source type (always ['llms.txt'] - builder normalizes all sources)"
    },
    "toc": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": { "type": "string", "description": "Page title" },
          "url": {
            "type": "string",
            "description": "Page URL (can be passed to read-page)"
          },
          "description": {
            "type": "string",
            "description": "One-sentence description of the page"
          },
          "section": {
            "type": "string",
            "description": "Section grouping (e.g., 'Getting Started', 'API Reference')"
          }
        }
      },
      "description": "Table of contents — documentation pages available for this library. Use read-page to fetch any of these URLs."
    },
    "availableSections": {
      "type": "array",
      "items": { "type": "string" },
      "description": "All section names in the library's documentation (e.g., ['Getting Started', 'API Reference', 'Concepts']). Always returned, regardless of whether sections filter is applied."
    },
    "filteredBySections": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Which sections were requested, if the sections filter was applied. Omitted when full TOC is returned."
    }
  }
}
```

**Behavior:**

1. Look up `libraryId` in registry (exact match, no fuzzy matching)
2. If not found in registry → return `LIBRARY_NOT_FOUND` error
3. Fetch llms.txt from `library.llmsTxtUrl` (builder guarantees all libraries have valid URLs)
4. Parse llms.txt format to extract TOC entries
5. Extract `availableSections` from TOC entries (unique section names)
6. If `sections` is specified, filter TOC entries to matching sections
7. Cache the TOC
8. Add library to session resolved list
9. Return library metadata + TOC + availableSections

**Performance characteristics:**

- **First query for a library** (cold cache): 2-5 seconds
  - Network fetch of llms.txt or GitHub README
  - Parsing and TOC extraction
  - Cache storage
- **Subsequent queries** (warm cache): <100ms (served from cache)
- **Cache TTL**: 24 hours (default)
- This is by design: on-demand content fetching with aggressive caching ensures both freshness and performance

**Error cases:**

- Library not found in registry → `LIBRARY_NOT_FOUND`
- llms.txt fetch returns 404 → `LLMS_TXT_NOT_FOUND`
- Network error (timeout, connection failed) → `NETWORK_FETCH_FAILED` (recoverable)

---

### 5.3 `get-docs`

The **fast path** tool. Retrieves focused documentation for a specific topic using server-side search (BM25). Best for keyword-heavy queries where the server can match effectively. Supports querying across multiple libraries in a single call.

**Input Schema:**

```json
{
  "type": "object",
  "properties": {
    "libraries": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "libraryId": {
            "type": "string",
            "description": "Canonical library ID"
          }
        },
        "required": ["libraryId"]
      },
      "description": "One or more libraries to search."
    },
    "topic": {
      "type": "string",
      "description": "Documentation topic (e.g., 'chat models', 'streaming', 'dependency injection')"
    },
    "maxTokens": {
      "type": "number",
      "description": "Maximum tokens to return. Default: 5000. Range: 500-10000.",
      "default": 5000,
      "minimum": 500,
      "maximum": 10000
    }
  },
  "required": ["libraries", "topic"]
}
```

**Output Schema:**

```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "Which library this content is from"
    },
    "content": {
      "type": "string",
      "description": "Documentation content in markdown format"
    },
    "source": {
      "type": "string",
      "description": "URL where documentation was fetched from"
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

1. For each library in the `libraries` array:
   a. Check cache (memory → SQLite) for matching (libraryId, topic)
   b. If cached and fresh → use cached content
   c. If cached but stale → use stale content, trigger background refresh
   d. If not cached → fetch documentation from llmsTxtUrl via fetcher, chunk into sections, index with BM25
2. Rank chunks across all specified libraries by topic relevance
3. Select top chunk(s) within `maxTokens` budget
4. Identify related pages from the TOC that the agent might want to read for more context
5. Store results in cache
6. Return content (with `libraryId` attribution) + related pages

**The `relatedPages` field**: This bridges the fast path and the navigation path. If the server-side BM25 search returns content with low confidence (e.g., <0.6), the `relatedPages` give the agent a way to navigate further. The agent sees "here's what I found, but you might also want to read these pages" — and can use `read-page` to explore them.

**Performance characteristics:**

- **First query for a library** (cold cache): 2-5 seconds
  - Network fetch of documentation pages
  - Markdown chunking (heading-aware splitting)
  - BM25 indexing for search
  - Cache storage
- **Subsequent queries** (warm cache): <500ms
  - Served from cache with BM25 ranking
  - No network calls
- **Cache TTL**: 24 hours (default)
- This is by design: incremental indexing avoids upfront bulk processing while ensuring fast repeat queries

**Error cases:**

- Any library in the array not found → `LIBRARY_NOT_FOUND` (identifies which library)
- Topic not found across all specified libraries → `TOPIC_NOT_FOUND` with suggestion to try `search-docs` or browse the TOC via `get-library-info`
- All sources unavailable → serve stale cache (if available) or `SOURCE_UNAVAILABLE`

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
          "libraryId": {
            "type": "string",
            "description": "Which library this result is from"
          },
          "title": { "type": "string", "description": "Section/page title" },
          "snippet": {
            "type": "string",
            "description": "Relevant text excerpt (~100 tokens)"
          },
          "relevance": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "BM25 relevance score (normalized)"
          },
          "url": {
            "type": "string",
            "description": "Page URL — use read-page to fetch full content"
          },
          "section": {
            "type": "string",
            "description": "Documentation section path"
          }
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

1. If `libraryIds` provided, validate each exists in registry
2. If no `libraryIds`, search across all content in the index (only previously fetched/indexed content — not a global search across all registry libraries)
3. Execute BM25 search across indexed chunks (only libraries that have been queried before have indexed content)
4. Rank results by relevance score
5. Return top N results with snippets, URLs, and library attribution
6. Include `searchedLibraries` to show which libraries had indexed content

**Search scope and incremental indexing:**

The `search-docs` tool only searches libraries that have been queried previously via `get-docs` or `read-page`. The search index is built **incrementally** as agents use the server:

- **Day 1**: Agent queries 5 libraries → search index contains 5 libraries
- **Week 1**: Agents query 50 libraries → search index contains 50 libraries
- **Month 1**: Agents query 200+ libraries → search index contains 200+ libraries

The `searchedLibraries` field indicates which libraries had indexed content at query time. This transparency allows agents to understand search coverage.

**Why incremental indexing?**

- Avoids upfront bulk processing (hours to index 1000+ libraries)
- Indexes only what's actually used (80%+ of libraries never queried)
- Keeps index fresh (content indexed on-demand is never stale)
- Storage efficient (only active libraries consume disk space)

**If a library is not indexed yet:**

- Agents should call `get-docs` first (which fetches and indexes the content)
- Then call `search-docs` to search the newly indexed library
- Or use `get-library-info` + `read-page` to navigate directly

**Error cases:**

- Specified library not in registry → `LIBRARY_NOT_FOUND`
- No results → empty results array (not an error)

---

### 5.5 `read-page`

The **navigation path** tool. Fetches a specific documentation page URL and returns its content as markdown. Supports line-based reading for long pages.

**Input Schema:**

```json
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "Documentation page URL to fetch. Must be from a resolved library's TOC, a search result, or a relatedPages entry."
    },
    "maxLines": {
      "type": "number",
      "description": "Maximum number of lines to return. Default: 200.",
      "default": 200,
      "minimum": 1,
      "maximum": 5000
    },
    "offset": {
      "type": "number",
      "description": "Line number to start reading from (0-based). Use this to continue reading a previously truncated page. Default: 0 (start of page).",
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
    "totalLines": {
      "type": "number",
      "description": "Total number of lines in the full page"
    },
    "offset": {
      "type": "number",
      "description": "Line number this response starts from (0-based)"
    },
    "linesReturned": {
      "type": "number",
      "description": "Number of lines in this response"
    },
    "hasMore": {
      "type": "boolean",
      "description": "Whether more content exists beyond this response. If true, call read-page again with offset = offset + linesReturned."
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
3. If cached → serve from cache (applying offset/maxLines)
4. If not cached → fetch the URL, convert to markdown if needed, cache the full page
5. Apply offset: skip to the specified line number
6. Apply maxLines: return up to `maxLines` lines from the offset position
7. Set `hasMore` to true if content remains beyond offset + maxLines
8. Index the page content for BM25 search (background)
9. Return content with line metadata

**Line-based reading**: When a page exceeds `maxLines`, the response includes `hasMore: true` and line metadata. The agent can call `read-page` again with `offset` set to `offset + linesReturned` to continue reading. The server caches the full page on first fetch, so subsequent reads are served from cache without re-fetching. This uses the same deterministic line-based pagination as standard file reading tools.

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
- Offset beyond total line count → empty content with `hasMore: false`

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
  "fetcher": {
    "status": "available",
    "lastSuccess": "2026-02-12T10:00:00Z",
    "successRate": 0.98
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
    {
      "id": "langchain-ai/langchain",
      "name": "LangChain",
      "languages": ["python"]
    },
    { "id": "pydantic/pydantic", "name": "Pydantic", "languages": ["python"] }
  ]
}
```

This resource is updated whenever `get-library-info` is called. It accumulates across the session — libraries are added but never removed.

### 6.3 Why TOC Is a Tool, Not a Resource

The TOC is accessed exclusively via `get-library-info`, not as a standalone MCP resource. This decision was made because:

1. **MCP resource support is inconsistent** across clients. Not all MCP clients handle resources well — some ignore them entirely. Tools are universally supported.
2. **The TOC should not be gated behind prior resolution.** If the agent already knows a `libraryId`, it can call `get-library-info` directly. A resource that only appears after resolution adds unnecessary coupling.
3. **Section filtering is only possible via tool parameters.** A resource has no input parameters — it returns the same data every time. The `sections` filter in `get-library-info` lets the agent request only relevant sections, which matters for large TOCs (e.g., Cloudflare: 2,348 entries across 35 sections).

### 6.4 Session Resource Updates

When the server resolves a library (via `get-library-info`), it:

1. Updates `pro-context://session/resolved-libraries` with the new library
2. Emits a `notifications/resources/list_changed` notification per MCP spec

---

## 7. MCP Prompt Templates

Prompt templates provide reusable workflows that agents can invoke. Updated to reference the current tool set.

### 7.1 `migrate-code`

**Name**: `migrate-code`
**Description**: Generate a migration plan for upgrading library code between versions.

**Arguments:**

| Name          | Required | Description        |
| ------------- | -------- | ------------------ |
| `libraryId`   | Yes      | Library to migrate |
| `fromVersion` | Yes      | Current version    |
| `toVersion`   | Yes      | Target version     |
| `codeSnippet` | No       | Code to migrate    |

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

| Name           | Required | Description                    |
| -------------- | -------- | ------------------------------ |
| `libraryId`    | Yes      | Library where the issue occurs |
| `errorMessage` | Yes      | Error message or description   |
| `codeSnippet`  | No       | Code that produces the error   |

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

| Name        | Required | Description                              |
| ----------- | -------- | ---------------------------------------- |
| `libraryId` | Yes      | Library containing the API               |
| `apiName`   | Yes      | API to explain (class, function, module) |

**Template:**

```
Explain the {apiName} API from {libraryId}.

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

## 8. Documentation Fetching

**Architectural shift**: All documentation sources are normalized to llms.txt format by the builder system (see `docs/builder/` for details). The MCP server is a simple fetch-parse-cache layer with no source-specific logic.

### 8.1 Fetching Flow

```
Request
  │
  ▼
[1] Cache Check ─ Memory LRU → SQLite → miss
  │ hit (fresh)
  ▼
[Return] ──────── Serve from cache
  │ hit (stale)
  ▼
[Return + Refresh] Serve stale + background refresh
  │ miss
  ▼
[2] Fetch ──────── HTTP GET library.llmsTxtUrl
  │                All libraries have valid llms.txt URLs (builder guarantee)
  │ success
  ▼
[Parse + Cache] ─ Parse llms.txt format, store in cache
  │
  ▼
[Return] ──────── Return documentation content
  │ error (404, timeout, network)
  ▼
[Error] ───────── LLMS_TXT_NOT_FOUND or NETWORK_FETCH_FAILED with recoverable flag
```

**Key simplifications:**

- No adapter chain, no fallback logic, no priority ordering
- Every library in registry has a valid `llmsTxtUrl` (guaranteed by builder)
- Builder handles source-specific complexity at build time (GitHub, HTML docs, etc.)
- MCP server only deals with HTTP GET + parse llms.txt format
- Error handling is simple: HTTP errors → ProContextError with recovery info

### 8.2 Custom Documentation Sources

For custom/internal documentation, users can add entries to their local registry override file (`~/.pro-context/custom-libraries.json`):

```json
{
  "libraries": [
    {
      "id": "company/internal-sdk",
      "names": ["internal-sdk"],
      "displayName": "Internal SDK",
      "docsUrl": "https://internal.docs.company.com/sdk",
      "llmsTxtUrl": "https://internal.docs.company.com/sdk/llms.txt"
    }
  ]
}
```

Custom entries are merged with the official registry at startup. They must provide an llms.txt URL (builder cannot process internal/private sources).

---

## 9. Security

### 9.1 URL Allowlist (SSRF Prevention)

`read-page` fetches URLs provided by the agent. To prevent SSRF:

**Default allowlist:**

- `github.com`, `raw.githubusercontent.com` (registry downloads, builder-hosted llms.txt)
- `*.github.io` (GitHub Pages-hosted documentation)
- `*.readthedocs.io`
- Documentation domains from the known-libraries registry
- Domains from any llms.txt file the server has fetched

**Always blocked:**

- Private IPs (127.0.0.1, 10.x, 172.16-31.x, 192.168.x)
- `file://` URLs
- Non-HTTP(S) protocols

**Dynamic allowlist expansion:**
When the server fetches an llms.txt file, all URLs in that file are added to the session allowlist. This means if LangChain's llms.txt links to `docs.langchain.com/some/page`, that URL becomes fetchable via `read-page` — without the user needing to configure it.

Domains from `custom-libraries.json` entries are also added to the allowlist at startup.

### 9.2 Input Validation

All tool inputs are validated with Zod schemas at the MCP boundary:

- `libraryId`: alphanumeric + `-_./`, max 200 chars
- `topic`, `query`: max 500 chars
- `url`: must be valid URL, must pass allowlist check
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

## 10. Language and Registry

### 10.1 Language Handling

Language is **not** a server-side routing concern. The `languages` field on a DocSource is informational metadata — it tells the agent what languages a library supports but the server does not validate or enforce it.

1. **`resolve-library`**: Accepts an optional `language` filter to narrow discovery results (e.g., only return DocSources listing `"python"`). This is a convenience filter, not a requirement.
2. **All other tools**: No language parameter. For multi-language documentation sites (e.g., protobuf.dev), the TOC contains language-specific sections and the agent navigates to the relevant pages based on its own context.

### 10.2 Package Registry Integration

| Language            | Registry | API                                        |
| ------------------- | -------- | ------------------------------------------ |
| Python              | PyPI     | `GET https://pypi.org/pypi/{package}/json` |
| JavaScript (future) | npm      | `GET https://registry.npmjs.org/{package}` |

### 10.3 Documentation Versioning

Pro-Context always serves the latest available documentation. Version-specific documentation is not supported in the current version.

**Rationale**: Research shows that version-specific llms.txt files are extremely rare in the Python ecosystem. Pydantic only publishes at `/latest/`. Django, SQLAlchemy, and most other libraries serve a single current version. Only a handful of JS frameworks (Next.js) support per-version llms.txt. The complexity of version resolution (URL patterns, fallback logic, version-specific caching) is not justified by the ecosystem's current state. This may be revisited when llms.txt versioning matures.

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

| Code                   | Trigger                             | Suggestion                                                                         |
| ---------------------- | ----------------------------------- | ---------------------------------------------------------------------------------- |
| `LIBRARY_NOT_FOUND`    | Unknown library ID                  | Did you mean '{suggestion}'? Use resolve-library to discover libraries.            |
| `TOPIC_NOT_FOUND`      | BM25 search finds nothing for topic | Try search-docs for broader results, or browse the TOC via get-library-info.       |
| `PAGE_NOT_FOUND`       | read-page URL returns 404           | Check the URL or use get-library-info to refresh the TOC.                          |
| `URL_NOT_ALLOWED`      | read-page URL fails allowlist check | Resolve the library first with get-library-info, or add the domain to your config. |
| `SOURCE_UNAVAILABLE`   | llms.txt fetch fails, no cache      | Try again later.                                                                   |
| `REGISTRY_TIMEOUT`     | PyPI/npm unreachable                | Try again or specify the library ID directly.                                      |
| `RATE_LIMITED`         | Token bucket exhausted              | Try again after {retryAfter} seconds.                                              |
| `INDEXING_IN_PROGRESS` | Docs being fetched/indexed          | Try again in {retryAfter} seconds.                                                 |
| `AUTH_REQUIRED`        | Missing API key (HTTP mode)         | Provide API key via Authorization header.                                          |
| `AUTH_INVALID`         | Bad/revoked API key                 | Check your API key.                                                                |
| `INVALID_CONTENT`      | Fetched URL is not documentation    | URL does not appear to contain documentation.                                      |
| `INTERNAL_ERROR`       | Unexpected server error             | This has been logged. Try again.                                                   |

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
  transport: stdio # "stdio" | "http"
  port: 3100 # HTTP port (http transport only)
  host: "127.0.0.1" # HTTP bind address

# Cache
cache:
  directory: "~/.pro-context/cache"
  maxMemoryMB: 100
  maxMemoryEntries: 500
  defaultTTLHours: 24
  cleanupIntervalMinutes: 60

# Infrastructure backends (default: all embedded, no external services)
backends:
  memoryCache: cachetools       # or "redis"
  persistentCache: sqlite       # or "postgresql"
  search: sqlite_fts5           # or "postgresql_fts"
  rateLimiter: memory           # or "redis"
  sessionStore: sqlite          # or "redis"
  # redisUrl: "redis://localhost:6379/0"
  # postgresqlUrl: "postgresql://user:pass@localhost/procontext"

# Per-library overrides
libraryOverrides:
  langchain:
    docsUrl: "https://docs.langchain.com"
    ttlHours: 12
  fastapi:
    docsUrl: "https://fastapi.tiangolo.com"
    ttlHours: 48

# Rate limiting (HTTP mode only)
rateLimit:
  maxRequestsPerMinute: 60
  burstSize: 10

# Logging
logging:
  level: "info" # "debug" | "info" | "warn" | "error"
  format: "json" # "json" | "pretty"

# Security (HTTP mode only)
security:
  cors:
    origins: ["*"]
  urlAllowlist: [] # Additional allowed domains for read-page
```

### 12.2 Environment Variable Overrides

| Config Key             | Environment Variable       | Example                     |
| ---------------------- | -------------------------- | --------------------------- |
| `server.transport`     | `PRO_CONTEXT_TRANSPORT`    | `http`                      |
| `server.port`          | `PRO_CONTEXT_PORT`         | `3100`                      |
| `cache.directory`      | `PRO_CONTEXT_CACHE_DIR`    | `/data/cache`               |
| `backends.redis_url`   | `PRO_CONTEXT_REDIS_URL`    | `redis://localhost:6379/0`  |
| `backends.postgresql_url` | `PRO_CONTEXT_POSTGRESQL_URL` | `postgresql://user:pass@host/db` |
| `logging.level`        | `PRO_CONTEXT_LOG_LEVEL`    | `debug`                     |
| —                      | `PRO_CONTEXT_DEBUG=true`   | Shorthand for `debug` level |

---

## 13. Language and Source Extensibility

### 13.1 Language Extensibility

Pro-Context is language-agnostic at the data model level. Language is informational metadata on DocSource entries, not a routing or validation concern. Language-specific behavior is isolated in registry resolvers (which handle version resolution via language-specific package registries).

**Current**: Python (PyPI registry)
**Future**: JavaScript/TypeScript (npm), Rust (crates.io), Go (pkg.go.dev)

Adding a new language requires:

1. A registry resolver (e.g., `npm-resolver.ts`) that implements version resolution for the language's package registry
2. Builder support for the language's package registry (e.g., npm scraping)
3. Known-library entries with the new language in their `languages` array
4. No changes to fetcher, cache, search, tools, or config — these layers are language-agnostic by design

### 13.2 Source Extensibility

New documentation sources are added in the builder system (see `docs/builder/`):

- Builder discovers packages from registries (PyPI, npm, etc.)
- Builder probes for native llms.txt files (10+ URL patterns)
- Builder generates llms.txt for sources without native support (GitHub README/docs, HTML docs sites)
- Builder publishes registry with llmsTxtUrl for every entry

**Current builder sources:**

- Native llms.txt (Mintlify, Fern, manually created)
- GitHub README → llms.txt
- GitHub docs/ → llms.txt

**Future builder sources:**

- HTML documentation sites (ReadTheDocs, Sphinx, Jekyll) → llms.txt
- API documentation generators (Swagger, OpenAPI) → llms.txt
- PyPI long-description → llms.txt

---

## 14. Design Decisions and Rationale

### D1: `read-page` replaces `get-examples`

**Decision**: Dropped the `get-examples` tool in favor of `read-page`.

**Rationale**: `get-examples` was a specialized content extraction tool — it fetched docs, found code blocks, and returned them. But modern AI agents are excellent at extracting code examples from documentation they read. What agents cannot do without a tool is navigate to a specific URL. `read-page` enables the entire navigation paradigm (the key insight from the competitive analysis), while `get-examples` solved a problem the agent can solve itself.

### D2: `resolve-library` is pure discovery, `get-library-info` provides depth

**Decision**: Split the original `resolve-library` (which returned metadata + TOC) into two tools: `resolve-library` for discovery and `get-library-info` for detail retrieval. `get-library-info` does not require a prior `resolve-library` call — the agent can call it directly if it already knows the `libraryId`.

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

### D7: `read-page` uses line-based pagination

**Decision**: `read-page` accepts `offset` (line number) and `maxLines` parameters for progressive reading of long pages, with the server caching the full page on first fetch.

**Rationale**: Some documentation pages are very long (thousands of lines). Without pagination, the agent would miss later portions entirely. Line-based pagination is deterministic (line 100 is always line 100), human-readable, and uses natural boundaries that don't split mid-word or mid-code-block. This is the same pattern used by standard file reading tools. The server caches the full page on first fetch, so subsequent offset reads are served from cache without re-fetching. Token estimation was considered but rejected — token counts are approximate (model-specific, dependent on content type), opaque to the client, and solve a problem (context window budgeting) at the wrong layer. The agent manages its own context budget by adjusting `maxLines` based on what it receives.

### D8: `get-docs` accepts multiple libraries

**Decision**: `get-docs` takes a `libraries` array instead of a single `libraryId`.

**Rationale**: Developers often work with related libraries simultaneously (e.g., LangChain + Pydantic, FastAPI + SQLAlchemy). When the agent asks "how do I do X", the answer might involve multiple libraries. Accepting an array lets the agent fetch relevant content from several libraries in a single call, with results ranked across all of them.

### D9: `search-docs` supports cross-library search

**Decision**: `search-docs` does not require a library ID. It can search across all indexed content, optionally scoped to specific libraries.

**Rationale**: Developers often don't know which library implements a concept. "How do I handle retries?" could be in LangChain, httpx, or tenacity. Cross-library search lets the agent find the right page without knowing the library upfront. The important caveat is that this searches only previously indexed content — it's not a global search engine. The `searchedLibraries` field in the response makes this explicit so the agent knows the scope.

### D10: TOC is a tool, not a resource

**Decision**: The TOC is accessed via `get-library-info` only, not as a standalone MCP resource.

**Rationale**: MCP resource support varies across clients — some ignore resources entirely. Tools are universally supported. Additionally, a resource has no input parameters, so section filtering is impossible. The `sections` parameter in `get-library-info` lets agents request only relevant TOC sections, which is important for large libraries (Cloudflare has 35 sections with 2,348 entries). Making TOC a tool keeps the interface consistent and functional across all MCP clients.

### D11: No `llms-full.txt` support

**Decision**: Pro-Context does not fetch or use `llms-full.txt` files.

**Rationale**: `llms-full.txt` can be enormous (Cloudflare: 3.7M tokens). It doesn't fit in a context window and must be chunked/indexed entirely before any search is possible. The per-page pattern (llms.txt index + read individual pages) is more aligned with the agent navigation paradigm and more efficient: pages are fetched and indexed on demand as the agent reads them. BM25 search quality improves organically as more pages are accessed. The upfront cost of downloading and indexing a multi-megabyte file for a single query is not justified.

### D12: Pre-built registry vs runtime adapters

**Decision**: All documentation source discovery and normalization happens at build time in the builder system (see `docs/builder/`). The MCP server is a simple fetch-parse-cache layer with no runtime adapters.

**Rationale**:

- **Simplicity**: MCP server becomes a single code path (HTTP GET + parse llms.txt), not 3+ adapter implementations
- **Performance**: No source-specific logic at runtime, no fallback chains, no adapter priority evaluation
- **Reliability**: All sources are pre-validated at build time, no runtime discovery failures
- **Separation**: Data engineering (builder, batch, weekly runs) vs data serving (MCP server, real-time, low latency)
- **Scalability**: Builder runs on GitHub Actions, handles all complexity (PyPI scraping, llms.txt probing, GitHub extraction, normalization)
- **Coverage**: Builder can generate llms.txt for sources without native support (GitHub README/docs → llms.txt format)
- **Guarantee**: Every library in registry has a valid `llmsTxtUrl` - no `LLMS_TXT_NOT_AVAILABLE` errors at runtime

This architectural shift moves complexity from the critical path (user query) to the build pipeline (weekly background job). The MCP server trusts the builder's output and focuses on fast, reliable delivery.

---

## 15. Open Questions

### Q1: How should the known-libraries registry be structured and maintained?

The registry maps library names to metadata (docs URL, GitHub repo, supported languages, URL patterns for versioned docs). This is a critical data structure — the quality of `resolve-library` depends on it. Should this be a static JSON file shipped with Pro-Context? A community-maintained repository? Auto-populated from PyPI metadata?

**Lean**: Start with a curated JSON file covering the top 200 Python libraries. Allow community contributions via PRs. Augment with live PyPI lookups for libraries not in the registry.

### Q2: How should `get-docs` handle a library it hasn't seen before?

`get-docs` accepts a `libraries` array and can trigger JIT fetching if a library hasn't been indexed yet. Should it silently index on first encounter, or return `INDEXING_IN_PROGRESS` and ask the agent to retry?

**Lean**: JIT fetch silently. The agent called `get-docs` expecting content — making it retry adds friction to the fast path. If the first fetch is slow (a few seconds), that's acceptable for the first call. Subsequent calls are fast from cache.

### Q3: ~~What is the right token estimation strategy for offset/limit?~~

**Resolved**: `read-page` uses line-based pagination (`offset` as line number, `maxLines` as line count), not token-based. Token estimation is no longer needed for pagination. The `estimate_tokens` utility (chars/4) remains for BM25 chunk sizing in the search engine (Section 7 of the technical spec) — a different concern from page reading.
