# Contributing to Pro-Context

Thank you for your interest in contributing. This guide covers everything you need to get started.

---

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — used for dependency management, virtual environments, and running the project

---

## Setup

```bash
git clone https://github.com/tewatia/pro-context.git
cd pro-context
uv sync --dev
```

This creates a virtual environment and installs all runtime + dev dependencies.

Verify the setup:

```bash
uv run ruff check src/        # Lint
uv run ruff format --check src/  # Format check
uv run pyright src/            # Type check
uv run pytest                  # Tests
```

---

## Development Workflow

### 1. Pick something to work on

- Check [open issues](https://github.com/tewatia/pro-context/issues) for bugs or feature requests.
- Check the [Implementation Roadmap](README.md#implementation-roadmap) for the current phase.
- Suggest libraries or MCP servers for the curated registry.
- Review the specs in [`docs/specs/`](docs/specs/) and open issues for anything unclear or inconsistent.

If you're unsure whether a change is wanted, open an issue first to discuss it.

### 2. Create a branch

```bash
git checkout -b <type>/<short-description>
```

Branch naming convention:

| Prefix | Use for |
|--------|---------|
| `feat/` | New features |
| `fix/` | Bug fixes |
| `docs/` | Documentation changes |
| `refactor/` | Code restructuring without behaviour change |
| `test/` | Adding or improving tests |
| `chore/` | Build, CI, tooling changes |

### 3. Make your changes

Before writing code, read the relevant spec documents — the project follows a spec-first approach:

- [Functional Specification](docs/specs/01-functional-spec.md) — what the tools do
- [Technical Specification](docs/specs/02-technical-spec.md) — how they work internally
- [Implementation Guide](docs/specs/03-implementation-guide.md) — project structure, conventions, phase details
- [API Reference](docs/specs/04-api-reference.md) — wire format, error codes
- [Security Specification](docs/specs/05-security-spec.md) — threat model, security controls

See the [Coding Conventions](#coding-conventions) section below for the rules that matter most.

### 4. Run all checks before pushing

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run pyright src/
uv run pytest
```

All four must pass. CI runs the same checks — a PR with failures will not be reviewed.

### 5. Commit and push

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>[optional scope]: <description>

[optional body]

[optional footer: BREAKING CHANGE: <description>]
```

**Types**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Examples:

```
feat(resolver): add fuzzy matching with rapidfuzz

fix(cache): handle aiosqlite.Error on write without crashing

docs: update security spec with bearer key auth

BREAKING CHANGE: rename resolve_library() to resolve()
```

Breaking changes **must** include `BREAKING CHANGE:` in the commit footer — this drives major version bumps and changelog entries.

### 6. Open a pull request

- Target the `main` branch.
- Describe what changed and why.
- Reference any related issue (e.g., `Closes #12`).
- If the PR introduces new behaviour, include the relevant test cases.

---

## Coding Conventions

These are the conventions that trip people up. Standard Python practices (PEP 8, type hints, etc.) are assumed.

### Architecture

- **AppState injection** — All shared state lives in `AppState`, created once at startup. Tool handlers receive it as a plain argument. No global variables, no module-level singletons. See [03-implementation-guide.md, Section 3.3](docs/specs/03-implementation-guide.md#33-appstate-and-dependency-injection).

- **Protocol interfaces** — Swappable components (`Cache`, `Fetcher`) are typed against `typing.Protocol`, not concrete classes. This enables test doubles without mocking frameworks.

- **Layering** — Tools import from services, services import from shared. Never the reverse. If a tool needs to import from `cache.py` directly, something is wrong.

### Error handling

- **Raise `ProContextError`, never return error dicts.** Tool handlers raise; `server.py` catches and serialises. See [03-implementation-guide.md, Section 3.4](docs/specs/03-implementation-guide.md#34-error-handling).

### Code style

- **`from __future__ import annotations`** in every module. Type-only imports go inside `if TYPE_CHECKING:` blocks.
- **`X | None`** union syntax, not `Optional[X]`.
- **pyright** is the type checker (not mypy). Standard mode is enforced.
- **ruff** handles linting and formatting. Line length is 100.
- **No `print()` in server code** — stdout is owned by the MCP JSON-RPC stream in stdio mode. Use `structlog` (which writes to stderr).

### Testing

- **pytest + pytest-asyncio** with `asyncio_mode = "auto"`.
- **respx** for HTTP mocking. Never make real network calls in tests.
- **In-memory SQLite** per test — no shared database state.
- **Unit tests** (`tests/unit/`) test internal functions directly. May break during refactoring.
- **Integration tests** (`tests/integration/`) test the full tool pipeline. Must not break on internal refactoring.

See [03-implementation-guide.md, Section 5](docs/specs/03-implementation-guide.md#5-testing-strategy) for the full testing strategy.

### Library-specific guidelines

This project follows additional guidelines for public library development covering API design, error handling, versioning, supply chain security, and adoptability. See [`docs/coding-guidelines.md`](docs/coding-guidelines.md).

---

## Project Structure

```
src/pro_context/
├── server.py          # FastMCP instance, lifespan, tool registration, entrypoint
├── state.py           # AppState dataclass
├── config.py          # Settings via pydantic-settings + YAML
├── errors.py          # ErrorCode, ProContextError
├── protocols.py       # CacheProtocol, FetcherProtocol
├── models/            # Pydantic models (registry, cache, tools)
├── tools/             # One file per MCP tool (business logic only)
├── registry.py        # Registry loading, index building
├── resolver.py        # Resolution algorithm, fuzzy matching
├── fetcher.py         # HTTP client, SSRF protection
├── cache.py           # SQLite cache
├── parser.py          # Heading parser
├── transport.py       # MCPSecurityMiddleware for HTTP mode
└── data/              # Bundled registry snapshot
```

See [03-implementation-guide.md, Section 1](docs/specs/03-implementation-guide.md#1-project-structure) for module responsibilities and layering rules.

---

## Questions?

- Open a [GitHub Discussion](https://github.com/tewatia/pro-context/discussions) for design questions or ideas.
- Open a [GitHub Issue](https://github.com/tewatia/pro-context/issues) for bugs or concrete feature requests.
