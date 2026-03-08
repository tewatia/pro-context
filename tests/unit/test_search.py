"""Unit tests for procontext.search — build_matcher and search_lines."""

from __future__ import annotations

import re

import pytest

from procontext.search import build_matcher, search_lines

# Sample content used across tests
_CONTENT = """\
# Streaming

## Overview

LangChain supports streaming.

## Streaming with Chat Models

Details here.

### Using .stream()

The `.stream()` method returns an iterator.

### Using .astream()

The `.astream()` method is async.

## Streaming with Chains

Chain streaming details."""


# ---------------------------------------------------------------------------
# build_matcher
# ---------------------------------------------------------------------------


class TestBuildMatcherLiteral:
    def test_literal_match_found(self) -> None:
        matcher = build_matcher("streaming")
        result = search_lines(_CONTENT, matcher)
        assert len(result.matches) > 0
        assert any(m.content == "LangChain supports streaming." for m in result.matches)

    def test_literal_no_match(self) -> None:
        matcher = build_matcher("xyzzy_nonexistent")
        result = search_lines(_CONTENT, matcher)
        assert result.matches == []

    def test_literal_escapes_regex_chars(self) -> None:
        """Literal mode must escape regex metacharacters."""
        matcher = build_matcher(".stream()")
        result = search_lines(_CONTENT, matcher)
        # Should match the literal ".stream()" — not treat dot/parens as regex
        assert any(".stream()" in m.content for m in result.matches)


class TestBuildMatcherRegex:
    def test_regex_match(self) -> None:
        matcher = build_matcher(r"\.a?stream\(\)", mode="regex")
        result = search_lines(_CONTENT, matcher)
        assert len(result.matches) >= 2

    def test_regex_invalid_raises(self) -> None:
        with pytest.raises(re.error):
            build_matcher("[invalid", mode="regex")


class TestBuildMatcherSmartCase:
    def test_smart_case_lowercase_insensitive(self) -> None:
        """All-lowercase query matches any case."""
        matcher = build_matcher("streaming")
        result = search_lines(_CONTENT, matcher)
        # Should match "Streaming" (title case) and "streaming" (lowercase)
        lines = [m.content for m in result.matches]
        assert any("Streaming" in line for line in lines)
        assert any("streaming" in line for line in lines)

    def test_smart_case_mixed_sensitive(self) -> None:
        """Mixed-case query is case-sensitive."""
        matcher = build_matcher("Streaming")
        result = search_lines(_CONTENT, matcher)
        # Should match "Streaming" but NOT "streaming" (lowercase in body text)
        for m in result.matches:
            assert "Streaming" in m.content


class TestBuildMatcherCaseMode:
    def test_case_mode_insensitive(self) -> None:
        """Explicit insensitive overrides smart case."""
        matcher = build_matcher("Streaming", case_mode="insensitive")
        result = search_lines(_CONTENT, matcher)
        lines = [m.content for m in result.matches]
        assert any("streaming" in line for line in lines)

    def test_case_mode_sensitive(self) -> None:
        """Explicit sensitive makes lowercase query case-sensitive."""
        matcher = build_matcher("streaming", case_mode="sensitive")
        result = search_lines(_CONTENT, matcher)
        # "streaming" appears in body text but "Streaming" headings should not match
        for m in result.matches:
            assert "streaming" in m.content


class TestBuildMatcherWholeWord:
    def test_whole_word_matches_boundary(self) -> None:
        """'stream' with whole_word=True should NOT match 'streaming'."""
        matcher = build_matcher("stream", whole_word=True)
        result = search_lines(_CONTENT, matcher)
        for m in result.matches:
            assert "streaming" not in m.content.lower()

    def test_whole_word_false_matches_substring(self) -> None:
        """'stream' without whole_word matches 'streaming'."""
        matcher = build_matcher("stream", whole_word=False)
        result = search_lines(_CONTENT, matcher)
        assert any("streaming" in m.content.lower() for m in result.matches)


# ---------------------------------------------------------------------------
# search_lines — pagination
# ---------------------------------------------------------------------------


class TestSearchLinesPagination:
    def test_offset_skips_early_lines(self) -> None:
        matcher = build_matcher("streaming")
        # First match is on line 5 ("LangChain supports streaming.")
        result = search_lines(_CONTENT, matcher, offset=6)
        for m in result.matches:
            assert m.line_number >= 6

    def test_max_results_limits_output(self) -> None:
        matcher = build_matcher("stream")  # matches many lines
        result = search_lines(_CONTENT, matcher, max_results=2)
        assert len(result.matches) <= 2

    def test_has_more_true_when_more_matches(self) -> None:
        matcher = build_matcher("stream")  # matches many lines
        result = search_lines(_CONTENT, matcher, max_results=1)
        assert result.has_more is True
        assert result.next_offset is not None

    def test_has_more_false_when_exhausted(self) -> None:
        matcher = build_matcher("streaming")
        result = search_lines(_CONTENT, matcher, max_results=100)
        assert result.has_more is False
        assert result.next_offset is None

    def test_empty_content(self) -> None:
        matcher = build_matcher("anything")
        result = search_lines("", matcher)
        assert result.matches == []
        assert result.has_more is False
        assert result.next_offset is None

    def test_offset_beyond_content(self) -> None:
        matcher = build_matcher("streaming")
        result = search_lines(_CONTENT, matcher, offset=9999)
        assert result.matches == []
        assert result.has_more is False

    def test_line_numbers_are_one_based(self) -> None:
        matcher = build_matcher("# Streaming")
        result = search_lines(_CONTENT, matcher)
        assert result.matches[0].line_number == 1

    def test_pagination_continues_correctly(self) -> None:
        """Two paginated calls should cover all matches without overlap."""
        matcher = build_matcher("stream")
        first = search_lines(_CONTENT, matcher, max_results=2)
        assert first.has_more is True
        assert first.next_offset is not None

        second = search_lines(_CONTENT, matcher, offset=first.next_offset, max_results=100)
        first_line_numbers = {m.line_number for m in first.matches}
        second_line_numbers = {m.line_number for m in second.matches}
        assert first_line_numbers.isdisjoint(second_line_numbers)
