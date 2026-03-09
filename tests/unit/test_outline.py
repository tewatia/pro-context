"""Unit tests for the outline module."""

from __future__ import annotations

from procontext.outline import (
    OutlineEntry,
    build_compaction_note,
    compact_outline,
    format_outline,
    parse_outline_entries,
    strip_empty_fences,
    trim_outline_to_range,
)

# ---------------------------------------------------------------------------
# parse_outline_entries
# ---------------------------------------------------------------------------


class TestParseOutlineEntries:
    def test_empty_string(self) -> None:
        assert parse_outline_entries("") == []

    def test_single_heading(self) -> None:
        entries = parse_outline_entries("1:# Title")
        assert len(entries) == 1
        e = entries[0]
        assert e.line_number == 1
        assert e.text == "# Title"
        assert e.depth == 1
        assert e.is_fence is False
        assert e.in_fence is False

    def test_multiple_headings(self) -> None:
        outline = "1:# Title\n3:## Section\n10:### Sub"
        entries = parse_outline_entries(outline)
        assert len(entries) == 3
        assert entries[0].depth == 1
        assert entries[1].depth == 2
        assert entries[1].line_number == 3
        assert entries[2].depth == 3

    def test_fence_lines_detected(self) -> None:
        outline = "5:```python\n8:```"
        entries = parse_outline_entries(outline)
        assert len(entries) == 2
        assert entries[0].is_fence is True
        assert entries[0].depth is None
        assert entries[1].is_fence is True

    def test_headings_inside_fence_tagged(self) -> None:
        outline = "1:# Title\n3:```\n5:## Inside\n7:```\n9:## After"
        entries = parse_outline_entries(outline)
        assert len(entries) == 5

        # # Title — not in fence
        assert entries[0].in_fence is False
        assert entries[0].depth == 1

        # ``` opener — fence, not in fence
        assert entries[1].is_fence is True
        assert entries[1].in_fence is False

        # ## Inside — in fence
        assert entries[2].in_fence is True
        assert entries[2].depth == 2

        # ``` closer — fence, not in fence
        assert entries[3].is_fence is True
        assert entries[3].in_fence is False

        # ## After — not in fence
        assert entries[4].in_fence is False
        assert entries[4].depth == 2

    def test_fence_closer_must_match_char(self) -> None:
        """Backtick fence cannot be closed by tilde fence."""
        outline = "1:```\n2:## Inside\n3:~~~\n4:## Still inside\n5:```"
        entries = parse_outline_entries(outline)

        # ~~~ does not close the ``` fence — treated as content
        assert entries[2].is_fence is False  # ~~~ is not treated as a closer
        assert entries[2].in_fence is True
        assert entries[3].in_fence is True  # Still inside the backtick fence
        assert entries[4].is_fence is True  # ``` closes it

    def test_fence_closer_must_be_at_least_as_long(self) -> None:
        """A shorter fence marker does not close the fence."""
        outline = "1:````\n2:## Inside\n3:```\n4:## Still inside\n5:````"
        entries = parse_outline_entries(outline)

        # ``` (3 backticks) doesn't close ```` (4 backticks)
        assert entries[2].is_fence is False  # Not treated as closer
        assert entries[2].in_fence is True
        assert entries[3].in_fence is True
        assert entries[4].is_fence is True  # ```` closes it

    def test_tilde_fence(self) -> None:
        outline = "1:~~~\n2:## Inside\n3:~~~"
        entries = parse_outline_entries(outline)
        assert entries[0].is_fence is True
        assert entries[1].in_fence is True
        assert entries[2].is_fence is True

    def test_blockquote_heading_depth(self) -> None:
        outline = "1:> ## Section"
        entries = parse_outline_entries(outline)
        assert entries[0].depth == 2
        assert entries[0].is_fence is False

    def test_h6_depth(self) -> None:
        outline = "1:###### Deep"
        entries = parse_outline_entries(outline)
        assert entries[0].depth == 6

    def test_indented_heading_inside_fence(self) -> None:
        outline = "1:```yaml\n2:    ## Host\n3:```"
        entries = parse_outline_entries(outline)
        assert entries[1].depth == 2
        assert entries[1].in_fence is True
        assert entries[1].text == "    ## Host"

    def test_preserves_text_exactly(self) -> None:
        outline = "42:## Section with `code` and **bold**"
        entries = parse_outline_entries(outline)
        assert entries[0].text == "## Section with `code` and **bold**"
        assert entries[0].line_number == 42


# ---------------------------------------------------------------------------
# strip_empty_fences
# ---------------------------------------------------------------------------


