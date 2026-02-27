"""Unit tests for the heading parser."""

from __future__ import annotations

from procontext.parser import parse_headings


class TestHeadingDetection:
    """Verify H1–H4 detection and H5+ exclusion."""

    def test_h1(self) -> None:
        assert parse_headings("# Title") == "1: # Title"

    def test_h2(self) -> None:
        assert parse_headings("## Section") == "1: ## Section"

    def test_h3(self) -> None:
        assert parse_headings("### Subsection") == "1: ### Subsection"

    def test_h4(self) -> None:
        assert parse_headings("#### Detail") == "1: #### Detail"

    def test_h5_ignored(self) -> None:
        assert parse_headings("##### Too deep") == ""

    def test_h6_ignored(self) -> None:
        assert parse_headings("###### Way too deep") == ""

    def test_no_headings_returns_empty(self) -> None:
        assert parse_headings("Just a paragraph.\nAnother line.") == ""

    def test_multiple_headings(self) -> None:
        content = "# Title\n\n## Section A\n\n## Section B"
        result = parse_headings(content)
        assert result == "1: # Title\n3: ## Section A\n5: ## Section B"

    def test_heading_with_inline_formatting(self) -> None:
        content = "## Using `stream()` for **real-time** output"
        assert parse_headings(content) == "1: ## Using `stream()` for **real-time** output"

    def test_heading_requires_space_after_hashes(self) -> None:
        # "##NoSpace" is not a valid heading
        assert parse_headings("##NoSpace") == ""

    def test_mixed_heading_levels(self) -> None:
        content = "# H1\n## H2\n### H3\n#### H4\n##### H5"
        result = parse_headings(content)
        assert result == "1: # H1\n2: ## H2\n3: ### H3\n4: #### H4"


class TestCodeFenceSuppression:
    """Verify headings inside code fences are excluded."""

    def test_backtick_fence_suppresses(self) -> None:
        content = "# Real heading\n```\n# Not a heading\n```\n## Another real"
        result = parse_headings(content)
        assert result == "1: # Real heading\n5: ## Another real"

    def test_tilde_fence_suppresses(self) -> None:
        content = "# Real heading\n~~~\n# Not a heading\n~~~\n## Another real"
        result = parse_headings(content)
        assert result == "1: # Real heading\n5: ## Another real"

    def test_fence_with_language_specifier(self) -> None:
        content = "# Top\n```python\n# comment, not heading\n```\n## Bottom"
        result = parse_headings(content)
        assert result == "1: # Top\n5: ## Bottom"

    def test_mismatched_fence_does_not_close(self) -> None:
        # Opened with backtick, tilde does not close it
        content = "# Before\n```\n# Inside\n~~~\n# Still inside\n```\n## After"
        result = parse_headings(content)
        assert result == "1: # Before\n7: ## After"

    def test_tilde_open_backtick_does_not_close(self) -> None:
        content = "# Before\n~~~\n# Inside\n```\n# Still inside\n~~~\n## After"
        result = parse_headings(content)
        assert result == "1: # Before\n7: ## After"

    def test_multiple_code_blocks(self) -> None:
        content = (
            "# Heading 1\n"
            "```\n# code\n```\n"
            "## Heading 2\n"
            "~~~\n# code\n~~~\n"
            "### Heading 3"
        )
        result = parse_headings(content)
        assert result == "1: # Heading 1\n5: ## Heading 2\n9: ### Heading 3"

    def test_unclosed_fence_suppresses_rest(self) -> None:
        content = "# Before\n```\n# Inside\n## Also inside"
        result = parse_headings(content)
        assert result == "1: # Before"


class TestLineNumbering:
    """Verify 1-based line numbering and blank line counting."""

    def test_one_based_numbering(self) -> None:
        content = "# First"
        assert parse_headings(content) == "1: # First"

    def test_blank_lines_counted(self) -> None:
        content = "\n\n# Third line"
        result = parse_headings(content)
        assert result == "3: # Third line"

    def test_fence_lines_not_emitted(self) -> None:
        # Fence lines (``` / ~~~) themselves are consumed, not emitted
        content = "```\n```\n# After fence"
        result = parse_headings(content)
        assert result == "3: # After fence"

    def test_complex_numbering(self) -> None:
        content = (
            "# Title\n"        # line 1
            "\n"               # line 2
            "## Overview\n"    # line 3
            "\n"               # line 4
            "Some text.\n"     # line 5
            "\n"               # line 6
            "```python\n"      # line 7
            "# comment\n"      # line 8
            "```\n"            # line 9
            "\n"               # line 10
            "### Details\n"    # line 11
            "More text."       # line 12
        )
        result = parse_headings(content)
        assert result == "1: # Title\n3: ## Overview\n11: ### Details"


class TestEdgeCases:
    """Edge cases: empty input, all code, large documents."""

    def test_empty_string(self) -> None:
        assert parse_headings("") == ""

    def test_only_code_blocks(self) -> None:
        content = "```\n# heading\n## heading\n```"
        assert parse_headings(content) == ""

    def test_large_document_over_1mb(self) -> None:
        # >1MB document with headings every 100 lines
        num_lines = 9_000
        body_line = "Line " + ("x" * 120)
        lines = []
        for i in range(num_lines):
            if i % 100 == 0:
                lines.append(f"## Section {i // 100}")
            else:
                lines.append(body_line)
        content = "\n".join(lines)
        assert len(content.encode("utf-8")) > 1_048_576

        result = parse_headings(content)
        result_lines = result.split("\n")
        assert len(result_lines) == num_lines // 100

    def test_deeply_nested_unclosed_fences(self) -> None:
        # 100+ unclosed fence opens — parser should not crash
        lines = ["# Before"]
        for _ in range(150):
            lines.append("```")
            lines.append("# Inside")
        content = "\n".join(lines)
        # Should terminate and return at least the heading before the fences
        result = parse_headings(content)
        assert "1: # Before" in result

    def test_heading_at_last_line_no_trailing_newline(self) -> None:
        content = "Some text\n## Final heading"
        result = parse_headings(content)
        assert result == "2: ## Final heading"

    def test_only_whitespace_lines(self) -> None:
        content = "   \n  \n   "
        assert parse_headings(content) == ""
