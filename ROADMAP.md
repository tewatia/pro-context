# Roadmap

> **Note for contributors**: This file is maintained by the core team and reflects decisions that have been discussed and committed to. It is not open to direct edits via pull request. To propose a feature, new library, or direction — open a [GitHub Discussion](https://github.com/procontexthq/procontext/discussions) or a [GitHub Issue](https://github.com/procontexthq/procontext/issues). Well-reasoned proposals consistent with the project's goals will be considered and, if accepted, added here.

---

## Where we are — v0.1.0

v0.1.0 ships a complete, production-ready MCP server. The core loop works: an agent resolves a library name, fetches its llms.txt table of contents, and reads specific documentation pages — all from a curated, pre-validated registry with SSRF protection and a stale-while-revalidate cache.

- **`resolve_library`** — resolves a library name or pip specifier to a known documentation source via fuzzy matching against a curated registry
- **`get_library_docs`** — fetches the llms.txt table of contents for a library with stale-while-revalidate caching
- **`read_page`** — fetches a documentation page with offset/limit windowing and a full heading map for section navigation
- **stdio transport** — default; process lifecycle managed by the MCP client
- **HTTP transport** — MCP Streamable HTTP (spec 2025-11-25) with security middleware (bearer auth, origin validation, protocol version checks)
- **SQLite cache** — 24-hour TTL, WAL mode, stale-while-revalidate, background refresh
- **SSRF protection** — domain allowlist derived from the registry, private IP blocking on every redirect hop
- **Background registry updates** — checks for registry updates at startup and (HTTP mode) on a 24-hour interval
- **Cross-platform** — config and data paths resolve automatically on Linux, macOS, and Windows

---

## What's next

The core server is solid. Future work focuses on three areas: expanding what the server knows, where it can run, and how well it helps agents navigate documentation.

### Registry coverage

The value of ProContext scales directly with the breadth and quality of the registry. Expanding coverage — more libraries, MCP servers, AI frameworks, and ecosystem tooling — is the highest-leverage work. Registry contributions are maintained separately at [procontexthq/procontexthq.github.io](https://github.com/procontexthq/procontexthq.github.io).

### Deployment

- **PyPI release** — `uvx procontext` as a first-class install path, no git clone required
- **Docker image** — official image for HTTP transport deployments; the most-requested path for shared team and self-hosted setups

### Tool quality

- **Validate the `read_page` default line limit** — empirically test against real-world documentation pages to determine whether the current 2000-line default is too generous and whether a smaller window (e.g. 300–500 lines) improves agent navigation by making the heading map and pagination more meaningful
- **Additional documentation formats** — as the ecosystem evolves, the server should serve documentation from formats that emerge alongside or complement llms.txt

### Performance

- Improvements for high-concurrency HTTP deployments — connection pooling, response streaming, and load testing at scale

---

## How we decide what to build

ProContext follows a spec-first development process. Significant changes are designed in [`docs/specs/`](docs/specs/) before any code is written — this keeps the architecture intentional and makes it easier for contributors to understand why things work the way they do.

Priority order: things that make the server more useful to agents today, then things that make it easier to deploy and operate, then developer experience improvements. Features that don't serve the agent-first use case don't belong here regardless of how popular the request is.

If you want to influence the roadmap, open a [discussion](https://github.com/procontexthq/procontext/discussions) before opening a PR.
