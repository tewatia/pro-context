# Installer Maintenance

This document defines the contract for the repository installer scripts:

- [`install.sh`](../../install.sh)
- [`install.ps1`](../../install.ps1)

These are the only supported public installer entrypoints. Do not reintroduce parallel families such as `install_cl.*` or `install_cx.*`.

## Why the Installers Live at the Repo Root

The public install URLs should be short and stable:

- `.../install.sh`
- `.../install.ps1`

Keeping the files at the repository root also makes it obvious which scripts are user-facing and avoids burying the public entrypoints inside a docs or tooling directory.

## Behavioral Contract

Both installers should preserve the same high-level behavior:

- install from the GitHub repository, not from PyPI
- manage a checkout on disk instead of using `uv tool install`
- sync a runtime-only environment with `uv sync --project ... --no-dev`
- default to the `main` branch unless a ref is provided
- accept raw refs directly; do not force a `v` prefix onto tags
- run `procontext setup` by default, with an explicit skip flag
- keep `--dry-run` or `-DryRun` side-effect free
- avoid overwriting a dirty checkout during updates
- print `uv run --project ... procontext` as the canonical way to start the server

## Platform-Specific Responsibilities

### `install.sh`

- support macOS and Linux
- bootstrap `git` through Homebrew or the system package manager when possible
- bootstrap `uv` through Homebrew or Astral's official installer
- add user-local bin directories to PATH when needed

### `install.ps1`

- support Windows PowerShell 5+ and PowerShell 7+
- bootstrap `git` through `winget`, `choco`, `scoop`, or portable Git as a fallback
- bootstrap `uv` through `winget`, `choco`, `scoop`, or Astral's official installer
- refresh PATH after package-manager installs so the current shell can continue

## End-User vs Development Setup

The installer scripts are for runtime installation only. They should not create a contributor environment.

Contributor setup belongs in [CONTRIBUTING.md](../../CONTRIBUTING.md) and should continue to use:

```bash
uv sync --dev
```

End-user setup should continue to use:

```bash
uv sync --no-dev
```

## Docs That Must Stay in Sync

If the installer behavior changes, update these docs in the same change:

- [README.md](../../README.md) installation section
- [installation.md](installation.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md) if development prerequisites or setup guidance changed

## Validation Checklist

When changing the installers, validate at least:

### Unix

```bash
bash -n install.sh
bash install.sh --dry-run --dir /tmp/procontext-install-test
```

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -DryRun
```

If you have PowerShell 7 available:

```powershell
pwsh -NoProfile -File .\install.ps1 -DryRun
```

Also verify:

- the docs still use the current flag names
- the installer still points at the correct repository URL
- the MCP config snippet still uses `uv run --project`

## Future PyPI Migration

These scripts are intentionally GitHub-checkout installers for now.

When ProContext is published to PyPI, revisit:

- whether end users should still get a managed checkout
- whether the public install flow should switch to `uv tool install procontext`
- how existing checkout-based installs should be migrated

Until that decision is made, keep the scripts GitHub-first and keep the docs explicit about that choice.
