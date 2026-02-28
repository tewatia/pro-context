# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-02-28

### Added

- **Registry & Resolution** — bundled snapshot of known libraries, startup load
  with SHA-256 checksum validation, atomic disk persistence, and background
  update checks against a hosted registry. Fuzzy name/alias matching via
  rapidfuzz (70 % threshold) with pip-specifier normalisation. `resolve_library`
  MCP tool.
- **Documentation fetcher** — httpx-based async fetcher with per-hop SSRF
  validation (private-IP blocking + domain allowlist derived from the registry).
  Manual redirect handling validates each hop before following. Configurable
  allowlist depth (0 = registry only, 1 = expand from llms.txt links,
  2 = expand from page links). Extra trusted domains configurable via
  `procontext.yaml`.
- **SQLite cache** — stale-while-revalidate cache (`toc_cache`, `page_cache`)
  with a 24-hour TTL. WAL mode. Stores `discovered_domains` per entry for
  cross-restart allowlist restoration. Periodic cleanup of entries expired more
  than 7 days ago, gated by a `server_metadata` timestamp to avoid redundant
  runs on frequent restarts.
- **`get_library_docs` tool** — fetches the llms.txt table of contents for a
  resolved library, with stale-while-revalidate background refresh.
- **Heading parser** — extracts H1–H4 headings with 1-based line numbers from
  fetched markdown pages.
- **`read_page` tool** — fetches a documentation page with offset/limit windowing
  and a full heading map, enabling agents to jump directly to relevant sections.
- **stdio transport** — default transport; process lifecycle managed by the MCP
  client. No authentication required.
- **HTTP transport** — MCP Streamable HTTP (spec 2025-11-25) via FastMCP +
  uvicorn. `MCPSecurityMiddleware` (pure ASGI) enforces optional bearer key
  authentication, localhost-only origin validation (DNS rebinding protection),
  and protocol version validation. Auto-generated bearer keys are logged to
  stderr on startup and not persisted.
- **Configuration** — `procontext.yaml` + `PROCONTEXT__*` environment variable
  overrides via pydantic-settings. Platform-aware data/config paths via
  platformdirs.
- **Structured logging** — JSON or text output to stderr via structlog. stdout
  is reserved for the MCP JSON-RPC stream in stdio mode.

[Unreleased]: https://github.com/procontexthq/procontext/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/procontexthq/procontext/releases/tag/v0.1.0
