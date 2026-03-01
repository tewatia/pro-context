---
name: changelog-release
description: "Maintain CHANGELOG.md. No args: populate [Unreleased] from commits since last tag (run after committing). With a version (e.g. 0.2.0): finalize [Unreleased] into a versioned release section."
argument-hint: "[version — e.g. 0.2.0, or leave blank to populate Unreleased]"
user-invokable: true
---

Arguments: $ARGUMENTS
Today's date: !`date +%Y-%m-%d`
Last release tag: !`git describe --tags --abbrev=0 2>/dev/null || echo "none"`

Commits since last tag:
!`git log $(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)..HEAD --pretty=format:"  %h %s"`

---

Read CHANGELOG.md, then act based on the arguments above.

## Mode 1 — Populate [Unreleased] (no version argument given)

Filter the commit list. Skip:
- `chore(release):` version bump commits
- `test:` commits
- `ci:` commits
- `docs:` commits that are purely internal spec or guide edits with no user-visible effect
- Merge commits

Group the remaining commits into Keep a Changelog subsections:
- `feat:` → **Added**
- `fix:` → **Fixed**
- Any commit mentioning security, SSRF, auth, or vulnerability → **Security**
- `refactor:` or `chore:` that changes observable behavior → **Changed**
- `refactor:` or `chore:` with no user-visible impact → skip

Write clean, user-facing prose entries under `## [Unreleased]`. Do not copy raw commit subject lines — rewrite them as clear, concise changelog entries describing what changed for someone using the library.

Rules:
- Only add entries not already present in `[Unreleased]`
- Do not touch any existing versioned release sections
- If there is nothing user-facing to add, say so and make no edits

## Mode 2 — Write release section (version argument given, e.g. `0.2.0`)

- Rename `## [Unreleased]` to `## [<version>] - <today's date>`
- Insert a fresh empty `## [Unreleased]` section above it (no subsections)
- Update the comparison links at the bottom of the file:
  - Update the `[Unreleased]` link to compare from the new tag: `v<version>...HEAD`
  - Add a new versioned link `[<version>]: .../compare/v<prev-tag>...v<version>` where `<prev-tag>` is the last release tag shown above
- Do not modify the content of any sections — only rename, reorder, and update links
