"""Outline structuring, compaction, match-range trimming, and formatting.

Parses the raw outline string (cached alongside page content) into structured
entries, applies intelligent compaction for token-efficient responses, and
formats entries back to the wire format.

The raw outline is produced by ``parser.py`` and stored as-is in the cache.
This module operates on that cached string at response time.
"""

from __future__ import annotations

from dataclasses import dataclass

from procontext.parser import _FENCE_RE, _HEADING_RE


@dataclass(frozen=True)
class OutlineEntry:
    """Single entry in a structured outline."""

    line_number: int  # 1-based line number in the source content
    text: str  # Original line text (e.g., "## Usage" or "```python")
    depth: int | None  # 1 for H1 … 6 for H6; None for fence lines
    is_fence: bool  # True for fence opener/closer
    in_fence: bool  # True if inside a fenced code block


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_outline_entries(outline_string: str) -> list[OutlineEntry]:
    """Parse a cached outline string into structured entries.

    The input format is ``"<lineno>:<original line>\\n..."``.  Each line is
    split on the first ``:``, then classified as a heading or fence line with
    CommonMark-compliant fence state tracking.
    """
    if not outline_string:
        return []

    entries: list[OutlineEntry] = []

    # Fence state tracking (CommonMark rules)
    in_fence = False
    fence_char: str = ""
    fence_len: int = 0

    for raw_line in outline_string.split("\n"):
        if not raw_line:
            continue

        # Split on first ":"
        colon_idx = raw_line.index(":")
        line_number = int(raw_line[:colon_idx])
        text = raw_line[colon_idx + 1 :]

        # Determine if this is a fence line
        fence_match = _FENCE_RE.match(text)
        is_fence = fence_match is not None

        if is_fence:
            assert fence_match is not None
            marker = fence_match.group(1)
            char = marker[0]
            length = len(marker)

            if not in_fence:
                # Opening a new fence
                in_fence = True
                fence_char = char
                fence_len = length
                entries.append(
                    OutlineEntry(
                        line_number=line_number,
                        text=text,
                        depth=None,
                        is_fence=True,
                        in_fence=False,  # The opener itself is not "inside" the fence
                    )
                )
            elif char == fence_char and length >= fence_len:
                # Closing the fence
                in_fence = False
                fence_char = ""
                fence_len = 0
                entries.append(
                    OutlineEntry(
                        line_number=line_number,
                        text=text,
                        depth=None,
                        is_fence=True,
                        in_fence=False,  # The closer itself is not "inside" the fence
                    )
                )
            else:
                # Fence-like line inside a fence that doesn't close it
                # (different char or shorter length) — treat as heading check
                depth = _extract_depth(text)
                entries.append(
                    OutlineEntry(
                        line_number=line_number,
                        text=text,
                        depth=depth,
                        is_fence=False,
                        in_fence=True,
                    )
                )
        else:
            # Heading line
            depth = _extract_depth(text)
            entries.append(
                OutlineEntry(
                    line_number=line_number,
                    text=text,
                    depth=depth,
                    is_fence=False,
                    in_fence=in_fence,
                )
            )

    return entries


def _extract_depth(text: str) -> int | None:
    """Extract heading depth (1-6) from a line, or None if not a heading."""
    match = _HEADING_RE.match(text.strip())
    if match:
        return len(match.group(1))
    return None


# ---------------------------------------------------------------------------
# Empty fence stripping
# ---------------------------------------------------------------------------


def strip_empty_fences(entries: list[OutlineEntry]) -> list[OutlineEntry]:
    """Remove fence pairs that contain no heading entries.

    Fence markers exist in the outline to disambiguate headings inside code
    blocks from structural headings.  Fence pairs with zero heading entries
    add no navigational value and are removed.
    """
    # Identify indices to remove
    remove: set[int] = set()
    opener_idx: int | None = None

    for i, entry in enumerate(entries):
        if entry.is_fence:
            if opener_idx is None:
                # This is an opener
                opener_idx = i
            else:
                # This is a closer — check for headings between opener and closer
                has_headings = any(entries[j].depth is not None for j in range(opener_idx + 1, i))
                if not has_headings:
                    # Mark opener, closer, and everything between for removal
                    for j in range(opener_idx, i + 1):
                        remove.add(j)
                opener_idx = None

    return [e for i, e in enumerate(entries) if i not in remove]


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------


def compact_outline(
    entries: list[OutlineEntry], max_entries: int = 50
) -> list[OutlineEntry] | None:
    """Progressively reduce outline entries to fit within *max_entries*.

    Reduction stages (in order, stopping as soon as count ≤ max_entries):
      1. Remove H6 headings
      2. Remove H5 headings
      3. Remove fenced content (in_fence entries) and their enclosing fence markers
      4. Remove H4 headings
      5. Remove H3 headings

    Returns ``None`` if the outline cannot be reduced to ≤ max_entries
    (only H1/H2 remain and still exceed the limit).
    """
    if len(entries) <= max_entries:
        return entries

    result = entries

    # Stage 1: Remove H6
    result = [e for e in result if e.depth != 6]
    if len(result) <= max_entries:
        return result

    # Stage 2: Remove H5
    result = [e for e in result if e.depth != 5]
    if len(result) <= max_entries:
        return result

    # Stage 3: Remove fenced content and fence markers
    result = [e for e in result if not e.in_fence and not e.is_fence]
    if len(result) <= max_entries:
        return result

    # Stage 4: Remove H4
    result = [e for e in result if e.depth != 4]
    if len(result) <= max_entries:
        return result

    # Stage 5: Remove H3
    result = [e for e in result if e.depth != 3]
    if len(result) <= max_entries:
        return result

    # Irreducible — only H1/H2 remain and still exceed max_entries
    return None


# ---------------------------------------------------------------------------
# Match-range trimming
# ---------------------------------------------------------------------------


def trim_outline_to_range(
    entries: list[OutlineEntry], first_line: int, last_line: int
) -> list[OutlineEntry]:
    """Filter entries to those within the given line range (inclusive)."""
    return [e for e in entries if first_line <= e.line_number <= last_line]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_outline(entries: list[OutlineEntry]) -> str:
    """Convert structured entries back to the wire format.

    Returns ``"<lineno>:<text>\\n<lineno>:<text>\\n..."``.
    """
    return "\n".join(f"{e.line_number}:{e.text}" for e in entries)


def build_compaction_note(
    entries: list[OutlineEntry],
    total_entries: int,
    *,
    match_range: tuple[int, int] | None = None,
) -> str:
    """Build a human-readable note describing what the compacted outline contains.

    Args:
        entries: The compacted entries (after compaction).
        total_entries: Total entry count before compaction (after fence stripping).
        match_range: Optional ``(first_line, last_line)`` tuple for search_page.

    Returns:
        A bracketed note string, e.g.
        ``[Compacted: showing H1-H3 headings only. ...]``
    """
    # Determine the surviving heading depth range
    depths = sorted({e.depth for e in entries if e.depth is not None})
    if depths:
        depth_desc = f"H{depths[0]}-H{depths[-1]}" if len(depths) > 1 else f"H{depths[0]}"
    else:
        depth_desc = "no headings"

    range_desc = ""
    if match_range is not None:
        range_desc = f" in match range (lines {match_range[0]}-{match_range[1]})"

    return (
        f"[Compacted: showing {depth_desc} headings{range_desc}. "
        f"Use read_outline for full outline ({total_entries} entries).]"
    )
