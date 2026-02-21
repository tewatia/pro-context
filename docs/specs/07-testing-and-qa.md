# Pro-Context: Testing & Quality Assurance

> **Document**: 07-testing-and-qa.md
> **Status**: Draft v1
> **Last Updated**: 2026-02-20
> **Depends on**: 03-technical-spec.md (v2), 04-implementation-guide.md (v1)

---

## Table of Contents

- [1. Testing Strategy](#1-testing-strategy)
  - [1.1 Test Pyramid Overview](#11-test-pyramid-overview)
  - [1.2 Mocking External Dependencies](#12-mocking-external-dependencies)
  - [1.3 Performance Testing](#13-performance-testing)
  - [1.4 MCP Client Compatibility Testing](#14-mcp-client-compatibility-testing)
  - [1.5 Smoke Tests](#15-smoke-tests)
- [2. CI Pipeline Design](#2-ci-pipeline-design)
  - [2.1 Pipeline Stages](#21-pipeline-stages)
  - [2.2 CI Triggers](#22-ci-triggers)
  - [2.3 Required Checks](#23-required-checks)
  - [2.4 Optional Checks](#24-optional-checks)
  - [2.5 CI Environment](#25-ci-environment)
- [3. Code Review and PR Workflow](#3-code-review-and-pr-workflow)
  - [3.1 Branch Strategy](#31-branch-strategy)
  - [3.2 Pull Request Requirements](#32-pull-request-requirements)
  - [3.3 Review Process](#33-review-process)
  - [3.4 Branch Protection Rules](#34-branch-protection-rules)
  - [3.5 Merge Strategy](#35-merge-strategy)
- [4. Definition of Done](#4-definition-of-done)
  - [4.1 Per-Phase Completion Criteria](#41-per-phase-completion-criteria)
  - [4.2 Release Readiness Checklist](#42-release-readiness-checklist)

---

## 1. Testing Strategy

This section defines the strategic testing approach for Pro-Context. For implementation-level details (test file layout, per-component mock strategy, pytest configuration), see `04-implementation-guide.md` Section 5.

### 1.1 Test Pyramid Overview

The test pyramid from `04-implementation-guide.md` Section 5.1 defines three tiers:

| Tier | Count | Speed | Scope |
|------|-------|-------|-------|
| Unit | 30–50 | Fast (<1s each) | Individual functions, pure logic, no I/O |
| Integration | 5–8 | Medium (<5s each) | Multi-component flows, real SQLite, mocked network |
| E2E | 2–3 | Slow (<30s each) | Full MCP client ↔ server via stdio/HTTP |

**Guiding principle**: If a bug can be caught by a unit test, don't write an integration test for it. Reserve integration and E2E tests for verifying cross-component behavior that unit tests cannot cover.

### 1.2 Mocking External Dependencies

Pro-Context makes outbound HTTP requests to three types of external services: llms.txt documentation sources, PyPI API (builder only — not runtime), and GitHub API (builder only). All outbound HTTP is done via `httpx.AsyncClient`, which enables clean mocking with `respx`.

#### 1.2.1 Mock Library: `respx`

[`respx`](https://github.com/lundberg/respx) is an httpx-compatible HTTP mock library. It intercepts requests at the transport layer, so the application code doesn't need modification.

**Add to dev dependencies:**

```toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "respx>=0.21.0,<1.0.0",
]
```

#### 1.2.2 Fixture Patterns

**Shared conftest fixture for mocking all outbound HTTP:**

```python
# tests/conftest.py
import respx
import httpx
import pytest

@pytest.fixture
def mock_http():
    """Mock all outbound HTTP. Tests must explicitly define expected routes."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as respx_mock:
        yield respx_mock

@pytest.fixture
def mock_llms_txt(mock_http):
    """Pre-configured mock for a typical llms.txt response."""
    mock_http.get("https://docs.example.com/llms.txt").mock(
        return_value=httpx.Response(200, text=(
            "# Example Library\n"
            "> A test library for unit testing.\n"
            "\n"
            "## Sections\n"
            "\n"
            "- [Getting Started](https://docs.example.com/getting-started)\n"
            "- [API Reference](https://docs.example.com/api)\n"
        ))
    )
    return mock_http
```

**Per-test route setup (preferred for targeted tests):**

```python
@pytest.mark.unit
async def test_fetcher_handles_404(mock_http):
    mock_http.get("https://docs.example.com/llms.txt").mock(
        return_value=httpx.Response(404)
    )
    # ... test that fetcher raises SourceUnavailableError ...
```

**Key rules:**
- `assert_all_mocked=True` — any unmocked URL raises an error. This prevents tests from making real network requests.
- Use `assert_all_called=False` by default — not every mock route needs to be hit in every test. Set to `True` when testing specific request flows.

#### 1.2.3 VCR-Style Cassette Recording (Integration Tests)

For integration tests that verify real HTTP response parsing, use recorded cassettes rather than hand-crafted mocks. This ensures tests break when the external API format changes.

**Library**: [`pytest-recording`](https://github.com/kiwicom/pytest-recording) (VCR.py wrapper for pytest)

```toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "pytest-recording>=0.13.0,<1.0.0",
]
```

**Usage:**

```python
@pytest.mark.integration
@pytest.mark.vcr
async def test_fetch_real_langchain_toc():
    """Verify TOC parsing against real LangChain llms.txt format."""
    # First run: makes real HTTP request, records to cassette
    # Subsequent runs: replays from cassette
    fetcher = LlmsTxtFetcher(...)
    toc = await fetcher.fetch_toc("https://python.langchain.com/llms.txt")
    assert len(toc.sections) > 0
```

**Cassette management:**
- Store cassettes in `tests/cassettes/` (gitignored for size; committed selectively for critical paths)
- Re-record monthly or when tests start failing due to format changes
- CI always replays from cassettes — never makes real requests

#### 1.2.4 In-Memory SQLite for Database Tests

All tests that touch the database use in-memory SQLite (`":memory:"` or `sqlite+aiosqlite:///:memory:`). This avoids filesystem side effects and is faster than file-based databases.

```python
@pytest.fixture
async def db():
    """In-memory SQLite database with schema applied."""
    async with aiosqlite.connect(":memory:") as conn:
        await apply_schema(conn)  # Run CREATE TABLE statements
        yield conn
```

### 1.3 Performance Testing

Performance testing verifies that Pro-Context meets the latency SLOs defined in `03-technical-spec.md` Section 8.1.

#### 1.3.1 Latency Targets (From Technical Spec)

| Tool | Cache hit (P95) | Cache miss (P95) |
|------|-----------------|-------------------|
| `resolve-library` | <10ms | N/A (in-memory only) |
| `get-library-info` | <50ms | <3s |
| `get-docs` | <100ms | <5s |
| `search-docs` | <200ms | N/A (requires prior indexing) |
| `read-page` | <50ms | <3s |

These are **pass/fail criteria**. Cache-hit benchmarks are measured with pre-warmed caches. Cache-miss benchmarks mock the HTTP response (so they measure processing time, not external network latency).

#### 1.3.2 Tooling: `pytest-benchmark`

```toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "pytest-benchmark>=4.0.0,<5.0.0",
]
```

**Example benchmark test:**

```python
@pytest.mark.benchmark
async def test_resolve_library_cache_hit(benchmark, loaded_registry):
    """resolve-library must respond in <10ms for cached registry lookups."""
    result = benchmark.pedantic(
        resolve_library,
        args=("langchain", loaded_registry),
        iterations=100,
        rounds=5,
    )
    assert benchmark.stats["median"] < 0.010  # 10ms

@pytest.mark.benchmark
async def test_search_docs_cache_hit(benchmark, indexed_corpus):
    """search-docs must respond in <200ms for BM25 queries."""
    result = benchmark.pedantic(
        search_docs,
        args=("streaming chat models", indexed_corpus),
        iterations=20,
        rounds=5,
    )
    assert benchmark.stats["stats"]["p95"] < 0.200  # 200ms — P95
```

#### 1.3.3 Regression Detection

- **Baseline**: After Phase 3 is complete (all tools functional), run the full benchmark suite and save results as the baseline (`pytest-benchmark --benchmark-save=baseline`).
- **Threshold**: CI fails if any P95 measurement regresses by more than **20%** compared to baseline.
- **Comparison**: `pytest-benchmark --benchmark-compare=baseline --benchmark-compare-fail=min:20%`

#### 1.3.4 When Performance Tests Run

Performance tests are expensive and nondeterministic on shared CI runners. They do **not** run on every PR.

| Trigger | Performance tests run? |
|---------|----------------------|
| PR to `main` | No |
| Push to `main` | No |
| Nightly schedule | Yes |
| Pre-release tag (`v*`) | Yes |
| Manual trigger (`workflow_dispatch`) | Yes |

Developers can run benchmarks locally: `uv run pytest -m benchmark --benchmark-only`

### 1.4 MCP Client Compatibility Testing

Pro-Context must work with real MCP clients. These tests cannot be automated in CI because they depend on external client software.

#### 1.4.1 Test Matrix

| Client | Transport | Test Environment |
|--------|-----------|-----------------|
| Claude Code (CLI) | stdio | Local terminal |
| Cursor | stdio | Cursor IDE with MCP config |
| Windsurf | stdio | Windsurf IDE with MCP config |
| Custom HTTP client | Streamable HTTP | `curl` or test script against HTTP server |

#### 1.4.2 Manual Test Checklist

Run before each minor/major release:

- [ ] Client connects via stdio and completes `initialize` handshake
- [ ] `resolve-library` returns results for a known library (e.g., "langchain")
- [ ] `resolve-library` returns fuzzy matches for a misspelled name (e.g., "langchan")
- [ ] `get-library-info` returns TOC with sections
- [ ] `get-docs` returns markdown content with relevant chunks
- [ ] `search-docs` returns ranked results with snippets
- [ ] `read-page` returns page content with `hasMore` for large pages
- [ ] `read-page` with `offset` returns content from the correct position
- [ ] Health resource returns valid JSON
- [ ] Session resource tracks resolved libraries across calls
- [ ] Server handles rapid successive calls without errors
- [ ] Server shuts down cleanly when client disconnects

#### 1.4.3 HTTP Mode Additional Checks

- [ ] Server starts on configured port
- [ ] Unauthenticated request returns 401
- [ ] Valid API key authenticates successfully
- [ ] Rate limiting returns 429 with `Retry-After` header
- [ ] CORS preflight returns correct headers

### 1.5 Smoke Tests

Smoke tests are a minimal subset of tests that verify the server is functional. They run on every PR and are the first gate in the CI pipeline.

**What smoke tests verify:**
1. Server starts without errors
2. Server responds to MCP `initialize` handshake
3. `tools/list` returns all 5 tools
4. `resources/list` returns both resources
5. `prompts/list` returns all 3 prompts
6. Each tool can be called with minimal valid input and returns a well-formed response

**Pytest marker:**

```python
@pytest.mark.smoke
async def test_server_starts_and_lists_tools(stdio_client):
    result = await stdio_client.call("tools/list")
    tool_names = {t["name"] for t in result["tools"]}
    assert tool_names == {
        "resolve-library",
        "get-library-info",
        "get-docs",
        "search-docs",
        "read-page",
    }
```

Add `"smoke: Smoke tests (minimal server functionality)"` to the pytest markers in `pyproject.toml`.

---

## 2. CI Pipeline Design

This section defines the CI strategy. For the concrete GitHub Actions YAML, see `04-implementation-guide.md` Section 6.3.

### 2.1 Pipeline Stages

The CI pipeline runs in sequential stages. Each stage must pass before the next begins.

```
┌─────────┐   ┌────────────┐   ┌────────────┐   ┌──────────────┐   ┌───────────────┐
│  Lint   │──▸│ Type Check │──▸│ Unit Tests │──▸│ Integration  │──▸│ Coverage Gate │
│ (ruff)  │   │  (mypy)    │   │  (pytest)  │   │   (pytest)   │   │  (≥80% stmts) │
└─────────┘   └────────────┘   └────────────┘   └──────────────┘   └───────────────┘
```

**Why sequential?** Early stages are fast and catch the majority of issues. Running lint before tests avoids wasting CI minutes on code that won't pass review anyway.

### 2.2 CI Triggers

| Event | Pipeline runs? |
|-------|---------------|
| Push to `main` | Yes — full pipeline |
| PR targeting `main` | Yes — full pipeline |
| Push to feature branch (no PR) | No — avoids redundant runs |
| Nightly schedule (cron) | Yes — full pipeline + performance benchmarks |
| Release tag (`v*`) | Yes — full pipeline + performance benchmarks + Docker build |

### 2.3 Required Checks (Must Pass Before Merge)

These checks are enforced by branch protection rules (Section 3.4). A PR cannot be merged if any required check fails.

| Check | Command | Failure means |
|-------|---------|--------------|
| Lint | `ruff check .` | Code style violations |
| Format | `ruff format --check .` | Unformatted code |
| Type check | `mypy src/` (strict mode) | Type errors |
| Unit tests | `pytest -m "unit or smoke"` | Failing tests |
| Integration tests | `pytest -m integration` | Cross-component failures |
| Coverage | `pytest --cov-fail-under=80` | Insufficient test coverage |

**Coverage thresholds** (from `04-implementation-guide.md` Section 5.4):
- Statements: ≥80%
- Branches: ≥75%

### 2.4 Optional Checks (Run But Don't Block Merge)

| Check | When | Purpose |
|-------|------|---------|
| Performance benchmarks | Nightly, pre-release | Detect latency regressions |
| E2E tests (stdio) | Nightly, pre-release | Full client-server flow |
| E2E tests (HTTP) | Nightly, pre-release | HTTP transport + auth flow |
| Docker build | Release tags | Verify image builds successfully |

Optional checks are reported in the PR but do not prevent merging. If an optional check fails on the nightly run, it is triaged as a bug and fixed before the next release.

### 2.5 CI Environment

| Component | Version/Tool |
|-----------|-------------|
| Runner | `ubuntu-latest` |
| Python | 3.12 |
| Package manager (primary) | uv (with `astral-sh/setup-uv@v1`) |
| Package manager (compatibility) | pip (separate job) |
| Cache | uv cache enabled via `enable-cache: true` |
| Timeout | 10 minutes per job |

Both uv and pip jobs run in parallel. The pip job ensures that users who don't use uv can still install and run Pro-Context.

---

## 3. Code Review and PR Workflow

### 3.1 Branch Strategy

`main` is the default and only long-lived branch. All work happens on short-lived feature branches.

| Branch pattern | Purpose | Example |
|---------------|---------|---------|
| `feature/<name>` | New functionality | `feature/search-docs-tool` |
| `fix/<name>` | Bug fixes | `fix/cache-eviction-race` |
| `docs/<name>` | Documentation changes | `docs/update-api-reference` |
| `chore/<name>` | Maintenance, deps, CI | `chore/update-ruff-config` |

**Rules:**
- Branch names use lowercase with hyphens (no underscores, no uppercase)
- One logical change per branch — don't bundle unrelated changes
- Delete branches after merge (GitHub auto-delete enabled)

### 3.2 Pull Request Requirements

Every PR must include:

1. **Descriptive title** — imperative mood, under 72 characters (e.g., "Add BM25 search engine with cross-library ranking")
2. **Summary** — what changed and why, in the PR body
3. **Link to related issue** — if one exists (use `Closes #N` or `Relates to #N`)
4. **All CI checks passing** — required checks from Section 2.3 must be green
5. **No unresolved review comments** — all review threads must be resolved before merge

**PR template** (`.github/pull_request_template.md`):

```markdown
## Summary
<!-- What changed and why? -->

## Changes
<!-- Bullet list of specific changes -->

## Testing
<!-- How was this tested? -->

## Checklist
- [ ] Tests added/updated for new functionality
- [ ] All CI checks pass
- [ ] No new warnings from ruff or mypy
- [ ] Documentation updated (if user-facing behavior changed)
```

### 3.3 Review Process

| Rule | Detail |
|------|--------|
| Minimum reviewers | 1 approving review required |
| Self-approval | Authors cannot approve their own PR |
| Review scope | Correctness, test coverage for new code, no regressions, follows coding conventions (`04-implementation-guide.md` Section 3) |
| Stale reviews | A new push to the PR branch dismisses previous approvals (re-review required) |
| Review response time | Best effort — no SLA, but reviewers should respond within 2 business days |

**What reviewers check:**

1. **Correctness** — Does the code do what the PR claims? Are there edge cases?
2. **Tests** — Is new code covered? Do tests actually verify behavior (not just run)?
3. **No regressions** — Do existing tests still pass? Is there new tech debt?
4. **Coding conventions** — Follows the conventions in `04-implementation-guide.md` Section 3 (naming, imports, error handling, type annotations)
5. **Security** — No hardcoded secrets, no new SSRF vectors, input validation present
6. **Performance** — No obviously expensive operations in hot paths (e.g., synchronous I/O in async handlers)

### 3.4 Branch Protection Rules

Applied to the `main` branch via GitHub repository settings:

| Rule | Setting |
|------|---------|
| Require pull request before merging | Enabled |
| Required approving reviews | 1 |
| Dismiss stale reviews on new push | Enabled |
| Require status checks to pass | Enabled |
| Required status checks | `lint`, `type-check`, `test-uv`, `test-pip` |
| Require branches to be up to date | Enabled |
| Restrict force push | Enabled (no force push to `main`) |
| Restrict deletions | Enabled (cannot delete `main`) |
| Allow squash merge | Enabled (default) |
| Allow merge commits | Enabled |
| Allow rebase merge | Disabled |
| Auto-delete head branches | Enabled |

### 3.5 Merge Strategy

| Scenario | Merge method | Rationale |
|----------|-------------|-----------|
| Single-commit PR | Squash merge | Clean linear history |
| Multi-commit PR (each commit meaningful) | Merge commit | Preserves commit history |
| Default | Squash merge | Most PRs are single logical changes |

**Squash merge commit message format:**

```
<PR title> (#<PR number>)

<PR body summary — first paragraph only>
```

GitHub enforces this via the "Default commit message" setting for squash merges: "Pull request title and description."

---

## 4. Definition of Done

### 4.1 Per-Phase Completion Criteria

Each phase has a verification checklist (defined in `04-implementation-guide.md` Sections 3.5–3.10). A phase is considered **done** when all of the following are satisfied:

| Criterion | Applies to | Detail |
|-----------|-----------|--------|
| Phase verification checklist complete | All phases | Every checkbox in the phase's checklist passes |
| All CI checks pass on `main` | All phases | Lint, type check, unit tests, integration tests, coverage gate |
| No open P0/P1 bugs for the phase | All phases | Critical and high-severity bugs filed during the phase are resolved |
| Coverage threshold met | All phases | ≥80% statement coverage, ≥75% branch coverage |
| Documentation updated | All phases | Spec documents reflect any design changes made during implementation |

**Phase-specific additional criteria:**

#### Phase 0: Registry Build

- Build script fetches top 1000 PyPI packages
- Groups packages by repository URL
- Probes for llms.txt at all documented URL patterns
- Validates llms.txt content (not HTML error pages)
- Detects and resolves hub files
- Applies manual overrides
- Outputs valid JSON with 1000+ DocSource entries
- GitHub Action runs weekly and commits updated registry

#### Phase 1: Foundation

- `uv sync` and `pip install -e ".[dev]"` both work
- Server starts and responds to MCP `initialize` handshake via stdio
- Health resource returns valid JSON with status "healthy"
- Configuration file validation produces clear errors for invalid config
- Environment variable overrides work
- `uv.lock` generated and committed

#### Phase 2: Core Documentation Pipeline

- `resolve-library("langchain")` returns matches from registry
- `resolve-library("langchan")` returns fuzzy matches
- `get-library-info` returns TOC with `availableSections`
- `get-docs` returns markdown content from llms.txt sources
- Second request for same content served from cache
- SQLite cache file created at configured path
- Session resource tracks resolved libraries

#### Phase 3: Search & Navigation

- `search-docs` searches across indexed content and within specific libraries
- BM25 ranks exact keyword matches higher than tangential mentions
- `read-page` returns content with position metadata and supports offset
- `hasMore` is correct when content exceeds budget
- Pages cached after first fetch
- URL allowlist blocks non-documentation URLs
- `get-docs` returns focused chunks (not raw full docs)

#### Phase 4: HTTP Mode & Authentication

- HTTP server starts on configured port
- Unauthenticated requests → 401
- Invalid API key → 401
- Valid API key → 200 with MCP response
- Admin CLI: `key create`, `key list`, `key revoke` all work
- Rate limiting activates at threshold, returns 429 with `Retry-After`
- CORS headers present
- Multiple clients share the same cache

#### Phase 5: Polish & Production Readiness

- Prompt templates produce correct output
- Docker image builds and runs successfully
- E2E stdio test: full tool chain succeeds
- E2E HTTP test: auth + all tools + rate limiting
- Code coverage ≥80% on `src/`
- Manual MCP client compatibility checklist complete (Section 1.4.2)

### 4.2 Release Readiness Checklist

Before tagging any release (`v*`):

- [ ] All CI checks pass on the release commit
- [ ] Performance benchmarks show no P95 regressions >20% from baseline
- [ ] MCP client compatibility checklist (Section 1.4.2) completed for all supported clients
- [ ] `CHANGELOG.md` updated with release notes
- [ ] Version bumped in `pyproject.toml`
- [ ] Docker image builds and starts successfully
- [ ] No known P0 or P1 bugs
- [ ] Documentation (specs, README) reflects current behavior
- [ ] `known-libraries.json` registry is up to date (refreshed within the last week)
- [ ] All dependency versions are pinned (no `latest` or unbounded ranges)

---

*This document complements `04-implementation-guide.md` Sections 5–6. Implementation-level details (test file paths, per-component mock table, pytest config, CI YAML, Dockerfile) remain in that document. This document covers the strategy and process that govern how those implementations are used.*