class TestStripEmptyFences:
    def test_empty_list(self) -> None:
        assert strip_empty_fences([]) == []

    def test_no_fences(self) -> None:
        entries = parse_outline_entries("1:# Title\n5:## Section")
        assert strip_empty_fences(entries) == entries

    def test_empty_fence_pair_removed(self) -> None:
        outline = "1:# Title\n3:```\n5:```\n7:## After"
        entries = parse_outline_entries(outline)
        result = strip_empty_fences(entries)
        assert len(result) == 2
        assert result[0].text == "# Title"
        assert result[1].text == "## After"

    def test_non_empty_fence_pair_kept(self) -> None:
        outline = "1:# Title\n3:```\n4:## Inside\n5:```\n7:## After"
        entries = parse_outline_entries(outline)
        result = strip_empty_fences(entries)
        assert len(result) == 5  # All kept

    def test_mixed_empty_and_non_empty(self) -> None:
        outline = (
            "1:# Title\n"
            "3:```\n5:```\n"  # Empty fence pair
            "7:```python\n8:## Code heading\n9:```\n"  # Non-empty
            "11:## After"
        )
        entries = parse_outline_entries(outline)
        result = strip_empty_fences(entries)
        # Empty pair (lines 3, 5) removed; non-empty pair (7, 8, 9) kept
        assert len(result) == 5
        texts = [e.text for e in result]
        assert "# Title" in texts
        assert "## Code heading" in texts
        assert "## After" in texts

    def test_unclosed_fence_not_removed(self) -> None:
        """An unclosed fence opener is left as-is."""
        outline = "1:# Title\n3:```\n5:## Inside"
        entries = parse_outline_entries(outline)
        result = strip_empty_fences(entries)
        assert len(result) == 3  # Nothing removed


# ---------------------------------------------------------------------------
# compact_outline
# ---------------------------------------------------------------------------


class TestCompactOutline:
    def _make_entries(self, count: int, depth: int) -> list[OutlineEntry]:
        """Create a list of heading entries at a given depth."""
        return [
            OutlineEntry(
                line_number=i * 10,
                text=f"{'#' * depth} Heading {i}",
                depth=depth,
                is_fence=False,
                in_fence=False,
            )
            for i in range(1, count + 1)
        ]

    def test_already_under_limit(self) -> None:
        entries = self._make_entries(10, 2)
        result = compact_outline(entries)
        assert result == entries

    def test_exactly_at_limit(self) -> None:
        entries = self._make_entries(50, 2)
        result = compact_outline(entries)
        assert result == entries

    def test_removes_h6_first(self) -> None:
        h2 = self._make_entries(30, 2)
        h6 = self._make_entries(25, 6)
        entries = h2 + h6  # 55 entries
        result = compact_outline(entries)
        assert result is not None
        assert len(result) == 30
        assert all(e.depth == 2 for e in result)

    def test_removes_h5_after_h6(self) -> None:
        h2 = self._make_entries(30, 2)
        h5 = self._make_entries(15, 5)
        h6 = self._make_entries(10, 6)
        entries = h2 + h5 + h6  # 55 entries
        result = compact_outline(entries)
        assert result is not None
        # H6 removed first (55-10=45 ≤ 50), stops at stage 1
        assert len(result) == 45
        assert not any(e.depth == 6 for e in result)
        assert any(e.depth == 5 for e in result)  # H5 kept

    def test_removes_h5_and_h6(self) -> None:
        """Both H6 and H5 must be removed to fit under 50."""
        h2 = self._make_entries(40, 2)
        h5 = self._make_entries(8, 5)
        h6 = self._make_entries(5, 6)
        entries = h2 + h5 + h6  # 53 entries
        result = compact_outline(entries)
        assert result is not None
        # H6 removed (53-5=48 ≤ 50), stops
        assert len(result) == 48
        assert not any(e.depth == 6 for e in result)

    def test_h5_removed_when_h6_not_enough(self) -> None:
        """H6 removal alone doesn't suffice, must also remove H5."""
        h2 = self._make_entries(45, 2)
        h5 = self._make_entries(5, 5)
        h6 = self._make_entries(5, 6)
        entries = h2 + h5 + h6  # 55 entries
        result = compact_outline(entries)
        assert result is not None
        # H6 removed: 55-5=50 ≤ 50, stops
        assert len(result) == 50
        assert not any(e.depth == 6 for e in result)
        assert any(e.depth == 5 for e in result)

    def test_removes_fenced_content(self) -> None:
        """Stage 3 removes in_fence entries and fence markers."""
        headings = self._make_entries(30, 2)
        fenced = [
            OutlineEntry(100, "```", None, True, False),  # opener
            OutlineEntry(101, "## In fence 1", 2, False, True),
            OutlineEntry(102, "## In fence 2", 2, False, True),
            OutlineEntry(103, "```", None, True, False),  # closer
        ]
        extra_h3 = self._make_entries(20, 3)
        entries = headings + fenced + extra_h3  # 54 entries
        result = compact_outline(entries)
        assert result is not None
        assert len(result) == 50  # 30 H2 + 20 H3
        assert not any(e.is_fence for e in result)
        assert not any(e.in_fence for e in result)

    def test_removes_h4_then_h3(self) -> None:
        h1 = self._make_entries(10, 1)
        h2 = self._make_entries(10, 2)
        h3 = self._make_entries(20, 3)
        h4 = self._make_entries(15, 4)
        entries = h1 + h2 + h3 + h4  # 55 entries
        result = compact_outline(entries)
        assert result is not None
        # H4 removed first (55-15=40 ≤ 50), stops
        assert len(result) == 40
        assert not any(e.depth == 4 for e in result)
        assert any(e.depth == 3 for e in result)  # H3 kept

    def test_returns_none_when_irreducible(self) -> None:
        """More than 50 H1/H2 entries — cannot be reduced."""
        h1 = self._make_entries(30, 1)
        h2 = self._make_entries(25, 2)
        entries = h1 + h2  # 55 entries, all H1/H2
        result = compact_outline(entries)
        assert result is None

    def test_progressive_stops_early(self) -> None:
        """Stops at H6 removal if that's enough."""
        h2 = self._make_entries(45, 2)
        h6 = self._make_entries(10, 6)
        entries = h2 + h6  # 55 entries
        result = compact_outline(entries)
        assert result is not None
        assert len(result) == 45

    def test_custom_max_entries(self) -> None:
        entries = self._make_entries(30, 2)
        result = compact_outline(entries, max_entries=20)
        assert result is None  # All H2, can't reduce below 30


