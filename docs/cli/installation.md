# Installation

ProContext ships two supported installer entrypoints at the repository root:

- `install.sh` for macOS and Linux
- `install.ps1` for Windows

Both installers follow the same model:

- clone or refresh a managed checkout from GitHub
- ensure `git` and `uv` are available
- sync a runtime-only environment with `uv sync --no-dev`
- run the one-time `procontext setup` step unless you skip it

These installers are for end-user setup. If you want a development environment, use the contributor flow in [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Quick Install

### macOS and Linux

```bash
curl -fsSL https://raw.githubusercontent.com/procontexthq/procontext/main/install.sh | bash
```

Examples:

```bash
# Preview what the installer would do
curl -fsSL https://raw.githubusercontent.com/procontexthq/procontext/main/install.sh | bash -s -- --dry-run

# Install a specific tag, branch, or commit
curl -fsSL https://raw.githubusercontent.com/procontexthq/procontext/main/install.sh | bash -s -- --version v0.1.0

# Skip the one-time registry download
curl -fsSL https://raw.githubusercontent.com/procontexthq/procontext/main/install.sh | bash -s -- --no-setup
```

### Windows

```powershell
powershell -c "irm https://raw.githubusercontent.com/procontexthq/procontext/main/install.ps1 | iex"
```

Examples:

```powershell
# Preview what the installer would do
powershell -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/procontexthq/procontext/main/install.ps1))) -DryRun"

# Install a specific tag, branch, or commit
powershell -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/procontexthq/procontext/main/install.ps1))) -Version v0.1.0"

# Skip the one-time registry download
powershell -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/procontexthq/procontext/main/install.ps1))) -NoSetup"
```

## What the Installers Need

- internet access to GitHub and Astral download endpoints
- `git`, which the installers attempt to bootstrap if it is missing
- `uv`, which the installers attempt to bootstrap if it is missing
- Python 3.12 or newer at runtime; `uv` can provision Python automatically if it is not already installed

## What Gets Installed

The installers manage a checkout instead of installing a PyPI package. The default checkout locations are:

- macOS: `~/Library/Application Support/procontext-source`
- Linux: `~/.local/share/procontext-source`
- Windows: `%LOCALAPPDATA%\procontext-source`

The checkout is then used with `uv run --project ...`, which keeps the runtime tied to that source tree.

## After Install

Run ProContext directly:

```bash
uv run --project "/path/to/procontext-source" procontext
```

The installers also print an MCP configuration snippet that points clients at the managed checkout.

If you skipped setup, run it later:

```bash
uv run --project "/path/to/procontext-source" procontext setup
```

If something looks unhealthy:

```bash
uv run --project "/path/to/procontext-source" procontext doctor --fix
```

## Installer Options

### `install.sh`

- `--dir PATH` installs or refreshes the checkout at `PATH`
- `--repo URL` uses a different Git repository
- `--ref REF` installs a branch, tag, or commit
- `--version REF` alias for `--ref`
- `--no-setup` skips `procontext setup`
- `--dry-run` prints the plan without making changes

### `install.ps1`

- `-InstallDir PATH` installs or refreshes the checkout at `PATH`
- `-RepoUrl URL` uses a different Git repository
- `-InstallRef REF` installs a branch, tag, or commit
- `-Version REF` alias for `-InstallRef`
- `-NoSetup` skips `procontext setup`
- `-DryRun` prints the plan without making changes

## Manual Install

If you do not want to run the helper scripts, the equivalent manual flow is:

```bash
git clone https://github.com/procontexthq/procontext.git
cd procontext
uv sync --no-dev
uv run --project . procontext setup
```

Then run:

```bash
uv run --project . procontext
```

## Troubleshooting

- If `uv` or `procontext` is reported as missing after install, open a new shell first so the updated PATH is loaded.
- If the managed checkout has local changes, the installer will not overwrite them during an update.
- If the one-time registry download fails, rerun `procontext setup` after fixing connectivity.
- For contributor setup, do not use the runtime installer flow. Use [CONTRIBUTING.md](../../CONTRIBUTING.md) and `uv sync --dev`.
