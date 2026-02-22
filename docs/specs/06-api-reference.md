# Pro-Context: MCP API Reference

> **Document**: 06-api-reference.md
> **Status**: Draft v1
> **Last Updated**: 2026-02-22
> **MCP Protocol Version**: 2025-11-25
> **Depends on**: 02-functional-spec.md, 03-technical-spec.md

This document is the single source of truth for Pro-Context's external interface. It defines every tool, resource, and prompt template using the exact wire formats specified by the [Model Context Protocol v2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/index.md).

---

## Table of Contents

- [1. Server Identity and Capabilities](#1-server-identity-and-capabilities)
  - [1.1 Initialization Handshake](#11-initialization-handshake)
  - [1.2 Declared Capabilities](#12-declared-capabilities)
- [2. Transports](#2-transports)
  - [2.1 stdio Transport](#21-stdio-transport)
  - [2.2 Streamable HTTP Transport](#22-streamable-http-transport)
  - [2.3 Session Management](#23-session-management)
- [3. Tools](#3-tools)
  - [3.1 resolve-library](#31-resolve-library)
  - [3.2 get-library-info](#32-get-library-info)
  - [3.3 get-docs](#33-get-docs)
  - [3.4 search-docs](#34-search-docs)
  - [3.5 read-page](#35-read-page)
- [4. Resources](#4-resources)
  - [4.1 pro-context://health](#41-pro-contexthealth)
  - [4.2 pro-context://session/resolved-libraries](#42-pro-contextsessionresolved-libraries)
- [5. Prompt Templates](#5-prompt-templates)
  - [5.1 migrate-code](#51-migrate-code)
  - [5.2 debug-with-docs](#52-debug-with-docs)
  - [5.3 explain-api](#53-explain-api)
- [6. Error Handling](#6-error-handling)
  - [6.1 Protocol Errors](#61-protocol-errors)
  - [6.2 Tool Execution Errors](#62-tool-execution-errors)
  - [6.3 Error Code Catalog](#63-error-code-catalog)
- [7. HTTP Mode API](#7-http-mode-api)
  - [7.1 Authentication](#71-authentication)
  - [7.2 Rate Limiting](#72-rate-limiting)
  - [7.3 CORS](#73-cors)
- [8. Versioning and Compatibility](#8-versioning-and-compatibility)
  - [8.1 Protocol Version](#81-protocol-version)
  - [8.2 Server Version](#82-server-version)
  - [8.3 Registry Version](#83-registry-version)
  - [8.4 Breaking Change Policy](#84-breaking-change-policy)
  - [8.5 Deprecation Policy](#85-deprecation-policy)

---

## 1. Server Identity and Capabilities

### 1.1 Initialization Handshake

Per the MCP lifecycle spec, the client sends an `initialize` request and the server responds with its identity and capabilities. The server then waits for the `initialized` notification before accepting further requests.

**Server `InitializeResult`:**

```json
{
  "protocolVersion": "2025-11-25",
  "capabilities": {
    "tools": {
      "listChanged": false
    },
    "resources": {
      "subscribe": false,
      "listChanged": true
    },
    "prompts": {
      "listChanged": false
    },
    "logging": {}
  },
  "serverInfo": {
    "name": "pro-context",
    "title": "Pro-Context Documentation Server",
    "version": "0.1.0",
    "description": "MCP server providing AI coding agents with accurate, up-to-date library documentation"
  },
  "instructions": "Pro-Context provides library documentation via 5 tools. Start with resolve-library to discover libraries, or call get-library-info directly if you know the libraryId. Use get-docs for quick topic lookups (fast path) or get-library-info + read-page to browse documentation (navigation path)."
}
```

### 1.2 Declared Capabilities

| Capability | Sub-capability | Value | Rationale |
|------------|---------------|-------|-----------|
| `tools` | `listChanged` | `false` | Tool set is static — all 5 tools are always available. |
| `resources` | `subscribe` | `false` | Resources are read-only snapshots; subscriptions are not needed. |
| `resources` | `listChanged` | `true` | The `session/resolved-libraries` resource list updates as libraries are resolved. |
| `prompts` | `listChanged` | `false` | Prompt templates are static — all 3 are always available. |
| `logging` | — | `{}` | Server emits structured log messages via `notifications/message`. |

---

## 2. Transports

### 2.1 stdio Transport

**Use case**: Individual developer running Pro-Context locally.

The client launches `pro-context` as a subprocess. JSON-RPC messages are exchanged over stdin/stdout, newline-delimited. The server writes structured logs to stderr.

```
$ pro-context                    # Starts stdio server
$ pro-context --config ./my.yaml # Custom config path
```

- One client connection per process.
- Session lifetime = process lifetime.
- `session_libraries` table is cleared on startup.

### 2.2 Streamable HTTP Transport

**Use case**: Team deployment as a shared service.

The server exposes a single MCP endpoint (default: `http://127.0.0.1:3100/mcp`) that accepts both POST and GET requests per the MCP Streamable HTTP transport specification.

- **POST**: Client sends JSON-RPC requests and notifications. Server responds with `application/json` or `text/event-stream` (SSE).
- **GET**: Client opens an SSE stream for server-initiated messages (notifications, requests).
- Multiple concurrent client connections supported.
- Shared documentation cache across all connections.
- API key authentication required (see [Section 7.1](#71-authentication)).

**Required headers on all requests (after initialization):**

| Header | Value | Required |
|--------|-------|----------|
| `MCP-Protocol-Version` | `2025-11-25` | Yes (MCP spec) |
| `MCP-Session-Id` | Session ID from init response | Yes (if server assigned one) |
| `Authorization` | `Bearer pc_...` | Yes (HTTP mode) |
| `Accept` | `application/json, text/event-stream` | Yes (POST) |
| `Accept` | `text/event-stream` | Yes (GET) |

### 2.3 Session Management

In Streamable HTTP mode, the server assigns an `MCP-Session-Id` in the HTTP response containing the `InitializeResult`. The session ID is a cryptographically secure random string (e.g., `secrets.token_urlsafe(32)`).

- Client must include `MCP-Session-Id` on all subsequent requests.
- Server responds with HTTP 400 if the header is missing (after init).
- Server responds with HTTP 404 if the session has expired or been terminated.
- Client may terminate the session by sending HTTP DELETE to the MCP endpoint with the `MCP-Session-Id` header.

---

## 3. Tools

All 5 tools are registered via `tools/list` and invoked via `tools/call`. Tool results use the MCP content array format. Errors are returned as tool execution errors (`isError: true`), not JSON-RPC protocol errors.

### 3.1 `resolve-library`

Discovers libraries matching a natural language query. Pure discovery — does not fetch documentation.

#### Tool Definition (returned by `tools/list`)

```json
{
  "name": "resolve-library",
  "title": "Resolve Library",
  "description": "Discovers libraries matching a natural language query. Returns ranked matches with IDs, names, descriptions, and supported languages. Handles typos via fuzzy matching. Does not fetch documentation — use get-library-info or get-docs for content.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Library name or natural language query (e.g., 'langchain', 'python fastapi', 'pydantic v2')",
        "maxLength": 500
      },
      "language": {
        "type": "string",
        "description": "Optional language filter (e.g., 'python', 'javascript'). Narrows results to libraries listing this language."
      }
    },
    "required": ["query"],
    "additionalProperties": false
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "results": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "libraryId": { "type": "string" },
            "name": { "type": "string" },
            "description": { "type": "string" },
            "languages": { "type": "array", "items": { "type": "string" } },
            "relevance": { "type": "number", "minimum": 0, "maximum": 1 }
          },
          "required": ["libraryId", "name", "description", "languages", "relevance"]
        }
      }
    },
    "required": ["results"]
  },
  "annotations": {
    "title": "Library Discovery",
    "readOnlyHint": true,
    "openWorldHint": false
  }
}
```

#### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "resolve-library",
    "arguments": {
      "query": "langchan",
      "language": "python"
    }
  }
}
```

#### Example Success Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"results\":[{\"libraryId\":\"langchain-ai/langchain\",\"name\":\"LangChain\",\"description\":\"Framework for developing applications powered by language models\",\"languages\":[\"python\"],\"relevance\":0.92}]}"
      }
    ],
    "structuredContent": {
      "results": [
        {
          "libraryId": "langchain-ai/langchain",
          "name": "LangChain",
          "description": "Framework for developing applications powered by language models",
          "languages": ["python"],
          "relevance": 0.92
        }
      ]
    }
  }
}
```

#### Example Error Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"code\":\"INTERNAL_ERROR\",\"message\":\"Failed to load library registry\",\"recoverable\":false,\"suggestion\":\"This has been logged. Try again.\"}"
      }
    ],
    "isError": true
  }
}
```

---

### 3.2 `get-library-info`

Returns library metadata and documentation TOC (table of contents). Entry point for the navigation path. Does not require a prior `resolve-library` call.

#### Tool Definition

```json
{
  "name": "get-library-info",
  "title": "Get Library Info",
  "description": "Returns detailed information about a library including its documentation table of contents (TOC). Use the TOC to browse available pages, then call read-page to fetch content. Supports section filtering for large TOCs. Does not require prior resolve-library call — pass libraryId directly if known.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "libraryId": {
        "type": "string",
        "description": "Canonical library ID (e.g., 'langchain-ai/langchain'). Obtained from resolve-library or known ahead of time.",
        "maxLength": 200,
        "pattern": "^[a-zA-Z0-9._/-]+$"
      },
      "sections": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Optional: only return TOC entries from these sections (e.g., ['Getting Started', 'API Reference']). If omitted, returns the full TOC."
      }
    },
    "required": ["libraryId"],
    "additionalProperties": false
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "libraryId": { "type": "string" },
      "name": { "type": "string" },
      "languages": { "type": "array", "items": { "type": "string" } },
      "sources": { "type": "array", "items": { "type": "string" } },
      "toc": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "title": { "type": "string" },
            "url": { "type": "string", "format": "uri" },
            "description": { "type": "string" },
            "section": { "type": "string" }
          },
          "required": ["title", "url"]
        }
      },
      "availableSections": { "type": "array", "items": { "type": "string" } },
      "filteredBySections": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["libraryId", "name", "languages", "sources", "toc", "availableSections"]
  },
  "annotations": {
    "title": "Library Info & TOC",
    "readOnlyHint": true,
    "openWorldHint": false
  }
}
```

#### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get-library-info",
    "arguments": {
      "libraryId": "langchain-ai/langchain",
      "sections": ["Getting Started"]
    }
  }
}
```

#### Example Success Response

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"libraryId\":\"langchain-ai/langchain\",\"name\":\"LangChain\",\"languages\":[\"python\"],\"sources\":[\"llms.txt\"],\"toc\":[{\"title\":\"Introduction\",\"url\":\"https://docs.langchain.com/docs/introduction\",\"description\":\"Overview of LangChain framework\",\"section\":\"Getting Started\"},{\"title\":\"Quickstart\",\"url\":\"https://docs.langchain.com/docs/quickstart\",\"description\":\"Get up and running in 5 minutes\",\"section\":\"Getting Started\"}],\"availableSections\":[\"Getting Started\",\"Concepts\",\"How-to Guides\",\"API Reference\"],\"filteredBySections\":[\"Getting Started\"]}"
      }
    ],
    "structuredContent": {
      "libraryId": "langchain-ai/langchain",
      "name": "LangChain",
      "languages": ["python"],
      "sources": ["llms.txt"],
      "toc": [
        {
          "title": "Introduction",
          "url": "https://docs.langchain.com/docs/introduction",
          "description": "Overview of LangChain framework",
          "section": "Getting Started"
        },
        {
          "title": "Quickstart",
          "url": "https://docs.langchain.com/docs/quickstart",
          "description": "Get up and running in 5 minutes",
          "section": "Getting Started"
        }
      ],
      "availableSections": ["Getting Started", "Concepts", "How-to Guides", "API Reference"],
      "filteredBySections": ["Getting Started"]
    }
  }
}
```

#### Side Effects

- Fetches and caches the library's llms.txt (if not cached).
- Adds the library to the session resolved list.
- Emits `notifications/resources/list_changed` (the `session/resolved-libraries` resource is updated).

---

### 3.3 `get-docs`

The **fast path** tool. Retrieves focused documentation for a topic using server-side BM25 search. Supports multi-library queries.

#### Tool Definition

```json
{
  "name": "get-docs",
  "title": "Get Documentation",
  "description": "Retrieves focused documentation for a specific topic using BM25 search. Best for keyword-heavy queries. Supports querying multiple libraries in a single call. Returns content, confidence score, and related pages for further browsing.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "libraries": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "libraryId": {
              "type": "string",
              "description": "Canonical library ID",
              "maxLength": 200
            }
          },
          "required": ["libraryId"]
        },
        "description": "One or more libraries to search.",
        "minItems": 1
      },
      "topic": {
        "type": "string",
        "description": "Documentation topic (e.g., 'chat models', 'streaming', 'dependency injection')",
        "maxLength": 500
      },
      "maxTokens": {
        "type": "number",
        "description": "Maximum tokens to return.",
        "default": 5000,
        "minimum": 500,
        "maximum": 10000
      }
    },
    "required": ["libraries", "topic"],
    "additionalProperties": false
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "libraryId": { "type": "string" },
      "content": { "type": "string" },
      "source": { "type": "string", "format": "uri" },
      "lastUpdated": { "type": "string", "format": "date-time" },
      "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
      "cached": { "type": "boolean" },
      "stale": { "type": "boolean" },
      "relatedPages": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "title": { "type": "string" },
            "url": { "type": "string", "format": "uri" },
            "description": { "type": "string" }
          },
          "required": ["title", "url"]
        }
      }
    },
    "required": ["libraryId", "content", "source", "confidence", "cached", "stale"]
  },
  "annotations": {
    "title": "Quick Doc Lookup",
    "readOnlyHint": true,
    "openWorldHint": false
  }
}
```

#### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get-docs",
    "arguments": {
      "libraries": [{ "libraryId": "langchain-ai/langchain" }],
      "topic": "chat models",
      "maxTokens": 3000
    }
  }
}
```

#### Example Success Response

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"libraryId\":\"langchain-ai/langchain\",\"content\":\"# Chat Models\\n\\nChat models in LangChain are language models that use chat messages as inputs and return chat messages as outputs...\\n\",\"source\":\"https://docs.langchain.com/docs/concepts/chat_models\",\"lastUpdated\":\"2026-02-20T08:00:00Z\",\"confidence\":0.87,\"cached\":false,\"stale\":false,\"relatedPages\":[{\"title\":\"Chat Model Integrations\",\"url\":\"https://docs.langchain.com/docs/integrations/chat\",\"description\":\"Available chat model providers\"}]}"
      }
    ],
    "structuredContent": {
      "libraryId": "langchain-ai/langchain",
      "content": "# Chat Models\n\nChat models in LangChain are language models that use chat messages as inputs and return chat messages as outputs...\n",
      "source": "https://docs.langchain.com/docs/concepts/chat_models",
      "lastUpdated": "2026-02-20T08:00:00Z",
      "confidence": 0.87,
      "cached": false,
      "stale": false,
      "relatedPages": [
        {
          "title": "Chat Model Integrations",
          "url": "https://docs.langchain.com/docs/integrations/chat",
          "description": "Available chat model providers"
        }
      ]
    }
  }
}
```

#### Side Effects

- Fetches, chunks, and indexes library documentation (if not cached).
- Stores results in both memory and persistent caches.
- Background refresh triggered if cache entry is stale.

---

### 3.4 `search-docs`

Searches across indexed documentation. Returns ranked results with snippets and URLs — use `read-page` to fetch full content.

#### Tool Definition

```json
{
  "name": "search-docs",
  "title": "Search Documentation",
  "description": "Searches across previously indexed documentation using BM25. Returns ranked results with snippets and URLs. Optionally scoped to specific libraries. Only searches content that has been previously fetched via get-docs or read-page. Use read-page to get full content for any result.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search query (e.g., 'retry logic', 'error handling middleware')",
        "maxLength": 500
      },
      "libraryIds": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Optional: restrict search to these libraries. If omitted, searches all indexed content."
      },
      "maxResults": {
        "type": "number",
        "description": "Maximum number of results.",
        "default": 5,
        "minimum": 1,
        "maximum": 20
      }
    },
    "required": ["query"],
    "additionalProperties": false
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "results": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "libraryId": { "type": "string" },
            "title": { "type": "string" },
            "snippet": { "type": "string" },
            "relevance": { "type": "number", "minimum": 0, "maximum": 1 },
            "url": { "type": "string", "format": "uri" },
            "section": { "type": "string" }
          },
          "required": ["libraryId", "title", "snippet", "relevance", "url"]
        }
      },
      "totalMatches": { "type": "number" },
      "searchedLibraries": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["results", "totalMatches", "searchedLibraries"]
  },
  "annotations": {
    "title": "Search Docs",
    "readOnlyHint": true,
    "openWorldHint": false
  }
}
```

#### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "search-docs",
    "arguments": {
      "query": "retry logic",
      "libraryIds": ["langchain-ai/langchain"],
      "maxResults": 3
    }
  }
}
```

