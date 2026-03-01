# Roadmap

> **Note for contributors**: This file is maintained by the core team and is not open to direct edits via pull request. It reflects decisions that have already been discussed and committed to. If you'd like to propose something — a new feature, a missing library, or a direction you think the project should take — open a [GitHub Issue](https://github.com/procontexthq/procontext/issues). Proposals that are well-reasoned and consistent with the project's goals will be considered and, if accepted, added here.

## What's in v0.1.0

The initial release ships a complete, production-ready MCP server:

- **`resolve_library`** — resolves a library name or pip specifier to a known documentation source via fuzzy matching against a curated registry
- **`get_library_docs`** — fetches the llms.txt table of contents for a library with stale-while-revalidate caching
- **`read_page`** — fetches a documentation page with offset/limit windowing and a full heading map for section navigation
- **stdio transport** — default; process lifecycle managed by the MCP client
- **HTTP transport** — MCP Streamable HTTP (spec 2025-11-25) with security middleware (bearer auth, origin validation, protocol version checks)
- **SQLite cache** — 24-hour TTL, WAL mode, stale-while-revalidate, background refresh
- **SSRF protection** — domain allowlist derived from the registry, private IP blocking on every redirect hop
- **Background registry updates** — checks for registry updates at startup and (HTTP mode) on a 24-hour interval
- **Cross-platform** — config and data paths resolve automatically on Linux, macOS, and Windows

## What's next

No features are currently planned for v0.2. Future work will be driven by issues, community feedback, and registry growth. Candidates include:

- Expanded registry coverage (more libraries, MCP servers, frameworks)
- Docker image for HTTP transport deployments
- Support for additional documentation formats beyond llms.txt
- Performance improvements for high-concurrency HTTP deployments
- SLSA provenance attestation on releases (`actions/attest-build-provenance`) — cryptographic proof that a published artifact was built from a specific source commit

## Design decisions

The project follows a spec-first approach — significant changes are designed in [`docs/specs/`](docs/specs/) before implementation begins. If you want to contribute to a future direction, open a discussion first.
