# ProContext Doctor

`procontext doctor` validates the health of a ProContext installation and optionally repairs detected issues.

## Purpose

Doctor performs deep validation of every component ProContext depends on at runtime: filesystem paths, registry integrity, cache database schema, and network connectivity. Each check explains what it found and — when something is wrong — tells you exactly how to fix it.

## Checks

### Data Directory

Validates that `data_dir` (default: platform data directory) exists with read/write/execute permissions, and that the `registry/` subdirectory exists.

- **Auto-fixable**: missing directories are created
- **Not auto-fixable**: permission issues (reports the `chmod` command to run)

### Registry

Validates that registry files (`known-libraries.json`, `registry-state.json`) are present, parseable, and that the checksum matches. Reports library count and version.

- **Auto-fixable**: missing or corrupt registry is re-downloaded via `attempt_registry_setup()`
- **Not auto-fixable**: network errors during download (reports the error)

### Cache Database

Validates the SQLite cache database in stages:

1. Parent directory exists and is writable
2. Database file is openable (not corrupt)
3. WAL journal mode is active
4. Expected tables exist (`page_cache`, `server_metadata`)
5. Table columns match the expected schema

Schema validation is **automatic** — doctor creates a reference database in memory using the same `Cache.init_db()` that the server uses, then compares column names and types via `PRAGMA table_info`. When `cache.py` changes its schema, doctor picks it up with zero manual updates.

- **Auto-fixable**: enable WAL mode, create missing tables, add missing columns in place
- **Not auto-fixable**: corrupt/unreadable DBs, incompatible column definitions, permission issues on the parent directory
- **Destructive fallback**: `procontext db recreate` deletes `cache.db` and recreates it with the current schema

### Network

Validates connectivity to the registry metadata URL.

- **Not auto-fixable**: network issues are external

## `--fix` Flag

```bash
procontext doctor --fix
```

When `--fix` is passed, each failing check that is auto-fixable attempts repair:
- If repair succeeds, the check shows `FIXED` with a description of what was done
- If repair fails, the check shows `FAIL` with the error
- Checks that cannot be auto-fixed always show a `fix_hint` explaining manual steps
- Cache repair is intentionally non-destructive: doctor preserves existing rows where possible and only suggests `procontext db recreate` when a clean repair is not possible

## `procontext db recreate`

```bash
procontext db recreate
```

This is the destructive cache reset path. It deletes the configured cache database along with any `-wal` and `-shm` side files, then creates a fresh database with the current schema.

Use it when:
- `procontext doctor --fix` reports that the cache DB is corrupt or unreadable
- `procontext doctor --fix` reports an incompatible schema that cannot be repaired in place
- you explicitly want to discard cached content and start from a clean DB

| Check | Auto-fixable | Fix action |
|-------|-------------|------------|
| Data dir missing | Yes | Create directories |
| Registry missing/corrupt | Yes | Re-download from configured URL |
| Cache parent dir missing | Yes | Create directory |
| Cache DB journal mode disabled | Yes | Enable WAL mode in place |
| Cache DB missing tables/columns | Yes | Create missing tables / add missing columns in place |
| Cache DB corrupt/unreadable | No | Suggest `procontext db recreate` |
| Cache DB incompatible schema | No | Suggest `procontext db recreate` |
| Permission errors | No | Reports `chmod` command |
| Network unreachable | No | Reports error |

## Output Format

### All checks pass
```
ProContext Doctor

  Data directory ...... ok (~/.local/share/procontext)
  Registry ............ ok (918 libraries, v2026-03-04)
  Cache ............... ok (~/.local/share/procontext/cache.db, schema valid)
  Network ............. ok (registry reachable)

All checks passed.
```

### Failures with hints
```
ProContext Doctor

  Data directory ...... ok (~/.local/share/procontext)
  Registry ............ FAIL
    Registry files not found.
    Fix: run 'procontext setup' or 'procontext doctor --fix'
  Cache ............... FAIL
    Schema mismatch — Table 'page_cache': missing columns: outline.
    Fix: run 'procontext doctor --fix' to attempt in-place repair; if that cannot fix it, run 'procontext db recreate' to replace the cache database
  Network ............. ok (registry reachable)

2 checks failed. Run 'procontext doctor --fix' to attempt auto-repair.
```

### After --fix
```
ProContext Doctor (--fix)

  Data directory ...... ok (~/.local/share/procontext)
  Registry ............ FIXED (downloaded 918 libraries, v2026-03-04)
  Cache ............... FIXED (enabled WAL mode; added columns to page_cache: outline, discovered_domains, last_checked_at)
  Network ............. ok (registry reachable)

All issues resolved.
```

## Exit Codes

- `0` — all checks passed (or all issues fixed with `--fix`)
- `1` — one or more checks failed

## Adding New Checks

1. Write an `async def check_*(settings: Settings, *, fix: bool = False) -> CheckResult` function
2. Add it to the `_CHECKS` list in `run_doctor()`
3. Add unit tests for pass, fail, and fix scenarios
4. Document the check in this file