#### Example Success Response

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"results\":[{\"libraryId\":\"langchain-ai/langchain\",\"title\":\"Retry Strategies\",\"snippet\":\"LangChain provides built-in retry logic for LLM calls. Configure max_retries and retry_delay on any LLM class...\",\"relevance\":0.81,\"url\":\"https://docs.langchain.com/docs/concepts/retries\",\"section\":\"Concepts\"}],\"totalMatches\":7,\"searchedLibraries\":[\"langchain-ai/langchain\"]}"
      }
    ],
    "structuredContent": {
      "results": [
        {
          "libraryId": "langchain-ai/langchain",
          "title": "Retry Strategies",
          "snippet": "LangChain provides built-in retry logic for LLM calls. Configure max_retries and retry_delay on any LLM class...",
          "relevance": 0.81,
          "url": "https://docs.langchain.com/docs/concepts/retries",
          "section": "Concepts"
        }
      ],
      "totalMatches": 7,
      "searchedLibraries": ["langchain-ai/langchain"]
    }
  }
}
```

---

### 3.5 `read-page`

The **navigation path** tool. Fetches a specific documentation page and returns its content as markdown. Supports line-based pagination for long pages.

#### Tool Definition

```json
{
  "name": "read-page",
  "title": "Read Documentation Page",
  "description": "Fetches a specific documentation page URL and returns clean markdown content. Supports line-based pagination for long pages — use offset and maxLines to paginate. URLs must come from a resolved TOC, search result, relatedPages entry, or configured allowlist.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "url": {
        "type": "string",
        "format": "uri",
        "description": "Documentation page URL to fetch. Must be from a resolved library's TOC, a search result, or a relatedPages entry."
      },
      "maxLines": {
        "type": "number",
        "description": "Maximum number of lines to return.",
        "default": 200,
        "minimum": 1,
        "maximum": 5000
      },
      "offset": {
        "type": "number",
        "description": "Line number to start reading from (0-based). Use to continue reading a truncated page. Set to previous offset + linesReturned.",
        "default": 0,
        "minimum": 0
      }
    },
    "required": ["url"],
    "additionalProperties": false
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "content": { "type": "string" },
      "title": { "type": "string" },
      "url": { "type": "string", "format": "uri" },
      "totalLines": { "type": "number" },
      "offset": { "type": "number" },
      "linesReturned": { "type": "number" },
      "hasMore": { "type": "boolean" },
      "cached": { "type": "boolean" }
    },
    "required": ["content", "title", "url", "totalLines", "offset", "linesReturned", "hasMore", "cached"]
  },
  "annotations": {
    "title": "Read Page",
    "readOnlyHint": true,
    "openWorldHint": false
  }
}
```

#### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "read-page",
    "arguments": {
      "url": "https://docs.langchain.com/docs/concepts/chat_models",
      "maxLines": 200,
      "offset": 0
    }
  }
}
```

