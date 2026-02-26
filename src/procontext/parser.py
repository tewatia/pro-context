"""Heading parser for documentation pages.

Single-pass algorithm that extracts H1–H4 headings from Markdown content,
suppressing headings inside fenced code blocks. Outputs a plain-text heading
map with 1-based line numbers for agent navigation via the ``read_page`` tool.
"""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,4}) (.+)")


def parse_headings(content: str) -> str:
    """Extract a plain-text heading map from Markdown content.

    Returns one line per heading in the format ``"<lineno>: <heading line>"``,
    joined by newlines.  Returns an empty string if no headings are found.
    """
    lines: list[str] = []

    in_code_block = False
    fence: str | None = None

    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()

        # Rule 1: code block tracking
        if stripped.startswith("```") or stripped.startswith("~~~"):
            current_fence = stripped[:3]
            if not in_code_block:
                in_code_block = True
                fence = current_fence
            elif current_fence == fence:
                in_code_block = False
                fence = None
            continue

        if in_code_block:
            continue

        # Rule 2: heading detection (H1–H4)
        match = _HEADING_RE.match(line)
        if not match:
            continue

        lines.append(f"{lineno}: {line}")

    return "\n".join(lines)
