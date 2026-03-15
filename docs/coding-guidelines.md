# Coding Guidelines

Follow these rules when writing or reviewing any code in this repository.

---

## API Design

### 1. Make correct usage the easiest path

Structure every API so the default usage is correct and safe. Require deliberate extra effort for dangerous operations — make them verbose and explicit (`React.dangerouslySetInnerHTML` is the canonical example). Never let the easy path be the unsafe path.

### 2. Treat every observable behavior as a contract

> "With a sufficient number of users of an API, it does not matter what you promise in the contract: all observable behaviors of your system will be depended on by somebody." — Hyrum Wright

Error message wording, collection iteration order, response timing, and incidental behaviors all become de facto contracts over time. Follow these rules:

- Document all observable behaviors explicitly, including ones you consider incidental.
- Use randomization or chaos-testing in CI to prevent consumers from depending on undocumented ordering.
- Treat any bug fix that changes observable behavior as a potential breaking change.

### 3. Keep the public surface area minimal

Every interface you expose is a commitment. MCP tool names, tool parameters, config schema fields, CLI commands, and public module functions — removing or changing any of them is a breaking change. Default to the most restrictive access modifier. Only expose what has a documented, intentional use case. Mark experimental interfaces clearly to reserve the right to change them before fully committing.

### 4. Keep abstractions consistent — no leaks by omission

If some methods require a `tenant_id` parameter while others don't, you are leaking internal architecture. Either all logically related methods carry the parameter or none do. Do not force consumers to understand your internal design to use your API correctly.

### 5. Layer complexity progressively

Make the 80% case a one-liner. Make the 20% advanced case accessible but not required reading. Layer the API:

- `fetch(url)` — zero config default
- `fetch(url, { timeout: 5000, retries: 3 })` — intermediate
- `new HttpClient(config).request(spec)` — full control

### 6. Design intentional extension and override points

