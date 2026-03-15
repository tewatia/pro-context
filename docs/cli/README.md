# ProContext CLI

ProContext provides a small set of CLI commands alongside the MCP server. The CLI uses Python's `argparse` with subcommands — no additional dependencies.

## Commands

### `procontext` (no arguments)

Starts the MCP server. This is the default behavior and what MCP clients (Claude Code, Cursor, Windsurf) invoke.

- In **stdio mode** (default): the server communicates over stdin/stdout via JSON-RPC.
- In **HTTP mode** (`PROCONTEXT__SERVER__TRANSPORT=http`): starts a persistent HTTP server on `/mcp`.

If the registry has not been downloaded yet, an automatic one-time setup is attempted before the server starts.

### `procontext setup`

Downloads the library registry from the configured metadata URL and saves it to the platform data directory.

```bash
uv run procontext setup
```

This is required once before the server can start. If skipped, the server will attempt auto-setup on first run.

### `procontext doctor`

Validates system health — filesystem paths, registry integrity, cache database schema, and network connectivity. Reports issues with actionable fix instructions.

```bash
uv run procontext doctor         # diagnose
uv run procontext doctor --fix   # diagnose and attempt in-place repair
```

See [doctor.md](doctor.md) for full documentation including check details, output format, and `--fix` behavior.

### `procontext db recreate`

Deletes the configured cache database and recreates it with the current schema. Use this when doctor reports that the DB cannot be repaired safely in place.

```bash
uv run procontext db recreate
```

For command naming and command-tree conventions, see [command-guidelines.md](command-guidelines.md).

## stdout Safety

CLI commands (`setup`, `doctor`, `db`) print to stdout freely. The stdout guard that protects the MCP JSON-RPC stream in stdio mode only activates inside the MCP server lifespan — CLI commands never enter that context.

For details on the stdio transport and stdout protection, see [Technical Spec §7](../specs/02-technical-spec.md).

## Adding New Commands

Convention for adding CLI commands:

1. Decide whether the new behavior is:
   a. a standalone workflow (`setup`, `doctor`), or
   b. a verb under an existing resource namespace (`db recreate`)
2. Expose one public runner per concrete action:
   ```python
   async def run_<name>(settings: Settings) -> None:
   async def run_<namespace>_<verb>(settings: Settings) -> None:
   ```
3. Prefer subcommands over boolean action flags when the new behavior is a different verb
4. Add a subparser in `src/procontext/cli/main.py`
5. Add `# noqa: T201` to any `print()` calls (the `T20` ruff rule catches accidental prints)
6. Add unit tests in `tests/unit/test_cli_<name>.py` and integration tests in `tests/integration/test_cli.py`
7. Update [command-guidelines.md](command-guidelines.md) when the command shape introduces a new reusable pattern
