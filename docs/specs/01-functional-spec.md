# ProContext: Functional Specification

> **Document**: 01-functional-spec.md
> **Status**: Draft v2
> **Last Updated**: 2026-03-08

---

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Design Philosophy](#2-design-philosophy)
- [3. Non-Goals](#3-non-goals)
- [4. MCP Tools](#4-mcp-tools)
  - [4.1 resolve_library](#41-resolve_library)
  - [4.2 read_page](#42-read_page)
  - [4.3 search_page](#43-search_page)
  - [4.4 read_outline](#44-read_outline)
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

**Minimal footprint.** The server does four things: resolve library names, fetch documentation pages, browse page outlines, and search within pages. Nothing more.

**Quality over features.** Fewer tools done correctly beats many tools done partially. Every code path is tested, every error is actionable, every response is predictable.

---

## 3. Non-Goals

The following are explicitly out of scope for the open-source version:

- **Cross-library full-text search**: No BM25, no FTS index across the documentation corpus. `search_page` performs keyword/regex matching within a single page — it does not search across pages or libraries.
- **Content chunking and ranking**: No server-side relevance extraction. Content is returned as-is from source.
- **Advanced API key management**: No RBAC, key rotation, key revocation, or multi-key support. Only an optional shared bearer key in HTTP mode (`auth_enabled` + `auth_key`).
- **Rate limiting**: No per-client throttling.
- **Multi-tenant deployments**: Single-user or single-team usage only.
- **Documentation generation**: ProContext does not generate or modify documentation. It only fetches and serves what already exists.
- **Version-aware documentation**: No version pinning. Always serves the latest documentation from the registry.

---

## 4. MCP Tools

ProContext exposes four MCP tools. All tools are async and return structured JSON responses.

### 4.1 resolve_library

**Purpose**: Resolve a library name or package name to a known documentation source. Always the first step — establishes the library identity and provides URLs the agent can use with `read_page` and `search_page`.

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
      "description": "Framework for building LLM-powered applications.",
      "languages": ["python"],
      "index_url": "https://python.langchain.com/llms.txt",
      "readme_url": "https://raw.githubusercontent.com/langchain-ai/langchain/master/README.md",
      "matched_via": "package_name",
      "relevance": 1.0
    }
  ]
}
```

| Field          | Description                                                                                                |
| -------------- | ---------------------------------------------------------------------------------------------------------- |
| `library_id`   | Stable identifier for the library                                                                          |
| `name`         | Human-readable display name                                                                                |
| `description`  | Short description of what the library does. May be empty for older registry entries                        |
| `languages`    | Languages this library supports                                                                            |
| `index_url`    | URL to the library's llms.txt documentation index. Pass to `read_page` to browse the table of contents     |
| `readme_url`   | URL to the library's README file (typically on GitHub). May be `null` if not available in the registry      |
| `matched_via`  | How the match was made: `"package_name"`, `"library_id"`, `"alias"`, `"fuzzy"`                             |
| `relevance`    | 0.0–1.0. Exact matches are 1.0; fuzzy matches are proportional to edit distance                            |

**Notes**:

- `matches` is always sorted by `relevance` descending. Exact matches (relevance `1.0`) always precede fuzzy matches. This ordering is guaranteed and stable.
- Returns multiple matches when fuzzy matching produces several candidates above the similarity threshold.
- An empty `matches` list means the library is not in the registry. The agent should inform the user.
- The agent typically uses `index_url` with `read_page` to browse the documentation index, or with `search_page` to find specific topics within the index.

---

### 4.2 read_page

**Purpose**: Fetch the content of any documentation URL — llms.txt indexes, README files, or documentation pages — with line-number navigation. Returns a compacted structural outline and a windowed slice of the content controlled by `offset` and `limit`.

**Input**:

| Parameter | Type    | Required | Default | Description                                                                                     |
| --------- | ------- | -------- | ------- | ----------------------------------------------------------------------------------------------- |
| `url`     | string  | Yes      | —       | URL of the page to read. Typically from `resolve_library` output (`index_url`, `readme_url`) or from links found within a documentation index. |
| `offset`  | integer | No       | 1       | 1-based line number to start reading from. Use a heading's line number to jump to that section. |
| `limit`   | integer | No       | 500     | Maximum number of lines to return from the offset.                                              |

**Processing**:

1. Validate URL against SSRF allowlist; validate `offset` >= 1, `limit` >= 1
2. Check SQLite cache for `page:{sha256(url)}` — if fresh, return from cache
3. On cache miss: if URL does not already end with `.md`, try fetching `url + ".md"` first. On any failure (404, timeout, network error), fall back to the original URL silently. A 200 HTML response from the `.md` probe is accepted as-is — no fallback, since the original URL would return the same content on an SPA. `.md` is never appended to redirect targets; redirects are followed as the server directs. Store full content + outline in SQLite cache keyed against the original URL.
4. Compact outline for response (progressive depth reduction to ≤50 entries; status message if irreducible)
5. Slice content to the requested window (`offset`/`limit`)
6. Return compacted outline, windowed content, and pagination metadata

**Navigation workflow**: Call `read_page` to get the compacted outline and the first 500 lines. Inspect the outline to find the section you need, then call again with `offset` set to that line number. For pages with very large outlines (status message instead of outline), use `read_outline` to browse the full outline with pagination. Use `search_page` when you know what keyword you're looking for and want to jump directly to matching content.

**Output**:

```json
{
  "url": "https://docs.langchain.com/docs/concepts/streaming.md",
  "outline": "1:# Streaming\n3:## Overview\n12:## Streaming with Chat Models\n18:### Using .stream()\n27:### Using .astream()\n35:## Streaming with Chains",
  "total_lines": 42,
  "offset": 1,
  "limit": 500,
  "content": "# Streaming\n\n## Overview\n...",
  "has_more": true,
  "next_offset": 501,
  "content_hash": "a1b2c3d4e5f6",
  "cached": false,
  "cached_at": null,
  "stale": false
}
```

| Field          | Description                                                                                                                                             |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `outline`      | Compacted structural outline of the page (target: ≤50 entries). Progressive depth reduction removes lower-priority headings (H6 → H5 → fenced content → H4 → H3). When the page outline exceeds 50 entries even after maximum reduction, this field contains a status message directing the agent to use `read_outline` for paginated access. Each entry: `<line_number>:<original line>`. |
| `total_lines`  | Total number of lines in the full page. Useful for determining if more content exists beyond the current window.                                        |
| `offset`       | The 1-based line number the returned content starts from.                                                                                               |
| `limit`        | The maximum number of lines requested.                                                                                                                  |
| `content`      | Page markdown for the requested window (from offset, up to limit lines). May be shorter than limit if the page ends before the window fills.            |
| `has_more`     | `true` if more content exists beyond the current window. When `true`, call again with `offset=next_offset` to continue reading.                         |
| `next_offset`  | Line number to pass as `offset` to continue reading. `null` if no more content.                                                                        |
| `content_hash` | Truncated SHA-256 (12 hex chars) of the full page content. Compare across paginated calls to detect if the underlying page changed due to a background cache refresh. |
| `cached`       | Whether this response was served from cache                                                                                                             |
| `cached_at`    | ISO 8601 timestamp (UTC) of when the content was originally fetched. `null` if not cached                                                               |
| `stale`        | `true` if the cache entry has expired and a background refresh has been triggered. Content is stale but usable. Always present; defaults to `false`.     |

**Notes**:

- The outline is compacted to ≤50 entries to save tokens. For the complete outline, use `read_outline`.
- The full page and outline are cached together on first fetch. Subsequent calls with different offsets are served from cache — no re-fetch or re-parse.
- `search_page` and `read_outline` share the same cache — a page fetched by any tool is available to the others without a re-fetch.
- URLs must be from the allowlist. See Section 8.

---

### 4.3 search_page

**Purpose**: Search within a documentation page for lines matching a query. Returns the matching lines with their line numbers and a compacted outline trimmed to the match range for structural context. The agent uses the outline and match locations to identify relevant sections, then calls `read_page` with `offset`/`limit` to read the full content.

This tool is the equivalent of `grep` for documentation pages. It supports literal keyword search, regex patterns, smart case sensitivity, and word boundary matching.

**Input**:

| Parameter        | Type    | Required | Default   | Description                                                                                          |
| ---------------- | ------- | -------- | --------- | ---------------------------------------------------------------------------------------------------- |
| `url`            | string  | Yes      | —         | URL of the page to search. Same URLs accepted by `read_page`.                                        |
| `query`          | string  | Yes      | —         | Search term or regex pattern.                                                                        |
| `mode`           | string  | No       | `"literal"` | `"literal"`: exact substring match. `"regex"`: treat `query` as a regular expression.              |
| `case_mode`      | string  | No       | `"smart"` | `"smart"`: lowercase query → case-insensitive; mixed/uppercase → case-sensitive. `"insensitive"`: always case-insensitive. `"sensitive"`: always case-sensitive. |
| `whole_word`     | boolean | No       | `false`   | When `true`, match only at word boundaries. Prevents `"api"` from matching `"rapid"` or `"capital"`. |
| `offset`         | integer | No       | 1         | 1-based line number to start searching from. Use for paginating through results.                     |
| `max_results`    | integer | No       | 20        | Maximum number of matching lines to return.                                                          |

**Processing**:

1. Validate URL against SSRF allowlist
2. Fetch page: check SQLite cache for `page:{sha256(url)}` — same cache as `read_page`. On cache miss, fetch and cache.
3. Starting from `offset`, scan each line for a match against `query` (respecting `mode`, `case_mode`, `whole_word`)
4. Collect up to `max_results` matching lines
5. Trim outline to the range between first and last match line numbers
6. Compact trimmed outline (progressive depth reduction to ≤50 entries; status message if irreducible)
7. Return compacted outline, matching lines, and pagination metadata

**Smart case** (default): If the query string is entirely lowercase, matching is case-insensitive. If the query contains any uppercase character, matching is case-sensitive. This mirrors ripgrep's default behaviour — searching `"redis"` finds `"Redis"`, `"REDIS"`, and `"redis"`; searching `"Redis"` finds only `"Redis"`.

**Output**:

```json
{
  "url": "https://python.langchain.com/llms.txt",
  "query": "streaming",
  "outline": "3:## Concepts\n15:## How-to Guides",
  "matches": "7:- [Streaming](https://docs.langchain.com/docs/concepts/streaming.md): Stream model outputs as they are generated.\n22:- [How to stream responses](https://docs.langchain.com/docs/how_to/streaming.md): Step-by-step guide to streaming.",
  "total_lines": 45,
  "has_more": false,
  "next_offset": null,
  "content_hash": "a1b2c3d4e5f6",
  "cached": true,
  "cached_at": "2026-02-23T10:00:00Z"
}
```

| Field          | Description                                                                                                               |
| -------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `outline`      | Compacted structural outline trimmed to the match range (first match line to last match line). Empty string when no matches are found. When the trimmed outline exceeds 50 entries even after maximum reduction, contains a status message directing the agent to `read_outline`. |
| `matches`      | Matching lines formatted as `<line_number>:<content>`, one per line. Empty string when no matches found.                  |
| `total_lines`  | Total number of lines in the page.                                                                                        |
| `has_more`     | `true` if more matches exist beyond the returned set.                                                                     |
| `next_offset`  | Line number to pass as `offset` for the next search call to continue paginating. `null` if no more matches.               |
| `content_hash` | Truncated SHA-256 (12 hex chars) of the full page content. Compare across calls to detect if the underlying page changed. |
| `cached`       | Whether the page content was served from cache.                                                                           |
| `cached_at`   | ISO 8601 timestamp (UTC) of when the page was originally fetched. `null` if not cached.                                   |

**Notes**:

- Matches are returned in document order (ascending line number).
- The agent cross-references match line numbers against the outline to determine which section each match belongs to, then uses `read_page` with the appropriate `offset` to read the full section.
- In `regex` mode, invalid patterns are rejected with `INVALID_INPUT`. Patterns are length-capped to prevent ReDoS.
- `search_page` shares the same cache and fetch path as `read_page` and `read_outline`. A page fetched by any tool is immediately available to the others.

---

### 4.4 read_outline

**Purpose**: Browse the full structural outline of a documentation page with pagination. Use when `read_page` or `search_page` return an outline status message indicating the page outline is too large, or when you need to explore the full page structure without fetching content.

**Input**:

| Parameter | Type    | Required | Default | Description                                          |
| --------- | ------- | -------- | ------- | ---------------------------------------------------- |
| `url`     | string  | Yes      | —       | URL of the page. Same URLs accepted by `read_page`.  |
| `offset`  | integer | No       | 1       | 1-based outline entry index to start from.           |
| `limit`   | integer | No       | 1000    | Maximum number of outline entries to return.         |

**Processing**:

1. Validate URL against SSRF allowlist; validate `offset` >= 1, `limit` >= 1
2. Check SQLite cache / fetch (same shared path as `read_page`)
3. Parse cached outline string into structured entries
4. Strip empty fence pairs (fence opener + closer with no headings between them)
5. Paginate by entry index (`offset`/`limit`)
6. Return formatted outline entries with pagination metadata

**Output**:

```json
{
  "url": "https://docs.langchain.com/docs/api_reference.md",
  "outline": "1:# API Reference\n5:## Authentication\n12:### API Keys\n28:### OAuth\n45:## Endpoints",
  "total_entries": 847,
  "has_more": true,
  "next_offset": 201,
  "content_hash": "a1b2c3d4e5f6",
  "cached": true,
  "cached_at": "2026-02-23T10:00:00Z",
  "stale": false
}
```

| Field           | Description                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| `outline`       | Paginated outline entries in `<line_number>:<original line>` format, joined by newlines.            |
| `total_entries`  | Total number of entries in the full outline (after stripping empty fences).                          |
| `has_more`      | `true` if more entries exist beyond the current window.                                              |
| `next_offset`   | Entry index to pass as `offset` to continue paginating. `null` if no more entries.                   |
| `content_hash`  | Truncated SHA-256 (12 hex chars) of the full page content. Compare across paginated calls to detect if the underlying page changed. |
| `cached`        | Whether served from cache.                                                                           |
| `cached_at`     | ISO 8601 timestamp (UTC) of when the page was originally fetched. `null` if not cached.              |
| `stale`         | `true` if the cache entry has expired and a background refresh has been triggered. Content is stale but usable. Defaults to `false`. |

**Notes**:

- Shares the same cache as `read_page` and `search_page`.
- Empty fences (fence pairs with no headings inside) are stripped since they provide no navigational value.
- If `offset` > `total_entries`, returns an empty outline string with correct `total_entries` — not an error.
- The `line_number` in each entry corresponds to the line in the page content — pass it as `offset` to `read_page` to jump to that section.

---

## 5. Transport Modes

ProContext supports two transport modes. The same MCP tools are available in both modes.

> **`<data_dir>`** refers to the platform-specific data directory resolved by `platformdirs.user_data_dir("procontext")`: `~/.local/share/procontext` on Linux, `~/Library/Application Support/procontext` on macOS, `C:\Users\<user>\AppData\Local\procontext` on Windows.

### 5.1 stdio Transport

The default mode for local development. The MCP client (e.g., Claude Code, Cursor) spawns ProContext as a subprocess and communicates over stdin/stdout using the MCP JSON-RPC protocol.

**Characteristics**:

- No network exposure — entirely local
- Process lifecycle managed by the MCP client
- Registry loaded from local disk when a valid local registry pair exists (`<data_dir>/registry/known-libraries.json` + `registry-state.json`). If no valid pair is found, the server attempts a one-time auto-setup (network fetch); if that also fails, it exits with an actionable error pointing to `procontext setup`.
- SQLite database at `cache.db_path` (default: `platformdirs.user_data_dir("procontext")/cache.db`, configurable independently from `data_dir`)
- No authentication required

**Configuration** (in MCP client settings):

```json
{
  "mcpServers": {
    "procontext": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/procontext", "procontext"]
    }
  }
}
```

> **Note**: Once published to PyPI, this simplifies to `"command": "uvx", "args": ["procontext"]`. Until then, use the `uv run` form above.

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
  host: "127.0.0.1"
  port: 8080
  auth_enabled: false
  auth_key: ""
```

---

## 6. Library Registry

The library registry (`known-libraries.json`) is the data backbone of ProContext. It is hosted on GitHub Pages and updated weekly. The MCP server consumes it — it never modifies it.

**Registry update cadence**: Weekly automated builds. Registry updates are independent of MCP server releases.

**Custom registry**: The registry metadata endpoint is configurable. Point `registry.metadata_url` in `procontext.yaml` at any HTTP endpoint that serves the expected metadata JSON (including `download_url`) to use a private registry. See D6 in Section 10 for details.

**At server startup**:

1. Attempt to load local registry pair from `<data_dir>/registry/known-libraries.json` and `<data_dir>/registry/registry-state.json`
2. Validate the pair (`known-libraries.json` parses, `registry-state.json` parses, checksum matches)
3. If either file is missing or the pair is invalid: attempt a one-time auto-setup (network fetch of registry). If auto-setup also fails, the server exits with an error message pointing to `procontext setup`.
4. In the background: check the configured registry metadata endpoint for a newer version and download if available. The updated registry is used on the next server start (stdio) or atomically swapped in-memory in HTTP long-running mode (registry indexes + SSRF allowlist updated together).

**Local state sidecar** (`registry-state.json`):

- Stores metadata for the currently active local registry copy: `version`, `checksum`, `updated_at`, `last_checked_at`
- `updated_at` is written whenever a background registry update is accepted (new version downloaded)
- `last_checked_at` is written after every successful update check — even when the registry is already current — and is used to gate the startup check in stdio mode (see below)
- Is persisted atomically with `known-libraries.json` as a consistency unit (temp file + fsync + atomic rename)
- Is used as the source of truth for `registry_version` on startup when loading from disk

**Update scheduling policy**:

- At startup in stdio mode, the one-time registry update check is **gated by `last_checked_at`**: if the state file shows a check was performed within the configured `poll_interval_hours`, the startup check is skipped. In HTTP long-running mode, the scheduler performs an immediate initial check (unless explicitly delayed by startup skip conditions).
- In HTTP long-running mode, successful checks follow a steady 24-hour cadence
- In HTTP long-running mode, **transient** failures (network timeout/DNS/connection issues, upstream 5xx) retry with exponential backoff (starting at 1 minute, capped at 60 minutes, with jitter)
- In HTTP long-running mode, after `8` consecutive transient failures, the failure counter and backoff reset, and checks return to 24-hour cadence. The next round gets a fresh set of fast-retry attempts.
- In HTTP long-running mode, **semantic** failures (invalid metadata shape, checksum mismatch, registry schema parse errors) do not fast-retry; they log and return to the normal 24-hour cadence
- In stdio mode, no post-startup retries are scheduled because the process is short-lived

**In-memory indexes** (rebuilt from registry on each load, <100ms for 1,000 entries):

- Package name → library ID (many-to-one): `"langchain-openai"` → `"langchain"`
- Library ID → full registry entry (one-to-one)
- Alias → library ID (exact alias lookup, e.g. `"torch"` → `"pytorch"`)
- Library ID + alias corpus for fuzzy matching (rapidfuzz, 70% threshold)

These four indexes serve all `resolve_library` lookups. No database reads during resolution.

---

## 7. Documentation Fetching & Caching

### Fetching

All documentation is fetched via plain HTTP GET. ProContext uses `httpx` with:

- Manual redirect handling (each redirect target is validated against the SSRF allowlist before following)
- Configurable connect timeout (default: 5 seconds) and read timeout (default: 30 seconds); see `fetcher.connect_timeout_seconds` and `fetcher.request_timeout_seconds`
- Maximum 3 redirect hops

### Cache

A single SQLite database stores all fetched content at `cache.db_path` (default: `platformdirs.user_data_dir("procontext")/cache.db`).

| Table        | Key                  | Content                                       | TTL      |
| ------------ | -------------------- | --------------------------------------------- | -------- |
| `page_cache` | `page:{sha256(url)}` | Full page markdown (llms.txt, README, or docs) | 24 hours |

All fetched content — llms.txt indexes, README files, and documentation pages — is stored in a single `page_cache` table. Both `read_page` and `search_page` share this cache: a page fetched by one tool is immediately available to the other without a re-fetch.

**Stale-while-revalidate**: When a cached entry is past its TTL, the stale content is returned immediately with `stale: true`, and a background task is spawned to re-fetch and update the cache. The next call to the same URL will get the fresh content if the background refresh has completed. Guards prevent redundant work: an in-memory set tracks in-flight refreshes (no duplicate tasks for the same URL), and a `last_checked_at` timestamp enforces a 15-minute cooldown between refresh attempts.

**Content hash**: Every response from `read_page`, `read_outline`, and `search_page` includes a `content_hash` field — a truncated SHA-256 (12 hex chars) of the full page content. Agents paginating through a page can compare `content_hash` across calls to detect if a background refresh updated the underlying content between paginated reads. If the hash changes, the agent should restart from `offset=1`.

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

`read_page` and `search_page` accept arbitrary URLs from the agent. To prevent Server-Side Request Forgery:

- All URLs are validated against an allowlist of permitted domains before fetching
- The allowlist is populated at startup from the registry (all `docs_url` and `llms_txt_url` domains) plus any configured `extra_allowed_domains`
- **Allowlist expansion** is controlled by a two-value setting (`allowlist_expansion`):
  - `"registry"` (default): allowlist is fixed at startup — only registry domains and `extra_allowed_domains`
  - `"discovered"`: domains found in any fetched content (llms.txt indexes, documentation pages) are added to the allowlist at runtime. Expansion is monotonic (domains are only added, never removed) and resets to the registry baseline on each registry update.
- In HTTP long-running mode, when a background registry update is accepted, the allowlist is rebuilt from the new registry and atomically swapped with the new indexes
- Redirects are followed manually — each redirect target is re-validated before following
- Private IP ranges (`10.x`, `172.16.x`, `192.168.x`, `127.x`, `::1`, `fc00::/7`) are always blocked, regardless of allowlist

### Input Validation

- All tool inputs are validated with Pydantic before processing
- String inputs are trimmed and length-capped (resolve_library query: 500 chars, search_page query: 200 chars, URL: 2048 chars)
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
    "code": "PAGE_NOT_FOUND",
    "message": "HTTP 404: page not found at 'https://docs.example.com/missing-page.md'.",
    "suggestion": "Check the URL is correct. Use resolve_library to find valid documentation URLs.",
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

| Code                    | Tool                            | `recoverable` | Description                                                                           |
| ----------------------- | ------------------------------- | ------------- | ------------------------------------------------------------------------------------- |
| `PAGE_NOT_FOUND`        | `read_page`, `search_page`, `read_outline` | `false`       | HTTP 404 — the page does not exist at that URL                                        |
| `PAGE_FETCH_FAILED`     | `read_page`, `search_page`, `read_outline` | `true`        | Transient network error or non-200/404 HTTP response fetching page; retry may succeed |
| `TOO_MANY_REDIRECTS`    | `read_page`, `search_page`, `read_outline` | `false`       | Redirect chain exceeded the 3-hop safety limit                                        |
| `URL_NOT_ALLOWED`       | `read_page`, `search_page`, `read_outline` | `false`       | URL domain not in SSRF allowlist; only a different URL will succeed                   |
| `INVALID_INPUT`         | Any                             | `false`       | Input validation failed; the request must be corrected before retrying                |

---

## 10. Design Decisions

**D1: Agent-driven navigation**
ProContext does not chunk documents or decide which content is relevant. The agent navigates the documentation structure — it resolves a library, browses its index, searches for keywords, and reads specific sections. This is simpler, more predictable, and gives the agent full visibility into what documentation exists.

_Trade-off_: Agents need 2–3 tool calls to reach content instead of 1. Accepted — the calls are fast (mostly cache hits after the first) and the agent retains full control. The `search_page` tool shortens this path when the agent knows what it's looking for.

**D2: Single SQLite cache tier**
A two-tier cache (memory + SQLite) adds meaningful complexity for marginal latency gain in single-user deployments. SQLite with WAL mode delivers <5ms reads, which is acceptable when the bottleneck is network fetch (100ms–3s). A memory tier can be added in the enterprise version where multi-user throughput justifies it.

**D3: Optional bearer key for HTTP mode**
Stdio mode requires no authentication — the MCP client spawns the server, and the transport is a local pipe. HTTP mode includes optional bearer key authentication controlled by `server.auth_enabled`. If `auth_enabled=true`, all requests must include a matching `Authorization: Bearer <key>` header or receive HTTP 401. If `auth_enabled=true` and `auth_key` is empty, a key is auto-generated and logged at startup. If `auth_enabled=false`, authentication is disabled by default and a warning is logged on startup. This is lightweight access control for shared-network deployments, not a full auth system — there is no key rotation, hashing, or revocation.

**D4: Registry independence from server version**
The registry (`known-libraries.json`) has its own release cadence (weekly) completely decoupled from the MCP server version. Users get updated library coverage without upgrading the server.

**D5: llms.txt as the documentation contract**
ProContext treats the llms.txt file as the authoritative interface to a library's documentation. It does not scrape HTML, parse Sphinx output, or infer documentation structure. Every library in the registry has a valid llms.txt URL — the MCP server only deals with fetching and serving that format. The llms.txt is fetched via `read_page` like any other page, benefiting from the same caching, pagination, and search capabilities.

**D6: Custom registry as the escape hatch for private documentation**
Teams with internal libraries or private documentation can point ProContext at a custom registry by setting `registry.metadata_url` in `procontext.yaml`:

```yaml
registry:
  metadata_url: "https://docs.internal.example.com/procontext/registry_metadata.json"
```

The custom registry must serve:

- **`known-libraries.json`**: An array of library entries in the same schema as the public registry. Each entry must include a valid `llms_txt_url`.
- **`registry_metadata.json`**: A JSON object with `version` (string), `download_url` (string), and `checksum` (`"sha256:<hex>"`) fields so the server's background update check works correctly.

**Important**: The SSRF allowlist is built from domains in the loaded registry. Documentation domains in a custom registry entry are automatically permitted by `read_page`, `search_page`, and `read_outline` — no additional SSRF configuration is needed.

_Trade-off_: The custom registry completely replaces the public registry — there is no merging. Teams that want both public and private libraries must include the public entries in their custom registry. This is intentional: a merge strategy introduces ordering and conflict-resolution complexity that is not warranted for the open-source version.

**D7: Outline compaction and the read_outline tool**
Large documentation pages (16K+ lines) produce outlines with 2000+ entries. Returning the full outline on every `read_page` and `search_page` call wastes tokens and provides no usable navigation for the agent. Compaction progressively removes lower-priority entries (H6 → H5 → fenced content → H4 → H3) until the outline fits within 50 entries. When even H1/H2 exceed 50, a status message directs the agent to `read_outline` for paginated access. `search_page` additionally trims the outline to the match range before compaction, so the agent only sees structural context around its search results.

`read_outline` is a separate tool (not a `view` parameter on `read_page`) because outline pagination uses entry indices while content pagination uses line numbers — overloading the same `offset`/`limit` parameters with different semantics depending on mode would be confusing and error-prone.

_Trade-off_: The compacted outline may omit the exact heading an agent needs, requiring a follow-up `read_outline` call. Accepted — this is strictly better than the alternative (returning 2000 entries of outline on every call) both for token efficiency and navigation usability.