#### Example Success Response

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"content\":\"# Chat Models\\n\\nChat models are a core component of LangChain...\\n\",\"title\":\"Chat Models\",\"url\":\"https://docs.langchain.com/docs/concepts/chat_models\",\"totalLines\":450,\"offset\":0,\"linesReturned\":200,\"hasMore\":true,\"cached\":false}"
      }
    ],
    "structuredContent": {
      "content": "# Chat Models\n\nChat models are a core component of LangChain...\n",
      "title": "Chat Models",
      "url": "https://docs.langchain.com/docs/concepts/chat_models",
      "totalLines": 450,
      "offset": 0,
      "linesReturned": 200,
      "hasMore": true,
      "cached": false
    }
  }
}
```

#### Example Continuation Request

When `hasMore` is `true`, the client calls again with `offset` = previous `offset` + `linesReturned`:

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "tools/call",
  "params": {
    "name": "read-page",
    "arguments": {
      "url": "https://docs.langchain.com/docs/concepts/chat_models",
      "maxLines": 200,
      "offset": 200
    }
  }
}
```

#### Side Effects

- Fetches and caches the full page (if not cached). Subsequent line-offset reads are served from cache.
- Indexes page content for BM25 search (background).
- URL must pass the allowlist check (see Technical Spec Section 12.2). Redirect targets are also validated.

