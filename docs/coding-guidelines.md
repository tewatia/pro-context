# Coding Guidelines for Public Libraries

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

Every exported symbol is a commitment. Removing or changing it later is a breaking change. Default to the most restrictive access modifier. Only expose what has a documented, intentional use case. Use `@Beta` or equivalent annotations to reserve the right to change APIs before fully committing.

### 4. Keep abstractions consistent — no leaks by omission

If some methods require a `tenant_id` parameter while others don't, you are leaking internal architecture. Either all logically related methods carry the parameter or none do. Do not force consumers to understand your internal design to use your API correctly.

### 5. Layer complexity progressively

Make the 80% case a one-liner. Make the 20% advanced case accessible but not required reading. Layer the API:

- `fetch(url)` — zero config default
- `fetch(url, { timeout: 5000, retries: 3 })` — intermediate
- `new HttpClient(config).request(spec)` — full control

### 6. Provide intentional escape hatches

All non-trivial abstractions leak eventually (Joel Spolsky's Law of Leaky Abstractions). Provide documented escape hatches that let consumers drop to a lower level without abandoning the library. Every escape hatch must be: easy to use when needed, well-integrated (easy to return to the higher abstraction), and documented with clear caveats.

### 7. Keep all imports at the top of the file

Place every import at module level. Do not import inside functions, methods, or conditional blocks (other than `if TYPE_CHECKING:`). In-function imports hide dependencies, make it harder to see what a module uses at a glance, and create subtle performance traps when called in loops.

The only acceptable exception is breaking a genuine circular import that cannot be resolved by restructuring. If you hit a circular import, first try to break the cycle by moving shared types to a lower-level module. Resort to an in-function import only as a last option, and add a comment explaining why.

---

## Error Handling

### 8. Never swallow errors in library code

An application can log-and-continue. A library must not. Catching an error silently steals the decision from the consumer — they cannot retry, fall back, alert, or audit what they cannot see. Do not write this:

```python
try:
    ...
except Exception as e:
    logger.error(e)  # silently swallowed — NEVER do this in library code
```

Always propagate errors with enough context for the consumer to act, or convert infrastructure errors into domain errors at your abstraction boundary.

### 9. Use typed, domain-specific error types

Do not force consumers to parse error strings. Use a typed error hierarchy:

- A sealed/discriminated union (TypeScript)
- Custom exception subclasses with structured fields (Python/Java)
- `Result[T, LibraryError]` where idiomatic

Every error type must carry: classification, human-readable message, and structured data the consumer needs to act on (which field failed validation, what the rate limit reset time is).

### 10. Wrap infrastructure errors at the boundary

Do not let raw infrastructure exceptions (`httpx.ConnectError`, `sqlite3.OperationalError`) cross your library boundary. A consumer should never need to import `httpx` or `sqlite3` to handle your errors. Catch infrastructure exceptions at the boundary and wrap them in your domain error types with the original as the cause.

### 11. Catch specific exceptions, not bare `except Exception:`

Always catch the narrowest exception type that covers the failure mode:

- Database operations: `except aiosqlite.Error:`
- Network operations: `except httpx.HTTPError:`
- Serialization: `except (ValueError, json.JSONDecodeError):`

Reserve `except Exception:` for top-level handlers and fire-and-forget background tasks where any failure must be suppressed to keep the process alive. Every other `except` block must name the specific exception types it handles.

### 12. Use `exc_info=True` when logging caught exceptions

When an `except` block catches and suppresses an error, always pass `exc_info=True` to the logger so the full traceback is captured. Do not stringify the exception into the message — structlog captures it structurally.

```python
# Correct — full traceback preserved
except aiosqlite.Error:
    log.warning("cache_write_error", key=cache_key, exc_info=True)

# Wrong — traceback lost, exception stuffed into a string
except aiosqlite.Error as e:
    log.warning("cache_write_error", key=cache_key, error=str(e))
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

## Testing Strategy

### 16. Test the public API contract, not the implementation

Write tests from the perspective of a consumer: import the public API and assert on observable behavior. Do not reach into private methods or internal state.

**The bar**: a complete internal rewrite must not break any test. If it does, the tests are testing implementation, not contract.

Do not generate tests that mirror the source file structure and test private helpers directly. Resist this pattern.

### 17. Keep tests for deprecated APIs until removal

Deprecated code is still public API. Maintain tests for it through the entire deprecation cycle. Suppress deprecation warnings explicitly in those test files so future contributors know the suppression is intentional.

### 18. Every bug fix requires a regression test

Do not merge a bug fix without a test that fails before the fix and passes after. This prevents the same bug from reappearing silently in a future refactor.

---

## Supply Chain Security

### 19. Publish provenance attestations

Add SLSA provenance attestation to the release pipeline. This is one CI step:

```yaml
- uses: actions/attest-build-provenance@v1
  with:
    subject-path: dist/
```

Enterprise consumers increasingly require provenance. Its absence is an adoption barrier.

### 20. Verify every dependency against the actual registry

~20% of AI-suggested packages do not exist in any public registry (2025 study, 576k samples). Attackers register these hallucinated names with malicious code ("slopsquatting"). Before adding any dependency, verify the package name exists in the actual registry and is the package you intend to use.

---

## Library Adoptability

### 21. Minimize runtime dependencies

Zero dependencies is ideal. When that is not practical, justify every runtime dependency. Be aware of the cost each one imposes on consumers:

- Transitive CVEs land on consumers' SBOMs
- Version conflicts with other libraries in the consumer's project
- Bundle size becomes unpredictable

When you inline a dependency, note the version and license in source comments. Do not add utility packages without considering the downstream implications.

## Additional guidelines:

1. **Type support quality** — not just "has types" but whether generics are useful and errors are typed.
2. **Changelog quality** — document breaking changes and provide migration guides.
3. **Forbidden imports inside functions** - no imports inside functions. THEY SHOULD BE AT THE TOP OF THE FILE.