# ---------------------------------------------------------------------------
# trim_outline_to_range
# ---------------------------------------------------------------------------


class TestTrimOutlineToRange:
    def test_filters_to_range(self) -> None:
        entries = parse_outline_entries("1:# A\n10:## B\n20:## C\n30:## D")
        result = trim_outline_to_range(entries, 10, 20)
        assert len(result) == 2
        assert result[0].line_number == 10
        assert result[1].line_number == 20

    def test_inclusive_boundaries(self) -> None:
        entries = parse_outline_entries("5:# A\n10:## B\n15:## C")
        result = trim_outline_to_range(entries, 5, 15)
        assert len(result) == 3

    def test_empty_input(self) -> None:
        assert trim_outline_to_range([], 1, 100) == []

    def test_no_entries_in_range(self) -> None:
        entries = parse_outline_entries("1:# A\n100:## B")
        result = trim_outline_to_range(entries, 50, 60)
        assert result == []


# ---------------------------------------------------------------------------
# format_outline
# ---------------------------------------------------------------------------


class TestFormatOutline:
    def test_empty_list(self) -> None:
        assert format_outline([]) == ""

    def test_round_trip(self) -> None:
        original = "1:# Title\n5:## Section\n10:### Sub"
        entries = parse_outline_entries(original)
        assert format_outline(entries) == original

    def test_preserves_text(self) -> None:
        entries = [
            OutlineEntry(1, "# Title", 1, False, False),
            OutlineEntry(5, "```python", None, True, False),
            OutlineEntry(8, "```", None, True, False),
        ]
        assert format_outline(entries) == "1:# Title\n5:```python\n8:```"


# ---------------------------------------------------------------------------
# build_compaction_note
# ---------------------------------------------------------------------------


class TestBuildCompactionNote:
    def test_single_depth(self) -> None:
        entries = [
            OutlineEntry(1, "# Title", 1, False, False),
            OutlineEntry(5, "# Other", 1, False, False),
        ]
        note = build_compaction_note(entries, 200)
        assert "H1" in note
        assert "200 entries" in note
        assert "read_outline" in note

    def test_depth_range(self) -> None:
        entries = [
            OutlineEntry(1, "# Title", 1, False, False),
            OutlineEntry(5, "## Section", 2, False, False),
            OutlineEntry(10, "### Sub", 3, False, False),
        ]
        note = build_compaction_note(entries, 500)
        assert "H1-H3" in note
        assert "500 entries" in note

    def test_with_match_range(self) -> None:
        entries = [
            OutlineEntry(50, "## Section", 2, False, False),
        ]
        note = build_compaction_note(entries, 300, match_range=(42, 380))
        assert "lines 42-380" in note
        assert "300 entries" in note

    def test_no_headings(self) -> None:
        note = build_compaction_note([], 100)
        assert "no headings" in note