---

## 4. Resources

Resources are listed via `resources/list` and read via `resources/read`. Pro-Context uses a custom URI scheme (`pro-context://`) for its resources.

### 4.1 `pro-context://health`

Server health and cache status. Available in both stdio and HTTP modes.

#### Resource Definition (returned by `resources/list`)

```json
{
  "uri": "pro-context://health",
  "name": "health",
  "title": "Server Health",
  "description": "Server health status, cache statistics, and fetcher availability",
  "mimeType": "application/json",
  "annotations": {
    "audience": ["user"],
    "priority": 0.3
  }
}
```

#### Read Response (`resources/read`)

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "result": {
    "contents": [
      {
        "uri": "pro-context://health",
        "mimeType": "application/json",
        "text": "{\"status\":\"healthy\",\"uptime\":3600,\"cache\":{\"memoryEntries\":142,\"persistentEntries\":1024,\"hitRate\":0.87},\"fetcher\":{\"status\":\"available\",\"lastSuccess\":\"2026-02-20T10:30:00Z\",\"errorCount\":0,\"successRate\":0.98},\"version\":\"0.1.0\"}"
      }
    ]
  }
}
```

**Status values:**

| Status | Condition |
|--------|-----------|
| `healthy` | Fetcher working, cache functional, hit rate > 80% |
| `degraded` | Fetcher experiencing errors, or cache hit rate < 50% |
| `unhealthy` | Fetcher completely failing, or cache corrupted |

### 4.2 `pro-context://session/resolved-libraries`

