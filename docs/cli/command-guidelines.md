# CLI Command Guidelines

Use the command tree to express the primary action, and use flags only to modify that action.

## Prefer Subcommands for Actions

Prefer:

```bash
procontext db recreate
```

Avoid:

```bash
procontext db --recreate
procontext doctor --recreate
```

Reasoning:
- `db recreate` is a distinct action, not a mode of `doctor` or `db`
- subcommands scale cleanly as the surface grows (`db recreate`, `db vacuum`, `db stats`)
- destructive operations are more explicit and easier to discover in `--help`
- flags should not silently change the meaning of the command being run

## Use Flags for Modifiers, Not Alternate Verbs

Good flag usage:

```bash
procontext doctor --fix
```

`--fix` is appropriate because the command is still `doctor`; the flag only changes how diagnosis is performed.

Use flags for:
- output format or verbosity (`--json`, `--verbose`)
- execution modifiers (`--fix`, `--dry-run`)
- confirmation or safety bypass (`--yes`, `--force`)
- filtering or scope (`--library`, `--path`)

Do not use flags for:
- a different primary operation
- destructive actions that deserve their own verb
- mutually exclusive workflows that would read more clearly as separate subcommands

## Namespace by Resource When Multiple Verbs Exist

Use top-level commands for standalone workflows:
- `procontext setup`
- `procontext doctor`

Use nested commands when a resource has multiple operations:
- `procontext db recreate`

This keeps the CLI stable as new capabilities are added and avoids a flat list of loosely related top-level commands.

## Make Destructive Actions Explicit

Any operation that deletes or replaces user data should be an explicit verb, not a hidden side effect of a flag.

Preferred pattern:

```bash
procontext db recreate
```

If confirmation is needed later, add a modifier to the destructive verb:

```bash
procontext db recreate --yes
```

Do not overload a diagnostic or read-oriented command with destructive flags.

## Quick Rules

- Use `<noun> <verb>` for resource-oriented operations.
- Use top-level commands only for distinct workflows.
- Use flags to modify execution, not to select a different action.
- Make destructive operations explicit and discoverable in help output.
- Extend the existing namespace before adding unrelated top-level verbs.
