# Pro-Context: API Reference

> **Document**: 04-api-reference.md
> **Status**: Draft v1
> **Last Updated**: 2026-02-23
> **Depends on**: 01-functional-spec.md, 02-technical-spec.md

---

## Table of Contents

- [1. Protocol Overview](#1-protocol-overview)
  - [1.1 Transport & Framing](#11-transport--framing)
  - [1.2 Initialization Handshake](#12-initialization-handshake)
  - [1.3 Calling a Tool](#13-calling-a-tool)
  - [1.4 Tool Errors vs Protocol Errors](#14-tool-errors-vs-protocol-errors)
- [2. Tool: resolve-library](#2-tool-resolve-library)
  - [2.1 Input Schema](#21-input-schema)
  - [2.2 Output Schema](#22-output-schema)
  - [2.3 Examples](#23-examples)
  - [2.4 Error Cases](#24-error-cases)
- [3. Tool: get-library-docs](#3-tool-get-library-docs)
  - [3.1 Input Schema](#31-input-schema)
  - [3.2 Output Schema](#32-output-schema)
  - [3.3 Examples](#33-examples)
  - [3.4 Error Cases](#34-error-cases)
- [4. Tool: read-page](#4-tool-read-page)
  - [4.1 Input Schema](#41-input-schema)
  - [4.2 Output Schema](#42-output-schema)
  - [4.3 Examples](#43-examples)
  - [4.4 Error Cases](#44-error-cases)
- [5. Resource: session/libraries](#5-resource-sessionlibraries)
  - [5.1 URI](#51-uri)
  - [5.2 Schema](#52-schema)
  - [5.3 Example](#53-example)
- [6. Error Reference](#6-error-reference)
  - [6.1 Error Envelope](#61-error-envelope)
  - [6.2 Error Code Catalogue](#62-error-code-catalogue)
- [7. Transport Reference](#7-transport-reference)
  - [7.1 stdio Transport](#71-stdio-transport)
  - [7.2 HTTP Transport](#72-http-transport)
- [8. Versioning Policy](#8-versioning-policy)

---

## 1. Protocol Overview

### 1.1 Transport & Framing

Pro-Context implements the [Model Context Protocol](https://modelcontextprotocol.io) (MCP) over JSON-RPC 2.0. All messages are UTF-8 JSON.

**stdio transport**: Each message is a single JSON object terminated by a newline (`\n`). Input is read from stdin; output is written to stdout. No HTTP headers, no framing beyond newline delimiters.

**HTTP transport**: JSON-RPC messages are sent as HTTP POST to `/mcp`. Server-sent events (SSE) are streamed as HTTP GET from `/mcp`. Session identity is tracked via the `MCP-Session-Id` header.

Both transports expose the identical set of tools and resources.

---

### 1.2 Initialization Handshake

Every MCP session begins with an `initialize` → `initialized` exchange. Clients must complete this before calling any tools.

**Client → Server** (`initialize`):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-11-25",
    "capabilities": {},
    "clientInfo": {
      "name": "claude-code",
      "version": "1.0.0"
    }
  }
}
```

**Server → Client** (response):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "tools": {},
      "resources": {}
    },
    "serverInfo": {
      "name": "pro-context",
      "version": "0.1.0"
    }
  }
}
```

**Client → Server** (`notifications/initialized`):

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

After `notifications/initialized` is received, the server is ready to handle tool calls and resource reads.

**Supported protocol versions**: `2025-11-25`, `2025-03-26`. If the client requests an unsupported version via the `MCP-Protocol-Version` header (HTTP mode), the server returns HTTP 400.

---

### 1.3 Calling a Tool

All tools are invoked via the `tools/call` JSON-RPC method.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "<tool-name>",
    "arguments": { }
  }
}
```

**Success response** — tool result is returned as a text content block:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "<JSON string of tool output>"
      }
    ]
  }
}
```

The `text` field is a JSON-encoded string. Clients parse it to get the structured output object.

**Listing available tools** (`tools/list`):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}
```

---

### 1.4 Tool Errors vs Protocol Errors

There are two distinct error channels:

**Tool-level errors** — business logic failures (unknown library, SSRF block, fetch failure). These are returned inside the MCP `result` envelope with `isError: true`. The agent receives the error and can take corrective action.

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"error\": {\"code\": \"LIBRARY_NOT_FOUND\", \"message\": \"...\", \"suggestion\": \"...\", \"recoverable\": false}}"
      }
    ],
    "isError": true
  }
}
```

**Protocol-level errors** — malformed JSON-RPC, unknown methods, invalid params before tool dispatch. These use the JSON-RPC `error` field:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "error": {
    "code": -32600,
    "message": "Invalid Request"
  }
}
```

Tool authors and MCP client implementors need to handle both. The agent should only ever encounter tool-level errors during normal operation.

---

## 2. Tool: resolve-library

**Purpose**: Resolve a library name or package identifier to a known documentation source. Always call this first to obtain a `libraryId` for use with `get-library-docs`.

### 2.1 Input Schema

```json
{
  "name": "resolve-library",
  "description": "Resolve a library name, package name, or alias to a known documentation source. Returns zero or more matches. Always the first step — establishes the libraryId used by subsequent tools.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Library name, package name, or alias. Accepts pip-style specifiers: 'langchain', 'langchain-openai', 'langchain[openai]>=0.3', 'LangChain'.",
        "minLength": 1,
        "maxLength": 500
      }
    },
    "required": ["query"]
  }
}
```

**Normalisation applied before matching**: pip extras (`[...]`) and version specifiers (`>=`, `==`, `~=`, `<`, `>`, `!=`, `^`) are stripped; input is lowercased and trimmed.

**Matching order** (first hit wins):
1. Exact match against known package names (PyPI, npm)
2. Exact match against library IDs
3. Exact match against known aliases
4. Levenshtein fuzzy match (score threshold: 70%)
5. No match → empty `matches` list

All matching is in-memory. No network calls.

### 2.2 Output Schema

```json
{
  "type": "object",
  "properties": {
    "matches": {
      "type": "array",
      "description": "Ranked list of matching libraries. Empty array if no match found.",
      "items": {
        "type": "object",
        "properties": {
          "libraryId": {
            "type": "string",
            "description": "Stable identifier. Use in all subsequent tool calls.",
            "pattern": "^[a-z0-9][a-z0-9_-]*$"
          },
          "name": {
            "type": "string",
            "description": "Human-readable display name."
          },
          "languages": {
            "type": "array",
            "items": { "type": "string" },
            "description": "Languages this library supports, e.g. ['python'], ['javascript', 'typescript']."
          },
          "docsUrl": {
            "type": ["string", "null"],
            "description": "Primary documentation site URL. Null if not in registry."
          },
          "matchedVia": {
            "type": "string",
            "enum": ["package_name", "library_id", "alias", "fuzzy"],
            "description": "How the match was made."
          },
          "relevance": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Match confidence. 1.0 for exact matches; proportional to edit distance for fuzzy matches."
          }
        },
        "required": ["libraryId", "name", "languages", "docsUrl", "matchedVia", "relevance"]
      }
    }
  },
  "required": ["matches"]
}
```

### 2.3 Examples

**Exact package name match**:

Request arguments:
```json
{ "query": "langchain-openai>=0.3" }
```

Result (`text` field, parsed):
```json
{
  "matches": [
    {
      "libraryId": "langchain",
      "name": "LangChain",
      "languages": ["python"],
      "docsUrl": "https://docs.langchain.com",
      "matchedVia": "package_name",
      "relevance": 1.0
    }
  ]
}
```

**Fuzzy match (typo)**:

Request arguments:
```json
{ "query": "fastapi" }
```

Result (typo example — `"fasapi"` → `"fastapi"`):
```json
{
  "matches": [
    {
      "libraryId": "fastapi",
      "name": "FastAPI",
      "languages": ["python"],
      "docsUrl": "https://fastapi.tiangolo.com",
      "matchedVia": "fuzzy",
      "relevance": 0.92
    }
  ]
}
```

**No match**:

Request arguments:
```json
{ "query": "xyzzy-nonexistent" }
```

Result:
```json
{
  "matches": []
}
```

An empty `matches` list is a valid, non-error outcome. The library is simply not in the registry.

### 2.4 Error Cases

`resolve-library` does not raise tool-level errors. An unrecognised library returns an empty list. The only failure path is `INVALID_INPUT` if the input fails Pydantic validation (e.g. empty string, query over 500 characters).

---

## 3. Tool: get-library-docs

**Purpose**: Fetch the table of contents (llms.txt) for a library. Returns the raw markdown content the agent reads to identify documentation pages and their URLs.

### 3.1 Input Schema

```json
{
  "name": "get-library-docs",
  "description": "Fetch the llms.txt table of contents for a library. Returns raw markdown listing documentation sections and page URLs. The agent reads this to decide which pages to fetch with read-page.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "libraryId": {
        "type": "string",
        "description": "Library identifier from resolve-library.",
        "pattern": "^[a-z0-9][a-z0-9_-]*$"
      }
    },
    "required": ["libraryId"]
  }
}
```

### 3.2 Output Schema

```json
{
  "type": "object",
  "properties": {
    "libraryId": {
      "type": "string",
      "description": "The library identifier."
    },
    "name": {
      "type": "string",
      "description": "Human-readable library name."
    },
    "content": {
      "type": "string",
      "description": "Raw llms.txt content as markdown. Contains section headings and links to documentation pages. The agent reads this directly to extract page URLs."
    },
    "cached": {
      "type": "boolean",
      "description": "True if this response was served from cache."
    },
    "cachedAt": {
      "type": ["string", "null"],
      "format": "date-time",
      "description": "ISO 8601 timestamp of when the content was originally fetched. Null if not cached."
    },
    "stale": {
      "type": "boolean",
      "description": "True if the cached entry has passed its TTL. Content is still valid but a background refresh has been triggered."
    }
  },
  "required": ["libraryId", "name", "content", "cached", "cachedAt", "stale"]
}
```

**Cache behaviour**:
- TTL: 24 hours from fetch time.
- **Stale-while-revalidate**: An expired entry is served immediately (`stale: true`) while a background refresh runs. The agent never waits for a network fetch on a cache hit.
- `stale: true` does not indicate an error. The content is accurate as of `cachedAt`.

### 3.3 Examples

**Cache miss (first fetch)**:

Request arguments:
```json
{ "libraryId": "langchain" }
```

Result:
```json
{
  "libraryId": "langchain",
  "name": "LangChain",
  "content": "# Docs by LangChain\n\n## Concepts\n\n- [Chat Models](https://docs.langchain.com/docs/concepts/chat_models.md): Interface for language models that take messages as input and return messages as output.\n- [Streaming](https://docs.langchain.com/docs/concepts/streaming.md): Stream model outputs as they are generated.\n\n## How-to Guides\n\n- [How to return structured data from a model](https://docs.langchain.com/docs/how_to/structured_output.md): ...\n\n## API Reference\n\n- [BaseChatModel](https://api.python.langchain.com/en/latest/language_models/langchain_core.language_models.chat_models.BaseChatModel.md): ...\n",
  "cached": false,
  "cachedAt": null,
  "stale": false
}
```

**Cache hit (fresh)**:

```json
{
  "libraryId": "langchain",
  "name": "LangChain",
  "content": "...",
  "cached": true,
  "cachedAt": "2026-02-23T10:00:00Z",
  "stale": false
}
```

**Cache hit (stale — TTL expired, background refresh running)**:

```json
{
  "libraryId": "langchain",
  "name": "LangChain",
  "content": "...",
  "cached": true,
  "cachedAt": "2026-02-22T10:00:00Z",
  "stale": true
}
```

### 3.4 Error Cases

| Condition | Error code | `recoverable` |
|-----------|-----------|---------------|
| `libraryId` not found in registry | `LIBRARY_NOT_FOUND` | `false` |
| Network error fetching llms.txt | `LLMS_TXT_FETCH_FAILED` | `true` |
| HTTP non-200 fetching llms.txt | `LLMS_TXT_FETCH_FAILED` | `true` |
| `libraryId` fails pattern validation | `INVALID_INPUT` | `false` |

**`LIBRARY_NOT_FOUND` example**:
```json
{
  "error": {
    "code": "LIBRARY_NOT_FOUND",
    "message": "Library 'langchan' not found in registry.",
    "suggestion": "Call resolve-library with your query to find the correct library ID.",
    "recoverable": false
  }
}
```

---

## 4. Tool: read-page

**Purpose**: Fetch the full content of a documentation page. Returns heading structure with line numbers for navigation.

### 4.1 Input Schema

```json
{
  "name": "read-page",
  "description": "Fetch the content of a documentation page. Returns the full page markdown and its heading structure. Each heading includes its line number for direct navigation.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "url": {
        "type": "string",
        "description": "URL of the documentation page, typically extracted from get-library-docs output. Must use http or https. Must be a domain from the library registry.",
        "maxLength": 2048
      }
    },
    "required": ["url"]
  }
}
```

### 4.2 Output Schema

**Output schema**:

```json
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "The URL that was fetched (after redirect resolution)."
    },
    "headings": {
      "type": "array",
      "description": "All headings on the page (H1–H4), in document order.",
      "items": {
        "type": "object",
        "properties": {
          "title": {
            "type": "string",
            "description": "Heading text as it appears in the document."
          },
          "level": {
            "type": "integer",
            "minimum": 1,
            "maximum": 4,
            "description": "Heading depth: 1 = H1 (#), 2 = H2 (##), 3 = H3 (###), 4 = H4 (####)."
          },
          "anchor": {
            "type": "string",
            "description": "URL-safe slug. Deduplicated: if the same title appears multiple times, subsequent occurrences get a numeric suffix (-2, -3, ...)."
          },
          "line": {
            "type": "integer",
            "description": "1-based line number where the heading appears in the page content. Use this to navigate directly to a section."
          }
        },
        "required": ["title", "level", "anchor", "line"]
      }
    },
    "content": {
      "type": "string",
      "description": "Full page markdown."
    },
    "cached": { "type": "boolean" },
    "cachedAt": { "type": ["string", "null"], "format": "date-time" },
    "stale": { "type": "boolean" }
  },
  "required": ["url", "headings", "content", "cached", "cachedAt", "stale"]
}
```

### 4.3 Examples

**Full page fetch**:

Request arguments:
```json
{ "url": "https://docs.langchain.com/docs/concepts/streaming.md" }
```

Result:
```json
{
  "url": "https://docs.langchain.com/docs/concepts/streaming.md",
  "headings": [
    { "title": "Streaming", "level": 1, "anchor": "streaming", "line": 1 },
    { "title": "Overview", "level": 2, "anchor": "overview", "line": 3 },
    { "title": "Streaming with Chat Models", "level": 2, "anchor": "streaming-with-chat-models", "line": 12 },
    { "title": "Using .stream()", "level": 3, "anchor": "using-stream", "line": 18 },
    { "title": "Using .astream()", "level": 3, "anchor": "using-astream", "line": 27 },
    { "title": "Streaming with Chains", "level": 2, "anchor": "streaming-with-chains", "line": 35 }
  ],
  "content": "# Streaming\n\n## Overview\n\nLangChain supports streaming...\n\n## Streaming with Chat Models\n...",
  "cached": false,
  "cachedAt": null,
  "stale": false
}
```

**Duplicate heading anchors** (same title appears three times):

```json
{
  "headings": [
    { "title": "Browser Mode", "level": 3, "anchor": "browser-mode", "line": 10 },
    { "title": "Browser Mode", "level": 3, "anchor": "browser-mode-2", "line": 45 },
    { "title": "Browser Mode", "level": 3, "anchor": "browser-mode-3", "line": 78 }
  ]
}
```

### 4.4 Error Cases

| Condition | Error code | `recoverable` |
|-----------|-----------|---------------|
| URL domain not in allowlist | `URL_NOT_ALLOWED` | `false` |
| URL scheme not http/https | `INVALID_INPUT` | `false` |
| HTTP 404 for the URL | `PAGE_NOT_FOUND` | `false` |
| Network error or non-200/404 response | `PAGE_FETCH_FAILED` | `true` |
| Redirect leads to non-allowlisted domain | `URL_NOT_ALLOWED` | `false` |
| URL over 2048 characters | `INVALID_INPUT` | `false` |

**`URL_NOT_ALLOWED` example**:

```json
{
  "error": {
    "code": "URL_NOT_ALLOWED",
    "message": "URL 'https://internal.example.com/docs' is not permitted.",
    "suggestion": "Only URLs from known documentation domains are allowed. Use get-library-docs to obtain valid documentation URLs.",
    "recoverable": false
  }
}
```

---

## 5. Resource: session/libraries

### 5.1 URI

```
pro-context://session/libraries
```

### 5.2 Schema

Read via `resources/read`:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "resources/read",
  "params": {
    "uri": "pro-context://session/libraries"
  }
}
```

Response:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "contents": [
      {
        "uri": "pro-context://session/libraries",
        "mimeType": "application/json",
        "text": "<JSON string>"
      }
    ]
  }
}
```

The `text` field (parsed):

```json
{
  "type": "object",
  "properties": {
    "resolvedLibraries": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "libraryId": { "type": "string" },
          "name": { "type": "string" },
          "resolvedAt": { "type": "string", "format": "date-time" }
        },
        "required": ["libraryId", "name", "resolvedAt"]
      }
    }
  },
  "required": ["resolvedLibraries"]
}
```

### 5.3 Example

```json
{
  "resolvedLibraries": [
    {
      "libraryId": "langchain",
      "name": "LangChain",
      "resolvedAt": "2026-02-23T10:00:00Z"
    },
    {
      "libraryId": "pydantic",
      "name": "Pydantic",
      "resolvedAt": "2026-02-23T10:05:00Z"
    }
  ]
}
```

**Purpose**: Allows the agent to recall which libraries have already been resolved in the current session, without re-calling `resolve-library`. Empty list at session start. Populated by each successful `resolve-library` call.

**Listing available resources** (`resources/list`):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "resources/list",
  "params": {}
}
```

Response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "resources": [
      {
        "uri": "pro-context://session/libraries",
        "name": "Session Libraries",
        "description": "Libraries resolved in the current session.",
        "mimeType": "application/json"
      }
    ]
  }
}
```

---

## 6. Error Reference

### 6.1 Error Envelope

All tool-level errors share the same envelope:

```json
{
  "error": {
    "code": "<ErrorCode>",
    "message": "<human-readable description>",
    "suggestion": "<actionable next step for the agent>",
    "recoverable": true | false
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Machine-readable error code (see table below) |
| `message` | string | What went wrong, in plain language |
| `suggestion` | string | What the agent should do next |
| `recoverable` | boolean | Whether retrying the same request might succeed (e.g. transient network error) |

This envelope is returned inside the MCP `result` content with `isError: true` — not as a JSON-RPC protocol error.

### 6.2 Error Code Catalogue

| Code | Raised by | Description | `recoverable` |
|------|-----------|-------------|---------------|
| `LIBRARY_NOT_FOUND` | `get-library-docs` | `libraryId` is valid syntax but not present in the registry | `false` |
| `LLMS_TXT_FETCH_FAILED` | `get-library-docs` | Network error, timeout, or non-200 HTTP response when fetching the llms.txt URL | `true` |
| `PAGE_NOT_FOUND` | `read-page` | HTTP 404 for the requested URL | `false` |
| `PAGE_FETCH_FAILED` | `read-page` | Network error, timeout, non-200/404 HTTP response, or too many redirects | `true` |
| `URL_NOT_ALLOWED` | `read-page` | URL domain is not in the SSRF allowlist, or is a private IP range | `false` |
| `INVALID_INPUT` | Any tool | Input failed Pydantic validation (empty query, URL too long, invalid library ID pattern, etc.) | `false` |

**On `recoverable: true`**: The same request may succeed if retried after a brief delay. Network errors and upstream failures are the typical cause. The agent should inform the user rather than retry indefinitely.

**On `recoverable: false`**: Retrying the identical request will not succeed. The agent must take a different action (e.g. use `resolve-library` to find a valid `libraryId`, or check the URL is from a known documentation domain).

---

## 7. Transport Reference

### 7.1 stdio Transport

**How it works**: The MCP client spawns Pro-Context as a subprocess. Messages are newline-delimited JSON over stdin/stdout. stderr is reserved for structured log output (does not affect the JSON-RPC stream).

**MCP client configuration** (Claude Code, Cursor, Windsurf):

```json
{
  "mcpServers": {
    "pro-context": {
      "command": "uvx",
      "args": ["pro-context"]
    }
  }
}
```

**With a local config file**:

```json
{
  "mcpServers": {
    "pro-context": {
      "command": "uvx",
      "args": ["pro-context", "--config", "/path/to/pro-context.yaml"]
    }
  }
}
```

**Process lifecycle**: The MCP client manages the process. Pro-Context exits when stdin is closed.

**No authentication**: stdio transport is inherently local. No API keys or tokens required.

---

### 7.2 HTTP Transport

**Endpoint**: `POST /mcp` for JSON-RPC requests, `GET /mcp` for SSE streams.

**Protocol**: MCP Streamable HTTP (spec 2025-11-25).

**Starting the server**:

```yaml
# pro-context.yaml
server:
  transport: http
  host: "0.0.0.0"
  port: 8080
```

```bash
uvx pro-context --config pro-context.yaml
# or via env var:
PRO_CONTEXT__SERVER__TRANSPORT=http uvx pro-context
```

**Request headers**:

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <key>`. The key is either configured via `server.auth_key` or auto-generated at startup (logged to stderr). Missing or incorrect key → HTTP 401. |
| `Content-Type` | Yes | `application/json` |
| `MCP-Session-Id` | Yes (after init) | Session identifier returned in `initialize` response. Must be included on all subsequent requests in the session. |
| `MCP-Protocol-Version` | Recommended | `2025-11-25` or `2025-03-26`. Validated if present; unknown version → HTTP 400. |
| `Origin` | Browser clients only | Must match `http://localhost` or `https://localhost` (with optional port). Non-localhost origins → HTTP 403. |

**Security constraints**:

1. **Bearer key authentication**: All HTTP requests must include `Authorization: Bearer <key>`. Requests with a missing or incorrect key are rejected with HTTP 401. The key is configured via `server.auth_key` in `pro-context.yaml` or the `PRO_CONTEXT__SERVER__AUTH_KEY` environment variable. If no key is configured, the server auto-generates a random key at startup and logs it to stderr. Stdio mode is unaffected — no authentication is required.

2. **Origin validation**: Requests with a non-localhost `Origin` header are rejected with HTTP 403. This prevents DNS rebinding attacks. Requests without an `Origin` header (standard API clients, curl) are allowed.

3. **Protocol version validation**: If `MCP-Protocol-Version` is present and not in `{"2025-11-25", "2025-03-26"}`, the server returns HTTP 400.

4. **SSRF protection**: Applies to all documentation fetches, regardless of transport mode (see Section 6.2, `URL_NOT_ALLOWED`).

**Example POST request**:

```
POST /mcp HTTP/1.1
Host: localhost:8080
Authorization: Bearer <key>
Content-Type: application/json
MCP-Session-Id: sess_abc123
MCP-Protocol-Version: 2025-11-25

{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"resolve-library","arguments":{"query":"langchain"}}}
```

**SSE stream** (GET `/mcp`):

Used for server-initiated notifications. Connect once per session; the server sends events as they occur. Most clients use this for progress updates and push notifications. For simple request-response tool calls, the POST endpoint suffices.

---

## 8. Versioning Policy

### Server Version

Pro-Context follows [Semantic Versioning](https://semver.org) (`MAJOR.MINOR.PATCH`).

| Change type | Version bump |
|-------------|-------------|
| New tool or resource | MINOR |
| New optional field in response | MINOR |
| Breaking change to input/output schema | MAJOR |
| Bug fix, performance improvement | PATCH |
| Registry update (no server change) | No bump |

The server version is returned in the `initialize` response (`serverInfo.version`) and in the `X-Pro-Context-Version` HTTP response header (HTTP transport).

### MCP Protocol Version

Pro-Context supports two MCP protocol versions simultaneously:

| Version | Status |
|---------|--------|
| `2025-11-25` | Supported (primary) |
| `2025-03-26` | Supported (compatibility) |

When a new MCP specification version is published, Pro-Context adds support in the next MINOR release. The oldest supported version is dropped when it is no longer used by any major MCP client.

### Registry Version

The library registry (`known-libraries.json`) has its own version, independent of the server version. The registry is updated weekly on GitHub Pages. The server downloads the latest registry in the background at startup. Registry version changes never require a server update — the server is always forward-compatible with newer registry files.

The current registry version loaded by a running server instance is visible in the `server_started` log event (`registry_version` field).