Libraries resolved in the current session. Accumulates as `get-library-info` is called — libraries are added, never removed within a session.

#### Resource Definition

```json
{
  "uri": "pro-context://session/resolved-libraries",
  "name": "resolved-libraries",
  "title": "Session Resolved Libraries",
  "description": "Libraries resolved in the current session. Updated each time get-library-info is called.",
  "mimeType": "application/json",
  "annotations": {
    "audience": ["assistant"],
    "priority": 0.5
  }
}
```

#### Read Response

```json
{
  "jsonrpc": "2.0",
  "id": 11,
  "result": {
    "contents": [
      {
        "uri": "pro-context://session/resolved-libraries",
        "mimeType": "application/json",
        "text": "{\"libraries\":[{\"id\":\"langchain-ai/langchain\",\"name\":\"LangChain\",\"languages\":[\"python\"]},{\"id\":\"pydantic/pydantic\",\"name\":\"Pydantic\",\"languages\":[\"python\"]}]}"
      }
    ]
  }
}
```

#### Update Notification

When `get-library-info` resolves a new library, the server emits:

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/resources/list_changed"
}
```

The client can then re-read the resource to get the updated list.

---

## 5. Prompt Templates

Prompts are listed via `prompts/list` and retrieved via `prompts/get`. They return pre-built messages that guide the agent through multi-step documentation workflows.

### 5.1 `migrate-code`

Generates a migration plan for upgrading library code between versions.

#### Prompt Definition (returned by `prompts/list`)

```json
{
  "name": "migrate-code",
  "title": "Migrate Code Between Versions",
  "description": "Generate a migration plan for upgrading library code between versions. Guides the agent to find changelogs and migration guides, then produce a step-by-step migration.",
  "arguments": [
    { "name": "libraryId", "description": "Library to migrate", "required": true },
    { "name": "fromVersion", "description": "Current version", "required": true },
    { "name": "toVersion", "description": "Target version", "required": true },
    { "name": "codeSnippet", "description": "Code to migrate (optional)", "required": false }
  ]
}
```

#### Get Response (`prompts/get`)

```json
{
  "jsonrpc": "2.0",
  "id": 20,
  "result": {
    "description": "Migration plan for upgrading langchain-ai/langchain from 0.1 to 0.2",
    "messages": [
      {
        "role": "user",
        "content": {
          "type": "text",
          "text": "You are helping migrate code from langchain-ai/langchain version 0.1 to 0.2.\n\nSteps:\n1. Use get-library-info to get the documentation index for langchain-ai/langchain\n2. Look for changelog, migration guide, or \"what's new\" pages in the TOC\n3. Use read-page to fetch the relevant migration/changelog pages\n4. If specific APIs in the code snippet need investigation, use get-docs or search-docs\n\nProvide:\n1. A list of breaking changes between 0.1 and 0.2 that affect this code\n2. The migrated code with explanations for each change\n3. Any new features in 0.2 that could improve this code"
        }
      }
    ]
  }
}
```

### 5.2 `debug-with-docs`

Debug an issue using current library documentation.

#### Prompt Definition

```json
{
  "name": "debug-with-docs",
  "title": "Debug With Documentation",
  "description": "Debug an issue using current library documentation. Guides the agent to search for error messages, find correct API usage, and produce a fix.",
  "arguments": [
    { "name": "libraryId", "description": "Library where the issue occurs", "required": true },
    { "name": "errorMessage", "description": "Error message or description", "required": true },
    { "name": "codeSnippet", "description": "Code that produces the error (optional)", "required": false }
  ]
}
```

#### Get Response

```json
{
  "jsonrpc": "2.0",
  "id": 21,
  "result": {
    "description": "Debug langchain-ai/langchain issue: AttributeError: 'ChatOpenAI' object has no attribute 'predict'",
    "messages": [
      {
        "role": "user",
        "content": {
          "type": "text",
          "text": "You are debugging an issue with langchain-ai/langchain.\n\nError: AttributeError: 'ChatOpenAI' object has no attribute 'predict'\n\nSteps:\n1. Use search-docs to find documentation related to this error message or the APIs involved\n2. Use read-page on the most relevant search results to understand correct usage\n3. If needed, use get-library-info to browse the TOC for related topics\n\nBased on the documentation, identify:\n1. The root cause of the error\n2. The correct API usage (with documentation source)\n3. A fixed version of the code"
        }
      }
    ]
  }
}
```

### 5.3 `explain-api`

Explain a library API with current documentation and examples.

#### Prompt Definition

```json
{
  "name": "explain-api",
  "title": "Explain API",
  "description": "Explain a library API with current documentation and examples. Guides the agent to find complete parameter docs, return values, and usage examples.",
  "arguments": [
    { "name": "libraryId", "description": "Library containing the API", "required": true },
    { "name": "apiName", "description": "API to explain (class, function, module)", "required": true }
  ]
}
```

#### Get Response

```json
{
  "jsonrpc": "2.0",
  "id": 22,
  "result": {
    "description": "Explain ChatOpenAI from langchain-ai/langchain",
    "messages": [
      {
        "role": "user",
        "content": {
          "type": "text",
          "text": "Explain the ChatOpenAI API from langchain-ai/langchain.\n\nSteps:\n1. Use get-docs to fetch documentation for ChatOpenAI\n2. If the result has low confidence or is incomplete, use the relatedPages or get-library-info TOC to find more specific pages\n3. Use read-page on relevant pages to get complete API documentation\n4. If needed, use search-docs to find related APIs or usage patterns\n\nProvide:\n1. What ChatOpenAI does and when to use it\n2. Complete parameter/argument documentation\n3. Return value documentation\n4. At least 2 practical examples from the documentation\n5. Common pitfalls or gotchas"
        }
      }
    ]
  }
}
```

---

## 6. Error Handling

Pro-Context uses two error mechanisms, as defined by the MCP spec.

### 6.1 Protocol Errors

Standard JSON-RPC errors for structural problems. These indicate issues with the request itself, not the tool's execution.

| JSON-RPC Code | Meaning | When |
|---------------|---------|------|
| `-32700` | Parse error | Request is not valid JSON |
| `-32600` | Invalid request | Missing `jsonrpc`, `method`, or `id` |
| `-32601` | Method not found | Unknown JSON-RPC method |
| `-32602` | Invalid params | Unknown tool name, missing required arguments, argument type mismatch |
| `-32603` | Internal error | Server crash, database corruption |

Example:

```json
{
  "jsonrpc": "2.0",
  "id": 99,
  "error": {
    "code": -32602,
    "message": "Unknown tool: get-documentation"
  }
}
```

### 6.2 Tool Execution Errors

Application-level errors returned as tool results with `isError: true`. These are actionable — the agent can use the `suggestion` field to self-correct.

**Format**: All tool execution errors return a JSON object in the text content:

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable description.",
  "recoverable": true,
  "suggestion": "Actionable advice for what to do next.",
  "retryAfter": 5,
  "details": {}
}
```

