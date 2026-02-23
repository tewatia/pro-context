# Pro-Context: Functional Specification

> **Document**: 01-functional-spec.md
> **Status**: Draft v1
> **Last Updated**: 2026-02-22

---

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Design Philosophy](#2-design-philosophy)
- [3. Non-Goals](#3-non-goals)
- [4. MCP Tools](#4-mcp-tools)
  - [4.1 resolve-library](#41-resolve-library)
  - [4.2 get-library-docs](#42-get-library-docs)
  - [4.3 read-page](#43-read-page)
- [5. Transport Modes](#5-transport-modes)
  - [5.1 stdio Transport](#51-stdio-transport)
  - [5.2 HTTP Transport](#52-http-transport)
- [6. Library Registry](#6-library-registry)
- [7. Documentation Fetching & Caching](#7-documentation-fetching--caching)
- [8. Security Model](#8-security-model)
- [9. Error Handling](#9-error-handling)
- [10. Design Decisions](#10-design-decisions)

---

## 1. Introduction

Pro-Context is an open-source MCP (Model Context Protocol) server that connects AI coding agents to accurate, up-to-date library documentation.

**The problem it solves**: AI coding agents hallucinate library API details because their training data is outdated. Pro-Context gives agents a reliable path to fetch current documentation on demand, reducing hallucination without requiring model retraining.

---

## 2. Design Philosophy

**Agent-driven navigation.** Pro-Context does not try to guess which documentation is relevant to an agent's task. It gives the agent the tools to navigate documentation themselves — see what sections exist, fetch the ones that matter.

**Minimal footprint.** The server does three things: resolve library names, serve table-of-contents, and serve page content. Nothing more.

**Quality over features.** Fewer tools done correctly beats many tools done partially. Every code path is tested, every error is actionable, every response is predictable.

---

## 3. Non-Goals

The following are explicitly out of scope for the open-source version:

- **Full-text search across documentation**: No BM25, no FTS index. Agents navigate by structure.
- **Content chunking and ranking**: No server-side relevance extraction. Content is returned as-is from source.
- **API key management**: No authentication for the HTTP transport in this version.
- **Rate limiting**: No per-client throttling.
- **Multi-tenant deployments**: Single-user or single-team usage only.
- **Documentation generation**: Pro-Context does not generate or modify documentation. It only fetches and serves what already exists.
- **Version-aware documentation**: No version pinning. Always serves the latest documentation from the registry.

---

## 4. MCP Tools

Pro-Context exposes three MCP tools. All tools are async and return structured JSON responses.

### 4.1 resolve-library

**Purpose**: Resolve a library name or package name to a known documentation source. Always the first step — establishes the `libraryId` used by subsequent tools.

**Input**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Library name, package name, or alias. Examples: `"langchain"`, `"langchain-openai"`, `"langchain[openai]>=0.3"`, `"LangChain"` |

**Processing**:
1. Normalize input: strip pip extras, version specifiers; lowercase; trim whitespace
2. Exact match against known package names (e.g., `"langchain-openai"` → `"langchain"`)
3. Exact match against library IDs
4. Match against known aliases
5. Fuzzy match (Levenshtein) for typos
6. If no match: return empty list (never an error — unknown library is a valid outcome)

All matching is against in-memory indexes loaded from the registry at startup. No network calls.

**Output**:

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

| Field | Description |
|-------|-------------|
| `libraryId` | Stable identifier used in all subsequent tool calls |
| `name` | Human-readable display name |
| `languages` | Languages this library supports |
| `docsUrl` | Primary documentation site URL |
| `matchedVia` | How the match was made: `"package_name"`, `"library_id"`, `"alias"`, `"fuzzy"` |
| `relevance` | 0.0–1.0. Exact matches are 1.0; fuzzy matches are proportional to edit distance |

**Notes**:
- `matches` is always sorted by `relevance` descending. Exact matches (relevance `1.0`) always precede fuzzy matches. This ordering is guaranteed and stable.
- Returns multiple matches when fuzzy matching produces several candidates above the similarity threshold.
- An empty `matches` list means the library is not in the registry. The agent should inform the user.

---

### 4.2 get-library-docs

**Purpose**: Fetch the table of contents for a library's documentation. Returns the raw llms.txt content so the agent can read it directly and decide what to fetch next.

**Input**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `libraryId` | string | Yes | Library identifier from `resolve-library` |

**Processing**:
1. Look up `libraryId` in registry → get `llmsTxtUrl`
2. Check SQLite cache for `toc:{libraryId}` — if fresh, return cached entry
3. On cache miss: HTTP GET `llmsTxtUrl`, store raw content in SQLite cache (TTL: 24 hours)
4. Return raw content

**Output**:

```json
{
  "libraryId": "langchain",
  "name": "LangChain",
  "content": "# Docs by LangChain\n\n## Concepts\n\n- [Chat Models](https://...): Interface for language models...\n- [Streaming](https://...): Stream model outputs...\n\n## API Reference\n\n- [Create Deployment](https://...): Create a new deployment.\n",
  "cached": false,
  "cachedAt": null,
  "stale": false
}
```

| Field | Description |
|-------|-------------|
| `content` | Raw llms.txt content as markdown. The agent reads this directly to understand available documentation and extract URLs to pass to `read-page` |
| `cached` | Whether this response was served from cache |
| `cachedAt` | ISO 8601 timestamp (UTC) of when the content was originally fetched. `null` if not cached |
| `stale` | `true` if the content is past its TTL and a background refresh has been triggered. The content is still valid but may be slightly outdated. Always present; defaults to `false` |

**Notes**:
- The llms.txt format is a markdown file with section headings and links — exactly what LLMs read well. No server-side parsing needed.
- The agent extracts page URLs from the content and passes them to `read-page`.

---

### 4.3 read-page

**Purpose**: Fetch the full content of a specific documentation page and its heading structure.

**Input**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL of the documentation page, typically from `get-library-docs` sections |

**Processing**:
1. Validate URL against SSRF allowlist
2. Check SQLite cache for `page:{sha256(url)}` — if fresh, return from cache
3. On cache miss: HTTP GET the URL, store full content in SQLite cache (TTL: 24 hours)
4. Parse markdown: extract heading tree with line numbers
5. Return content and heading structure

**Output**:

```json
{
  "url": "https://docs.langchain.com/docs/concepts/streaming.md",
  "headings": [
    { "level": 1, "title": "Streaming", "anchor": "streaming", "line": 1 },
    { "level": 2, "title": "Overview", "anchor": "overview", "line": 3 },
    { "level": 2, "title": "Streaming with Chat Models", "anchor": "streaming-with-chat-models", "line": 12 },
    { "level": 3, "title": "Using .stream()", "anchor": "using-stream", "line": 18 },
    { "level": 2, "title": "Streaming with Chains", "anchor": "streaming-with-chains", "line": 35 }
  ],
  "content": "# Streaming\n\n## Overview\n...",
  "cached": true,
  "cachedAt": "2026-02-22T10:00:00Z"
}
```

| Field | Description |
|-------|-------------|
| `headings` | All headings on the page in document order (top to bottom). Each entry includes `level` (1–4), `title`, `anchor`, and `line` |
| `headings[].anchor` | Slugified heading title for constructing deep links (e.g., `"streaming-with-chat-models"`). Format: lowercase, punctuation removed, spaces and underscores replaced with hyphens, consecutive hyphens collapsed. Duplicate anchors within a page are suffixed: `-2`, `-3`, etc. This format is stable |
| `headings[].line` | 1-based line number where the heading appears in the page content |
| `content` | Full page markdown |
| `cached` | Whether this response was served from cache |
| `cachedAt` | ISO 8601 timestamp (UTC) of when the content was originally fetched. `null` if not cached |
| `stale` | `true` if the content is past its TTL and a background refresh has been triggered. Always present; defaults to `false` |

**Notes**:
- The full page is cached on first fetch. Subsequent calls are served from cache — no re-fetch.
- URLs must be from the allowlist. See Section 8.

---

## 5. Transport Modes

Pro-Context supports two transport modes. The same MCP tools are available in both modes.

### 5.1 stdio Transport

The default mode for local development. The MCP client (e.g., Claude Code, Cursor) spawns Pro-Context as a subprocess and communicates over stdin/stdout using the MCP JSON-RPC protocol.

**Characteristics**:
- No network exposure — entirely local
- Process lifecycle managed by the MCP client
- Registry loaded from local disk (`~/.local/share/pro-context/registry/known-libraries.json`)
- SQLite database at `~/.local/share/pro-context/cache.db`
- No authentication required

**Configuration** (in MCP client settings):
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

### 5.2 HTTP Transport

For shared or remote deployments. Implements the MCP Streamable HTTP transport spec (2025-11-25) — a single `/mcp` endpoint accepting both POST (requests) and GET (SSE streams).

**Characteristics**:
- Exposes a single `/mcp` endpoint
- Session management via `MCP-Session-Id` header
- Bearer key authentication (see Section 8 and Section 10, D3)
- Origin validation enforced (see Section 8)
- Protocol version validation via `MCP-Protocol-Version` header
- Supports `SUPPORTED_PROTOCOL_VERSIONS = {"2025-11-25", "2025-03-26"}`

**Configuration**:
```yaml
# pro-context.yaml
server:
  transport: http
  host: "0.0.0.0"
  port: 8080
```

---

## 6. Library Registry

The library registry (`known-libraries.json`) is the data backbone of Pro-Context. It is hosted on GitHub Pages and updated weekly. The MCP server consumes it — it never modifies it.

**Registry update cadence**: Weekly automated builds. Registry updates are independent of MCP server releases.

**Custom registry**: The registry URL is configurable. Point `registry.url` and `registry.metadata_url` in `pro-context.yaml` at any HTTP endpoint that serves the same JSON format to use a private registry. See D6 in Section 10 for details.

**At server startup**:
1. Load local registry file from `~/.local/share/pro-context/registry/`
2. If no local file exists: fall back to bundled snapshot (shipped with the package)
3. In the background: check the configured registry URL for a newer version and download if available. The updated registry is used on the next server start (stdio) or atomically swapped in-memory (HTTP long-running mode).

**In-memory indexes** (rebuilt from registry on each load, <100ms for 1,000 entries):
- Package name → library ID (many-to-one): `"langchain-openai"` → `"langchain"`
- Library ID → full registry entry (one-to-one)
- Alias + ID corpus for fuzzy matching

These three indexes serve all `resolve-library` lookups. No database reads during resolution.

---

## 7. Documentation Fetching & Caching

### Fetching

All documentation is fetched via plain HTTP GET. Pro-Context uses `httpx` with:
- Manual redirect handling (each redirect target is validated against the SSRF allowlist before following)
- 30-second request timeout
- Maximum 3 redirect hops

### Cache

A single SQLite database (`cache.db`) stores all fetched content.

| Table | Key | Content | TTL |
|-------|-----|---------|-----|
| `toc_cache` | `toc:{libraryId}` | Raw llms.txt content | 24 hours |
| `page_cache` | `page:{sha256(url)}` | Full page markdown | 24 hours |

**Stale-while-revalidate**: When a cached entry is past its TTL, it is served immediately with `cached: true` and `stale: true`, and a background task re-fetches the content. This ensures the agent never waits for a network fetch on a cache hit, even if the content is slightly outdated.

**No memory tier**: SQLite reads are fast enough (<5ms) for this use case. A memory cache adds complexity without meaningful latency benefit for single-user deployments.

---

## 8. Security Model

### Bearer Key Authentication (HTTP mode)

- In HTTP mode, all requests must include `Authorization: Bearer <key>`. Requests with a missing or incorrect key receive HTTP 401.
- The key is configured via `server.auth_key` in `pro-context.yaml` or the `PRO_CONTEXT__SERVER__AUTH_KEY` env var.
- If no key is configured, the server auto-generates a random key at startup and logs it to stderr.
- Stdio mode is unaffected — no authentication is required (the transport is a local pipe owned by the spawning process).

### SSRF Prevention

`read-page` accepts arbitrary URLs from the agent. To prevent Server-Side Request Forgery:

- All URLs are validated against an allowlist of permitted domains before fetching
- The allowlist is populated at startup from the registry (all `docsUrl` and `llmsTxtUrl` domains)
- Redirects are followed manually — each redirect target is re-validated before following
- Private IP ranges (`10.x`, `172.16.x`, `192.168.x`, `127.x`, `::1`) are always blocked, regardless of allowlist

### Input Validation

- All tool inputs are validated with Pydantic before processing
- String inputs are trimmed and length-capped (query: 500 chars, URL: 2048 chars)
- Library IDs are validated against a strict pattern (`[a-z0-9_-]+`)

### Content Sanitization

- Fetched markdown content is not executed or rendered server-side
- Content is returned as plain text to the agent — no HTML, no script injection risk

---

## 9. Error Handling

Every error response follows the same structure:

```json
{
  "error": {
    "code": "LIBRARY_NOT_FOUND",
    "message": "No library found matching 'langchan'.",
    "suggestion": "Did you mean 'langchain'? Call resolve-library to find the correct ID.",
    "recoverable": false
  }
}
```

| Field | Description |
|-------|-------------|
| `code` | Machine-readable error code (see table below) |
| `message` | Human-readable description of what went wrong |
| `suggestion` | Actionable next step for the agent |
| `recoverable` | `true` if retrying the identical request may succeed (transient failure). `false` if the request must change before it can succeed (permanent failure) |

**Error codes**:

| Code | Tool | `recoverable` | Description |
|------|------|--------------|-------------|
| `LIBRARY_NOT_FOUND` | `get-library-docs` | `false` | `libraryId` not in registry; retrying won't help |
| `LLMS_TXT_FETCH_FAILED` | `get-library-docs` | `true` | Transient network error or non-200 fetching llms.txt; retry may succeed |
| `PAGE_NOT_FOUND` | `read-page` | `false` | HTTP 404 — the page does not exist at that URL |
| `PAGE_FETCH_FAILED` | `read-page` | `true` | Transient network error fetching page; retry may succeed |
| `URL_NOT_ALLOWED` | `read-page` | `false` | URL domain not in SSRF allowlist; only a different URL will succeed |
| `INVALID_INPUT` | Any | `false` | Input validation failed; the request must be corrected before retrying |

---

## 10. Design Decisions

**D1: Agent-driven navigation**
Pro-Context does not chunk documents or decide which content is relevant. The agent navigates the documentation structure — it sees the TOC, picks sections, reads pages. This is simpler, more predictable, and gives the agent full visibility into what documentation exists.

*Trade-off*: Agents need 2–3 tool calls to reach content instead of 1. Accepted — the calls are fast (mostly cache hits after the first) and the agent retains full control.

**D2: Single SQLite cache tier**
A two-tier cache (memory + SQLite) adds meaningful complexity for marginal latency gain in single-user deployments. SQLite with WAL mode delivers <5ms reads, which is acceptable when the bottleneck is network fetch (100ms–3s). A memory tier can be added in the enterprise version where multi-user throughput justifies it.

**D3: Optional bearer key for HTTP mode**
Stdio mode requires no authentication — the MCP client spawns the server, and the transport is a local pipe. HTTP mode includes optional bearer key authentication: if `server.auth_key` is set in the config, all requests must include a matching `Authorization: Bearer <key>` header or receive HTTP 401. If no key is configured, the server auto-generates one at startup and logs it to stderr. This is lightweight access control for shared-network deployments, not a full auth system — there is no key rotation, hashing, or revocation.

**D4: Registry independence from server version**
The registry (`known-libraries.json`) has its own release cadence (weekly) completely decoupled from the MCP server version. Users get updated library coverage without upgrading the server.

**D5: llms.txt as the documentation contract**
Pro-Context treats the llms.txt file as the authoritative interface to a library's documentation. It does not scrape HTML, parse Sphinx output, or infer documentation structure. Every library in the registry has a valid llms.txt URL — the MCP server only deals with fetching and parsing that format.

**D6: Custom registry as the escape hatch for private documentation**
Teams with internal libraries or private documentation can point Pro-Context at a custom registry by setting `registry.url` and `registry.metadata_url` in `pro-context.yaml`:

```yaml
registry:
  url: "https://docs.internal.example.com/pro-context/known-libraries.json"
  metadata_url: "https://docs.internal.example.com/pro-context/registry_metadata.json"
```

The custom registry must serve:
- **`known-libraries.json`**: An array of library entries in the same schema as the public registry. Each entry must include a valid `llms_txt_url`.
- **`registry_metadata.json`**: A JSON object with `version` (string), `download_url` (string), and `checksum` (`"sha256:<hex>"`) fields so the server's background update check works correctly.

**Important**: The SSRF allowlist is built from domains in the loaded registry. Documentation domains in a custom registry entry are automatically permitted by `read-page` — no additional SSRF configuration is needed.

*Trade-off*: The custom registry completely replaces the public registry — there is no merging. Teams that want both public and private libraries must include the public entries in their custom registry. This is intentional: a merge strategy introduces ordering and conflict-resolution complexity that is not warranted for the open-source version.
