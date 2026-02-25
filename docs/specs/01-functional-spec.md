# ProContext: Functional Specification

> **Document**: 01-functional-spec.md
> **Status**: Draft v1
> **Last Updated**: 2026-02-22

---

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Design Philosophy](#2-design-philosophy)
- [3. Non-Goals](#3-non-goals)
- [4. MCP Tools](#4-mcp-tools)
  - [4.1 resolve_library](#41-resolve_library)
  - [4.2 get_library_docs](#42-get_library_docs)
  - [4.3 read_page](#43-read_page)
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

ProContext is an open-source MCP (Model Context Protocol) server that connects AI coding agents to accurate, up-to-date library documentation.

**The problem it solves**: AI coding agents hallucinate library API details because their training data is outdated. ProContext gives agents a reliable path to fetch current documentation on demand, reducing hallucination without requiring model retraining.

---

## 2. Design Philosophy

**Agent-driven navigation.** ProContext does not try to guess which documentation is relevant to an agent's task. It gives the agent the tools to navigate documentation themselves — see what sections exist, fetch the ones that matter.

**Minimal footprint.** The server does three things: resolve library names, serve table-of-contents, and serve page content. Nothing more.

**Quality over features.** Fewer tools done correctly beats many tools done partially. Every code path is tested, every error is actionable, every response is predictable.

---

## 3. Non-Goals

The following are explicitly out of scope for the open-source version:

- **Full-text search across documentation**: No BM25, no FTS index. Agents navigate by structure.
- **Content chunking and ranking**: No server-side relevance extraction. Content is returned as-is from source.
- **Advanced API key management**: No RBAC, key rotation, key revocation, or multi-key support. Only an optional shared bearer key in HTTP mode (`auth_enabled` + `auth_key`).
- **Rate limiting**: No per-client throttling.
- **Multi-tenant deployments**: Single-user or single-team usage only.
- **Documentation generation**: ProContext does not generate or modify documentation. It only fetches and serves what already exists.
- **Version-aware documentation**: No version pinning. Always serves the latest documentation from the registry.

---

## 4. MCP Tools

ProContext exposes three MCP tools. All tools are async and return structured JSON responses.

### 4.1 resolve_library

**Purpose**: Resolve a library name or package name to a known documentation source. Always the first step — establishes the `library_id` used by subsequent tools.

**Input**:

| Parameter | Type   | Required | Description                                                                                                                    |
| --------- | ------ | -------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `query`   | string | Yes      | Library name, package name, or alias. Examples: `"langchain"`, `"langchain-openai"`, `"langchain[openai]>=0.3"`, `"LangChain"` |

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
      "library_id": "langchain",
      "name": "LangChain",
      "languages": ["python"],
      "docs_url": "https://docs.langchain.com",
      "matched_via": "package_name",
      "relevance": 1.0
    }
  ]
}
```

| Field         | Description                                                                     |
| ------------- | ------------------------------------------------------------------------------- |
| `library_id`  | Stable identifier used in all subsequent tool calls                             |
| `name`        | Human-readable display name                                                     |
| `languages`   | Languages this library supports                                                 |
| `docs_url`    | Primary documentation site URL                                                  |
| `matched_via` | How the match was made: `"package_name"`, `"library_id"`, `"alias"`, `"fuzzy"`  |
| `relevance`   | 0.0–1.0. Exact matches are 1.0; fuzzy matches are proportional to edit distance |

**Notes**:

- `matches` is always sorted by `relevance` descending. Exact matches (relevance `1.0`) always precede fuzzy matches. This ordering is guaranteed and stable.
- Returns multiple matches when fuzzy matching produces several candidates above the similarity threshold.
- An empty `matches` list means the library is not in the registry. The agent should inform the user.

---

### 4.2 get_library_docs

**Purpose**: Fetch the table of contents for a library's documentation. Returns the raw llms.txt content so the agent can read it directly and decide what to fetch next.

**Input**:

| Parameter    | Type   | Required | Description                               |
| ------------ | ------ | -------- | ----------------------------------------- |
| `library_id` | string | Yes      | Library identifier from `resolve_library` |

**Processing**:

1. Look up `library_id` in registry → get `llms_txt_url`
2. Check SQLite cache for `toc:{library_id}` — if fresh, return cached entry
3. On cache miss: HTTP GET `llms_txt_url`, store raw content in SQLite cache (TTL: 24 hours)
4. Return raw content

**Output**:

```json
{
  "library_id": "langchain",
  "name": "LangChain",
  "content": "# Docs by LangChain\n\n## Concepts\n\n- [Chat Models](https://...): Interface for language models...\n- [Streaming](https://...): Stream model outputs...\n\n## API Reference\n\n- [Create Deployment](https://...): Create a new deployment.\n",
  "cached": false,
  "cached_at": null,
  "stale": false
}
```

| Field       | Description                                                                                                                                                                     |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `content`   | Raw llms.txt content as markdown. The agent reads this directly to understand available documentation and extract URLs to pass to `read_page`                                   |
| `cached`    | Whether this response was served from cache                                                                                                                                     |
| `cached_at` | ISO 8601 timestamp (UTC) of when the content was originally fetched. `null` if not cached                                                                                       |
| `stale`     | `true` if the content is past its TTL and a background refresh has been triggered. The content is still valid but may be slightly outdated. Always present; defaults to `false` |

**Notes**:

- The llms.txt format is a markdown file with section headings and links — exactly what LLMs read well. No server-side parsing needed.
- The agent extracts page URLs from the content and passes them to `read_page`.

---

### 4.3 read_page

**Purpose**: Fetch the content of a documentation page with line-number navigation. Returns a heading map of the full page and a windowed slice of the content controlled by `offset` and `limit`.

**Input**:

| Parameter | Type    | Required | Default | Description                                                                                     |
| --------- | ------- | -------- | ------- | ----------------------------------------------------------------------------------------------- |
| `url`     | string  | Yes      | —       | URL of the documentation page, typically from `get_library_docs` sections                       |
| `offset`  | integer | No       | 1       | 1-based line number to start reading from. Use a heading's line number to jump to that section. |
| `limit`   | integer | No       | 2000    | Maximum number of lines to return from the offset.                                              |

**Processing**:

1. Validate URL against SSRF allowlist; validate `offset` >= 1, `limit` >= 1
2. Check SQLite cache for `page:{sha256(url)}` — if fresh, return from cache
3. On cache miss: HTTP GET the URL, parse headings, store full content + headings in SQLite cache (TTL: 24 hours)
4. Build plain-text heading map from full page (always complete, regardless of offset/limit)
5. Slice content to the requested window (`offset`/`limit`)
6. Return heading map, windowed content, and pagination metadata

**Navigation workflow**: Call `read_page` with just the URL to get the heading map and the first 2000 lines. Inspect headings to find the section you need. Call again with `offset` set to that heading's line number to jump there.

**Output**:

```json
{
  "url": "https://docs.langchain.com/docs/concepts/streaming.md",
  "headings": "1: # Streaming\n3: ## Overview\n12: ## Streaming with Chat Models\n18: ### Using .stream()\n27: ### Using .astream()\n35: ## Streaming with Chains",
  "total_lines": 42,
  "offset": 1,
  "limit": 2000,
  "content": "# Streaming\n\n## Overview\n...",
  "cached": false,
  "cached_at": null,
  "stale": false
}
```

| Field         | Description                                                                                                                                               |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `headings`    | Plain-text heading map of the full page (always complete, regardless of offset/limit). Each line: `<line_number>: <heading line>`. Only H1–H4 included.  |
| `total_lines` | Total number of lines in the full page. Useful for determining if more content exists beyond the current window.                                          |
| `offset`      | The 1-based line number the returned content starts from.                                                                                                 |
| `limit`       | The maximum number of lines requested.                                                                                                                    |
| `content`     | Page markdown for the requested window (from offset, up to limit lines). May be shorter than limit if the page ends before the window fills.              |
| `cached`      | Whether this response was served from cache                                                                                                               |
| `cached_at`   | ISO 8601 timestamp (UTC) of when the content was originally fetched. `null` if not cached                                                                 |
| `stale`       | `true` if the content is past its TTL and a background refresh has been triggered. Always present; defaults to `false`                                    |

**Notes**:

- The full page and headings are cached together on first fetch. Subsequent calls with different offsets are served from cache — no re-fetch or re-parse.
- URLs must be from the allowlist. See Section 8.

---

## 5. Transport Modes

ProContext supports two transport modes. The same MCP tools are available in both modes.

### 5.1 stdio Transport

The default mode for local development. The MCP client (e.g., Claude Code, Cursor) spawns ProContext as a subprocess and communicates over stdin/stdout using the MCP JSON-RPC protocol.

**Characteristics**:

- No network exposure — entirely local
- Process lifecycle managed by the MCP client
- Registry loaded from local disk when a valid local registry pair exists (`~/.local/share/procontext/registry/known-libraries.json` + `registry-state.json`), otherwise bundled snapshot fallback
- SQLite database at `~/.local/share/procontext/cache.db`
- No authentication required

**Configuration** (in MCP client settings):

```json
{
  "mcpServers": {
    "procontext": {
      "command": "uvx",
      "args": ["procontext"]
    }
  }
}
```

### 5.2 HTTP Transport

For shared or remote deployments. Implements the MCP Streamable HTTP transport spec (2025-11-25) — a single `/mcp` endpoint accepting both POST (requests) and GET (SSE streams).

**Characteristics**:

- Exposes a single `/mcp` endpoint
- Session management via `MCP-Session-Id` header
- Optional bearer key authentication (disabled by default; see Section 8 and Section 10, D3)
- Origin validation enforced (see Section 8)
- Protocol version validation via `MCP-Protocol-Version` header
- Supports `SUPPORTED_PROTOCOL_VERSIONS = {"2025-11-25", "2025-03-26"}`

**Configuration**:

```yaml
# procontext.yaml
server:
  transport: http
  host: "0.0.0.0"
  port: 8080
  auth_enabled: false
  auth_key: ""
```

---

## 6. Library Registry

The library registry (`known-libraries.json`) is the data backbone of ProContext. It is hosted on GitHub Pages and updated weekly. The MCP server consumes it — it never modifies it.

**Registry update cadence**: Weekly automated builds. Registry updates are independent of MCP server releases.

**Custom registry**: The registry URL is configurable. Point `registry.url` and `registry.metadata_url` in `procontext.yaml` at any HTTP endpoint that serves the same JSON format to use a private registry. See D6 in Section 10 for details.

**At server startup**:

1. Attempt to load local registry pair from `~/.local/share/procontext/registry/known-libraries.json` and `~/.local/share/procontext/registry/registry-state.json`
2. Validate the pair (`known-libraries.json` parses, `registry-state.json` parses, checksum matches)
3. If either file is missing or the pair is invalid: ignore local pair and fall back to bundled snapshot (shipped with the package)
4. In the background: check the configured registry URL for a newer version and download if available. The updated registry is used on the next server start (stdio) or atomically swapped in-memory in HTTP long-running mode (registry indexes + SSRF allowlist updated together).

**Local state sidecar** (`registry-state.json`):

- Stores metadata for the currently active local registry copy: `version`, `checksum`, `updated_at`
- Is written whenever a background registry update is accepted
- Is persisted atomically with `known-libraries.json` as a consistency unit (temp file + fsync + atomic rename)
- Is used as the source of truth for `registry_version` on startup when loading from disk

**Update scheduling policy**:

- Both transports perform one registry update check at startup
- In HTTP long-running mode, successful checks follow a steady 24-hour cadence
- In HTTP long-running mode, **transient** failures (network timeout/DNS/connection issues, upstream 5xx) retry with exponential backoff (starting at 1 minute, capped at 60 minutes, with jitter)
- In HTTP long-running mode, after `8` consecutive transient failures, fast retries are suspended and checks return to 24-hour cadence until the next successful check
- In HTTP long-running mode, **semantic** failures (invalid metadata shape, checksum mismatch, registry schema parse errors) do not fast-retry; they log and return to the normal 24-hour cadence
- In stdio mode, no post-startup retries are scheduled because the process is short-lived

**In-memory indexes** (rebuilt from registry on each load, <100ms for 1,000 entries):

- Package name → library ID (many-to-one): `"langchain-openai"` → `"langchain"`
- Library ID → full registry entry (one-to-one)
- Alias + ID corpus for fuzzy matching

These three indexes serve all `resolve_library` lookups. No database reads during resolution.

---

## 7. Documentation Fetching & Caching

### Fetching

All documentation is fetched via plain HTTP GET. ProContext uses `httpx` with:

- Manual redirect handling (each redirect target is validated against the SSRF allowlist before following)
- 30-second request timeout
- Maximum 3 redirect hops

### Cache

A single SQLite database (`cache.db`) stores all fetched content.

| Table        | Key                  | Content              | TTL      |
| ------------ | -------------------- | -------------------- | -------- |
| `toc_cache`  | `toc:{library_id}`   | Raw llms.txt content | 24 hours |
| `page_cache` | `page:{sha256(url)}` | Full page markdown   | 24 hours |

**Stale-while-revalidate**: When a cached entry is past its TTL, it is served immediately with `cached: true` and `stale: true`, and a background task re-fetches the content. This ensures the agent never waits for a network fetch on a cache hit, even if the content is slightly outdated.

**No memory tier**: SQLite reads are fast enough (<5ms) for this use case. A memory cache adds complexity without meaningful latency benefit for single-user deployments.

---

## 8. Security Model

### Optional Bearer Key Authentication (HTTP mode)

- HTTP mode supports optional bearer key authentication.
- Default behavior: authentication is disabled when `server.auth_enabled` is `false` (the default).
- If `server.auth_enabled` is `true`, all HTTP requests must include `Authorization: Bearer <key>`. Missing or incorrect keys receive HTTP 401.
- The key is configured via `server.auth_key` in `procontext.yaml` or the `PROCONTEXT__SERVER__AUTH_KEY` env var.
- If `server.auth_enabled` is `true` and `server.auth_key` is empty, the server auto-generates a random key at startup and logs it to stderr.
- If `server.auth_enabled` is `false`, the server logs a startup warning that HTTP authentication is disabled (regardless of host/bind address).
- Stdio mode is unaffected — no authentication is required (the transport is a local pipe owned by the spawning process).

### SSRF Prevention

`read_page` accepts arbitrary URLs from the agent. To prevent Server-Side Request Forgery:

- All URLs are validated against an allowlist of permitted domains before fetching
- The allowlist is populated at startup from the registry (all `docs_url` and `llms_txt_url` domains)
- In HTTP long-running mode, when a background registry update is accepted, the allowlist is rebuilt from the new registry and atomically swapped with the new indexes
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
    "suggestion": "Did you mean 'langchain'? Call resolve_library to find the correct ID.",
    "recoverable": false
  }
}
```

| Field         | Description                                                                                                                                            |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `code`        | Machine-readable error code (see table below)                                                                                                          |
| `message`     | Human-readable description of what went wrong                                                                                                          |
| `suggestion`  | Actionable next step for the agent                                                                                                                     |
| `recoverable` | `true` if retrying the identical request may succeed (transient failure). `false` if the request must change before it can succeed (permanent failure) |

**Error codes**:

| Code                    | Tool               | `recoverable` | Description                                                             |
| ----------------------- | ------------------ | ------------- | ----------------------------------------------------------------------- |
| `LIBRARY_NOT_FOUND`     | `get_library_docs` | `false`       | `library_id` not in registry; retrying won't help                       |
| `LLMS_TXT_FETCH_FAILED` | `get_library_docs` | `true`        | Transient network error or non-200 fetching llms.txt; retry may succeed |
| `PAGE_NOT_FOUND`        | `read_page`        | `false`       | HTTP 404 — the page does not exist at that URL                          |
| `PAGE_FETCH_FAILED`     | `read_page`        | `true`        | Transient network error fetching page; retry may succeed                |
| `URL_NOT_ALLOWED`       | `read_page`        | `false`       | URL domain not in SSRF allowlist; only a different URL will succeed     |
| `INVALID_INPUT`         | Any                | `false`       | Input validation failed; the request must be corrected before retrying  |

---

## 10. Design Decisions

**D1: Agent-driven navigation**
ProContext does not chunk documents or decide which content is relevant. The agent navigates the documentation structure — it sees the TOC, picks sections, reads pages. This is simpler, more predictable, and gives the agent full visibility into what documentation exists.

_Trade-off_: Agents need 2–3 tool calls to reach content instead of 1. Accepted — the calls are fast (mostly cache hits after the first) and the agent retains full control.

**D2: Single SQLite cache tier**
A two-tier cache (memory + SQLite) adds meaningful complexity for marginal latency gain in single-user deployments. SQLite with WAL mode delivers <5ms reads, which is acceptable when the bottleneck is network fetch (100ms–3s). A memory tier can be added in the enterprise version where multi-user throughput justifies it.

**D3: Optional bearer key for HTTP mode**
Stdio mode requires no authentication — the MCP client spawns the server, and the transport is a local pipe. HTTP mode includes optional bearer key authentication controlled by `server.auth_enabled`. If `auth_enabled=true`, all requests must include a matching `Authorization: Bearer <key>` header or receive HTTP 401. If `auth_enabled=true` and `auth_key` is empty, a key is auto-generated and logged at startup. If `auth_enabled=false`, authentication is disabled by default and a warning is logged on startup. This is lightweight access control for shared-network deployments, not a full auth system — there is no key rotation, hashing, or revocation.

**D4: Registry independence from server version**
The registry (`known-libraries.json`) has its own release cadence (weekly) completely decoupled from the MCP server version. Users get updated library coverage without upgrading the server.

**D5: llms.txt as the documentation contract**
ProContext treats the llms.txt file as the authoritative interface to a library's documentation. It does not scrape HTML, parse Sphinx output, or infer documentation structure. Every library in the registry has a valid llms.txt URL — the MCP server only deals with fetching and parsing that format.

**D6: Custom registry as the escape hatch for private documentation**
Teams with internal libraries or private documentation can point ProContext at a custom registry by setting `registry.url` and `registry.metadata_url` in `procontext.yaml`:

```yaml
registry:
  url: "https://docs.internal.example.com/procontext/known-libraries.json"
  metadata_url: "https://docs.internal.example.com/procontext/registry_metadata.json"
```

The custom registry must serve:

- **`known-libraries.json`**: An array of library entries in the same schema as the public registry. Each entry must include a valid `llms_txt_url`.
- **`registry_metadata.json`**: A JSON object with `version` (string), `download_url` (string), and `checksum` (`"sha256:<hex>"`) fields so the server's background update check works correctly.

**Important**: The SSRF allowlist is built from domains in the loaded registry. Documentation domains in a custom registry entry are automatically permitted by `read_page` — no additional SSRF configuration is needed.

_Trade-off_: The custom registry completely replaces the public registry — there is no merging. Teams that want both public and private libraries must include the public entries in their custom registry. This is intentional: a merge strategy introduces ordering and conflict-resolution complexity that is not warranted for the open-source version.