**Wire format**:

```json
{
  "jsonrpc": "2.0",
  "id": 99,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"code\":\"LIBRARY_NOT_FOUND\",\"message\":\"Library 'langchan' not found in registry.\",\"recoverable\":true,\"suggestion\":\"Did you mean 'langchain-ai/langchain'? Use resolve-library to discover libraries.\"}"
      }
    ],
    "isError": true
  }
}
```

### 6.3 Error Code Catalog

| Code | Recoverable | Trigger | Suggestion Template |
|------|-------------|---------|---------------------|
| `LIBRARY_NOT_FOUND` | Yes | Unknown library ID | "Did you mean '{closest}'? Use resolve-library to discover libraries." |
| `TOPIC_NOT_FOUND` | Yes | BM25 search returns no results | "Try search-docs for broader results, or browse the TOC via get-library-info." |
| `PAGE_NOT_FOUND` | No | `read-page` URL returns HTTP 404 | "Check the URL or use get-library-info to refresh the TOC." |
| `URL_NOT_ALLOWED` | Yes | `read-page` URL fails allowlist | "Resolve the library first with get-library-info — its llms.txt URLs are auto-added to the allowlist." |
| `INVALID_CONTENT` | No | Fetched URL is not documentation | "URL does not appear to contain documentation." |
| `SOURCE_UNAVAILABLE` | Varies | Fetch fails and no cache available | "Try again later." |
| `NETWORK_FETCH_FAILED` | Yes | Network/timeout error fetching llms.txt or page | "Network error. Retry in a few seconds." |
| `LLMS_TXT_NOT_FOUND` | No | Library's llms.txt URL returns 404 | "Documentation source not found. The library may have changed its URL." |
| `STALE_CACHE_EXPIRED` | No | Stale cache exceeded 7-day max age | "Cached content has expired. A fresh fetch is required." |
| `RATE_LIMITED` | Yes | Token bucket exhausted (HTTP mode) | "Try again after {retryAfter} seconds." |
| `AUTH_REQUIRED` | No | Missing API key (HTTP mode) | "Provide API key via Authorization: Bearer header." |
| `AUTH_INVALID` | No | Invalid or revoked API key | "Check your API key." |
| `INTERNAL_ERROR` | No | Unexpected server error | "This has been logged. Try again." |

