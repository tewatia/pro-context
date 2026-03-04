"""Page outline parser for documentation pages.

Single-pass algorithm that extracts H1–H6 headings and fenced code block
boundaries from Markdown content. Outputs a plain-text outline with
1-based line numbers for agent navigation via the ``read_page`` tool.

Emitted lines:
- Heading lines (H1–H6), including those inside fenced code blocks and those
  prefixed with a blockquote marker (``> ``).
- Fence opener and closer lines (`` ``` `` / ``~~~``), so the agent can tell
  which headings belong to code block content vs. structural page sections.
"""

from __future__ import annotations

import re

# Matches fence openers/closers: at most 3 spaces of indentation, then 3+
# backticks or tildes. Checked against the original (unstripped) line so that
# 4-space indented lines (indented code blocks) are correctly ignored.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

# Matches ATX headings H1–H6 on the stripped line.  The optional ``(?:>\s*)?``
# prefix handles blockquote headings (``> ## Section``).
_HEADING_RE = re.compile(r"(?:>\s*)?(#{1,6}) .+")


def parse_outline(content: str) -> str:
    """Extract a plain-text structural map from Markdown content.

    Returns one line per heading or fence marker in the format
    ``"<lineno>: <original line>"``, joined by newlines.
    Returns an empty string if no headings or fences are found.

    Fence opener and closer lines are included so the agent can determine
    whether a heading-like line belongs to code content or the document
    structure proper.
    """
    # Strip UTF-8 BOM if present — some servers prepend \ufeff to responses,
    # which would prevent the heading regex from matching line 1.
    content = content.removeprefix("\ufeff")

    lines: list[str] = []

    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if _FENCE_RE.match(line) or _HEADING_RE.match(stripped):
            lines.append(f"{lineno}: {line}")

    return "\n".join(lines)
