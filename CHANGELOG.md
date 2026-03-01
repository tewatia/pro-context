# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`procontext setup` command** — one-time CLI command that downloads and
  persists the registry to the platform data directory. Run this after
  installing before starting the server for the first time.
- **Auto-setup on first run** — if no local registry is found at startup, the
  server attempts a one-time fetch automatically before failing with an
  actionable error message pointing to `procontext setup`.
- **New configurable settings** — fetch timeout, fuzzy match score cutoff,
  fuzzy max results, and registry poll interval are now exposed via
  `procontext.yaml` or `PROCONTEXT__*` environment variables.
- **`last_checked_at` field in `registry-state.json`** — written after every
  successful update check (even when the registry is already current). In stdio
  mode, the startup check is skipped if this timestamp is within the configured
  `poll_interval_hours`, avoiding redundant metadata fetches on frequent
  restarts.

### Changed

- **Bundled registry snapshot removed** — the server no longer ships with an
  embedded registry. Use `procontext setup` to initialise the registry before
  first use (or let the auto-setup fallback handle it on the first run).
- **HTTP requests use split connect/read timeouts** — network requests now apply
  separate connect and read timeouts instead of a single wall-clock timeout,
  giving more predictable behaviour on slow or unreliable connections.

### Fixed

- **Config typos now fail loudly at startup** — unknown fields in
  `procontext.yaml` are rejected with a clear, human-readable error message
  rather than being silently ignored.

### Security

- **HTTP server binds to `127.0.0.1` by default** — `server.host` has changed
  from `0.0.0.0` to `127.0.0.1`. The server no longer listens on all network
  interfaces unless explicitly configured. Users who need network-wide access
  must set `server.host: 0.0.0.0` in `procontext.yaml` or via
  `PROCONTEXT__SERVER__HOST=0.0.0.0`.
- **SLSA provenance attestation on releases** — release artifacts are now signed
  with SLSA provenance attestations, enabling build provenance verification.

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