---

## 7. HTTP Mode API

These details apply only when running with `transport: http`.

### 7.1 Authentication

All requests (except the initial `initialize` POST) must include an API key.

**Header**: `Authorization: Bearer pc_aBcDeFgH...`

**Key format**: `pc_` prefix + 40 chars base64url (43 chars total).

**Server-side storage**: SHA-256 hash of the key + first 8 chars as prefix. The full key is never stored.

**Responses for auth failures**:

| Situation | HTTP Status | Error Code |
|-----------|-------------|------------|
| No `Authorization` header | 401 Unauthorized | `AUTH_REQUIRED` |
| Invalid or revoked key | 401 Unauthorized | `AUTH_INVALID` |

### 7.2 Rate Limiting

Token bucket algorithm per API key.

**Default limits:**

| Parameter | Value |
|-----------|-------|
| `capacity` (burst size) | 10 |
| `refillRate` | 1 token/second (60/minute) |

**Response headers** (on every HTTP response):

| Header | Description | Example |
|--------|-------------|---------|
| `X-RateLimit-Limit` | Requests per minute | `60` |
| `X-RateLimit-Remaining` | Remaining requests | `42` |
| `X-RateLimit-Reset` | Unix timestamp when bucket refills | `1707700000` |

**When rate limited**: Server returns a tool execution error with code `RATE_LIMITED` and `retryAfter` in seconds.