All non-trivial abstractions leak eventually (Joel Spolsky's Law of Leaky Abstractions). When a real operator need cannot be met by the default behaviour, the answer must be a documented configuration knob or extension point — not a fork. Every extension point must be: easy to use when needed, well-integrated (using it should not require understanding internal wiring), and documented with its defaults and caveats.

For ProContext specifically: operators need levers for custom registries, trusted domains, auth, cache sizing, and transport. Design these up front rather than bolting them on when the first user hits the wall.

---

## Error Handling

### 8. Never swallow errors in core modules

Low-level modules — resolver, cache, fetcher — must not catch errors silently. Catching an error silently steals the decision from the caller — they cannot retry, fall back, alert, or audit what they cannot see. Do not write this:

```python
try:
    ...
except Exception as e:
    logger.error(e)  # silently swallowed — NEVER do this in core modules
```

Always propagate errors with enough context for the caller to act, or convert infrastructure errors into domain errors at your module boundary.

Top-level handlers (MCP tool handlers, schedulers) may catch errors to prevent process termination — but they must still log them (see Rule 12) and return a structured error response to the client rather than continuing silently.

### 9. Use typed, domain-specific error types

Do not force consumers to parse error strings. Use a typed error hierarchy:

- A sealed/discriminated union (TypeScript)
- Custom exception subclasses with structured fields (Python/Java)
- `Result[T, LibraryError]` where idiomatic

Every error type must carry: classification, human-readable message, and structured data the consumer needs to act on (which field failed validation, what the rate limit reset time is).

### 10. Wrap infrastructure errors at the module boundary

Do not let raw infrastructure exceptions (`httpx.ConnectError`, `sqlite3.OperationalError`) cross module boundaries. Callers — whether MCP tool handlers or higher-level modules — should not need to import `httpx` or `sqlite3` to handle errors from the fetcher or cache. Catch infrastructure exceptions at the module boundary and wrap them in your domain error types with the original as the cause.

### 11. Catch specific exceptions, not bare `except Exception:`

Always catch the narrowest exception type that covers the failure mode:

- Database operations: `except aiosqlite.Error:`
- Network operations: `except httpx.HTTPError:`
- Serialization: `except (ValueError, json.JSONDecodeError):`

Reserve `except Exception:` for top-level handlers and fire-and-forget background tasks where any failure must be suppressed to keep the process alive. Every other `except` block must name the specific exception types it handles.

### 12. Use `exc_info=True` when logging caught exceptions; never suppress silently

When an `except` block catches and suppresses an error, always pass `exc_info=True` to the logger so the full traceback is captured. Do not stringify the exception into the message — structlog captures it structurally.

```python
# Correct — full traceback preserved
except aiosqlite.Error:
    log.warning("cache_write_error", key=cache_key, exc_info=True)

# Wrong — traceback lost, exception stuffed into a string
except aiosqlite.Error as e:
    log.warning("cache_write_error", key=cache_key, error=str(e))
```

**Silence is never acceptable — even when there is nothing to do.** If you suppress an exception because recovery is not possible, you must still log it. The user must be able to see the error in logs to investigate or report it. Never write an `except` block that contains only `pass` or only a comment.

```python
# Wrong — silent suppression; the error disappears completely
except OSError:
    pass  # NEVER do this

# Wrong — a comment is not a log entry
except OSError:
    # best-effort, ignore  # NEVER do this

# Correct — logged even though no recovery is attempted
except OSError:
    log.warning("state_file_write_failed", path=str(path), exc_info=True)
```

---

## Versioning and Breaking Changes

### 13. Watch for non-obvious breaking changes

Not all breaking changes involve removing a method. Check for these before every release:

- Dropping runtime/Python version/OS compatibility (code may not change at all)
- Changing error types — consumers who `except SpecificError` silently stop catching
- Changing default parameter values — behavior changes, signature doesn't
- Narrowing accepted input types
- Changing iteration order of returned collections (see rule 2)
- Persisted data format changes — these outlive code versions

### 14. Follow a deprecation cycle before removing anything

Use this lifecycle without exception:

1. Introduce the replacement in a minor release.
2. Deprecate the old API in the same or following minor release (warning level).
3. Escalate to error-level deprecation in a subsequent minor release.
4. Remove in the next major version.

Every deprecation warning must state: when it was deprecated, why, and exactly what to use instead. Allow at least 12 months before removal. **Never remove an API in the same commit as its replacement.**

### 15. Maintain machine-readable changelogs

Follow [Keep a Changelog](https://keepachangelog.com) format:

- ISO 8601 dates
- `Added / Changed / Deprecated / Removed / Fixed / Security` categories
- Breaking changes prefixed with `BREAKING` in a visible callout

Automate via Conventional Commits + semantic-release. The changelog is the artifact consumers rely on before upgrading — do not skip it.

---

## Code Conventions

### 16. Keep all imports at the top of the file

Place every import at module level. Do not import inside functions, methods, or conditional blocks (other than `if TYPE_CHECKING:`). In-function imports hide dependencies, make it harder to see what a module uses at a glance, and create subtle performance traps when called in loops.

The only acceptable exception is breaking a genuine circular import that cannot be resolved by restructuring. If you hit a circular import, first try to break the cycle by moving shared types to a lower-level module. Resort to an in-function import only as a last option, and add a comment explaining why.

### 17. Keep functions small and focused

A function should do one thing. If you find yourself reaching for a comment like `# Step 2` or `# Phase 2`, that's a signal to extract a named function. Functions that are hard to name are usually doing too much.

A useful heuristic: if a function cannot be understood in one reading without scrolling, it is too long.

---

## Testing Strategy

### 18. Test the public API contract, not the implementation

Write tests from the perspective of a consumer: import the public API and assert on observable behavior. Do not reach into private methods or internal state.

**The bar**: a complete internal rewrite must not break any test. If it does, the tests are testing implementation, not contract.

Do not generate tests that mirror the source file structure and test private helpers directly. Resist this pattern.

### 19. Keep tests for deprecated APIs until removal

Deprecated code is still public API. Maintain tests for it through the entire deprecation cycle. Suppress deprecation warnings explicitly in those test files so future contributors know the suppression is intentional.

### 20. Every bug fix requires a regression test

Do not merge a bug fix without a test that fails before the fix and passes after. This prevents the same bug from reappearing silently in a future refactor.

---

## Supply Chain Security

### 21. Publish provenance attestations

Add SLSA provenance attestation to the release pipeline. This is one CI step:

```yaml
- uses: actions/attest-build-provenance@v1
  with:
    subject-path: dist/
```

Enterprise consumers increasingly require provenance. Its absence is an adoption barrier.

### 22. Verify every dependency against the actual registry

~20% of AI-suggested packages do not exist in any public registry (2025 study, 576k samples). Attackers register these hallucinated names with malicious code ("slopsquatting"). Before adding any dependency, verify the package name exists in the actual registry and is the package you intend to use.

---

## Maintainability

### 24. Keep files small and focused

A file should own one concern. If the module docstring requires more than one sentence to summarize all responsibilities, that is a signal to split the file.

A useful heuristic: if you cannot understand what a file does without scrolling through it, it is doing too much. Aim for files where the purpose is obvious from the filename alone.

Prefer flat files for single-concern modules — a subdirectory only earns its place when two or more closely related files belong together and would be confusing in isolation.

Prefer files under `300` lines when possible; treat `500` lines as an exception ceiling that should require a strong cohesion argument.

### 25. Minimize runtime dependencies

Zero dependencies is ideal. When that is not practical, justify every runtime dependency. Each one has an ongoing cost:

- Transitive CVEs become your CVEs to track and patch
- Every dependency is a potential supply-chain attack vector
- More dependencies mean slower installs and larger container images

When you inline a small helper instead of adding a dependency, note the source, version, and license in a comment. Do not add utility packages without weighing the ongoing maintenance cost.