### 7.3 CORS

**Default configuration**: `origins: ["*"]` (configurable via `security.cors.origins` in config).

Production deployments should restrict this to specific origins.

---

## 8. Versioning and Compatibility

### 8.1 Protocol Version

Pro-Context targets **MCP protocol version `2025-11-25`**. The server includes this in its `InitializeResult` and expects clients to send it in the `MCP-Protocol-Version` header (HTTP mode).

The server also accepts `2025-03-26` for backwards compatibility (see Technical Spec Section 9.2). If a client requests an unsupported protocol version, the server responds with HTTP 400.

### 8.2 Server Version

Pro-Context follows [Semantic Versioning](https://semver.org/):

- **Major** (`X.0.0`): Breaking changes to tool schemas, resource URIs, or error codes.
- **Minor** (`0.X.0`): New tools, resources, or prompt templates. New optional fields on existing schemas.
- **Patch** (`0.0.X`): Bug fixes, performance improvements, documentation updates.

The server version is reported in `serverInfo.version` during initialization and in the `pro-context://health` resource.

### 8.3 Registry Version

The library registry (`known-libraries.json`) is versioned independently from the server using date-based versions (e.g., `registry-v2026-02-20`). Registry updates do not require server updates. See Technical Spec Section 6 for update mechanism.

### 8.4 Breaking Change Policy

A breaking change is any modification that would cause an existing, correct client integration to fail:

- Removing a tool, resource, or prompt template.
- Removing a required output field from a tool response.
- Changing the type or semantics of an existing field.
- Renaming a tool, resource URI, or prompt name.
- Changing an optional input parameter to required.

Breaking changes require a **major version bump** and at least one minor release of deprecation notice (see below).

Non-breaking changes (additive):

- Adding a new tool, resource, or prompt template.
- Adding an optional input parameter with a default value.
- Adding a new optional output field.
- Adding a new error code.

### 8.5 Deprecation Policy

When a tool, resource, prompt, or field is scheduled for removal:

1. **Deprecation notice**: The element is marked as deprecated in the tool `description` and in release notes. It continues to function normally.
2. **Minimum deprecation period**: One minor release cycle.
3. **Removal**: The element is removed in the next major version.

Deprecated tools include `"[DEPRECATED]"` at the start of their `description` field so that agents and clients can detect deprecation programmatically.

---

*This document is the authoritative contract for Pro-Context's external interface. Implementation details are in the [Technical Spec](03-technical-spec.md). Feature rationale and user stories are in the [Functional Spec](02-functional-spec.md).*
