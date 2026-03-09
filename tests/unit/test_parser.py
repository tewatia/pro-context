"""Unit tests for the heading parser."""

from __future__ import annotations

from procontext.parser import parse_outline


class TestHeadingDetection:
    """Verify H1–H6 detection."""

    def test_h1(self) -> None:
        assert parse_outline("# Title") == "1:# Title"

    def test_h2(self) -> None:
        assert parse_outline("## Section") == "1:## Section"

    def test_h3(self) -> None:
        assert parse_outline("### Subsection") == "1:### Subsection"

    def test_h4(self) -> None:
        assert parse_outline("#### Detail") == "1:#### Detail"

    def test_h5(self) -> None:
        assert parse_outline("##### Deep") == "1:##### Deep"

    def test_h6(self) -> None:
        assert parse_outline("###### Deepest") == "1:###### Deepest"

    def test_no_headings_returns_empty(self) -> None:
        assert parse_outline("Just a paragraph.\nAnother line.") == ""

    def test_multiple_headings(self) -> None:
        content = "# Title\n\n## Section A\n\n## Section B"
        result = parse_outline(content)
        assert result == "1:# Title\n3:## Section A\n5:## Section B"

    def test_heading_with_inline_formatting(self) -> None:
        content = "## Using `stream()` for **real-time** output"
        assert parse_outline(content) == "1:## Using `stream()` for **real-time** output"

    def test_heading_requires_space_after_hashes(self) -> None:
        # "##NoSpace" is not a valid heading
        assert parse_outline("##NoSpace") == ""

    def test_all_heading_levels(self) -> None:
        content = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6"
        result = parse_outline(content)
        assert result == "1:# H1\n2:## H2\n3:### H3\n4:#### H4\n5:##### H5\n6:###### H6"

    def test_seven_hashes_not_a_heading(self) -> None:
        # 7+ hashes exceed the CommonMark H6 maximum
        assert parse_outline("####### Not a heading") == ""


class TestBlockquoteHeadings:
    """Headings prefixed with a blockquote marker are captured."""

    def test_blockquote_h1(self) -> None:
        assert parse_outline("> # Title") == "1:> # Title"

    def test_blockquote_h2(self) -> None:
        assert parse_outline("> ## Section") == "1:> ## Section"

    def test_blockquote_heading_mixed_with_structural(self) -> None:
        content = "> ## Navigation\n\n# Real Heading\n\n## Section"
        result = parse_outline(content)
        assert result == "1:> ## Navigation\n3:# Real Heading\n5:## Section"

    def test_blockquote_h5_captured(self) -> None:
        assert parse_outline("> ##### Deep") == "1:> ##### Deep"

    def test_blockquote_h6_captured(self) -> None:
        assert parse_outline("> ###### Deepest") == "1:> ###### Deepest"

    def test_deep_blockquote_ignored(self) -> None:
        # >> ## heading has two > markers — not matched
        assert parse_outline(">> ## heading") == ""

    def test_blockquote_with_space_before_hashes(self) -> None:
        # "> ## heading" with a space between > and ## — still matched
        assert parse_outline(">  ## Section") == "1:>  ## Section"


class TestFenceLines:
    """Fence opener/closer lines are emitted; headings inside are included."""

    def test_fence_opener_emitted(self) -> None:
        content = "```python\n# comment\n```"
        result = parse_outline(content)
        assert "1:```python" in result

    def test_fence_closer_emitted(self) -> None:
        content = "```\n# comment\n```"
        result = parse_outline(content)
        assert "3:```" in result

    def test_heading_inside_fence_emitted(self) -> None:
        content = "# Real heading\n```\n# Inside fence\n```\n## After"
        result = parse_outline(content)
        assert "1:# Real heading" in result
        assert "3:# Inside fence" in result
        assert "5:## After" in result

    def test_fence_lines_carry_line_numbers(self) -> None:
        content = "# Title\n\n```python\n## code heading\n```"
        result = parse_outline(content)
        assert result == "1:# Title\n3:```python\n4:## code heading\n5:```"

    def test_tilde_fence_emitted(self) -> None:
        content = "~~~\n## Inside\n~~~"
        result = parse_outline(content)
        assert "1:~~~" in result
        assert "2:## Inside" in result
        assert "3:~~~" in result

    def test_fence_with_info_string_emitted(self) -> None:
        content = "```yaml openapi.json\n## Host\n```"
        result = parse_outline(content)
        assert "1:```yaml openapi.json" in result

    def test_extended_fence_emitted(self) -> None:
        # 4-backtick fence — opener and closer both captured
        content = "````markdown\n## Example\n````"
        result = parse_outline(content)
        assert "1:````markdown" in result
        assert "2:## Example" in result
        assert "3:````" in result

    def test_indented_heading_inside_fence_preserves_indent(self) -> None:
        # Heading inside a code block retains its original indentation
        content = "```yaml\n    ## Host\n```"
        result = parse_outline(content)
        assert "2:    ## Host" in result

    def test_four_space_indented_fence_not_detected(self) -> None:
        # 4-space indent = indented code block in CommonMark, not a fence
        content = "    ```python\n## Real heading"
        result = parse_outline(content)
        assert result == "2:## Real heading"

    def test_no_headings_in_fence_only_fence_lines_emitted(self) -> None:
        content = "```\nsome code\n```\n## After"
        result = parse_outline(content)
        assert result == "1:```\n3:```\n4:## After"


class TestLineNumbering:
    """Verify 1-based line numbering and blank line counting."""

    def test_one_based_numbering(self) -> None:
        assert parse_outline("# First") == "1:# First"

    def test_blank_lines_counted(self) -> None:
        content = "\n\n# Third line"
        result = parse_outline(content)
        assert result == "3:# Third line"

    def test_fence_lines_emitted_with_correct_numbers(self) -> None:
        content = "```\n```\n# After fence"
        result = parse_outline(content)
        assert result == "1:```\n2:```\n3:# After fence"

    def test_complex_numbering(self) -> None:
        content = (
            "# Title\n"  # line 1
            "\n"  # line 2
            "## Overview\n"  # line 3
            "\n"  # line 4
            "Some text.\n"  # line 5
            "\n"  # line 6
            "```python\n"  # line 7  — fence opener
            "# comment\n"  # line 8  — heading inside fence
            "```\n"  # line 9  — fence closer
            "\n"  # line 10
            "### Details\n"  # line 11
            "More text."  # line 12
        )
        result = parse_outline(content)
        assert result == (
            "1:# Title\n3:## Overview\n7:```python\n8:# comment\n9:```\n11:### Details"
        )


class TestIndentedHeadings:
    """CommonMark allows up to 3 spaces of indentation before the # character."""

    def test_one_space_indent(self) -> None:
        assert parse_outline(" # Title") == "1: # Title"

    def test_two_space_indent(self) -> None:
        assert parse_outline("  ## Section") == "1:  ## Section"

    def test_three_space_indent(self) -> None:
        assert parse_outline("   ### Sub") == "1:   ### Sub"

    def test_four_space_indent_captured(self) -> None:
        # We match on stripped lines so indented headings inside code blocks
        # (e.g. "    ## Host" in a YAML block) are captured. As a side effect,
        # a 4-space indented line outside a fence is also captured — acceptable
        # given the stateless design.
        assert parse_outline("    # Heading") == "1:    # Heading"

    def test_indented_heading_preserves_original_line_in_output(self) -> None:
        result = parse_outline("  ## Section")
        assert result == "1:  ## Section"


# ---------------------------------------------------------------------------
# Realistic page fixtures used by TestRealWorldPages
# ---------------------------------------------------------------------------

# Mirrors the structure of comments.txt: blockquote nav hint, H1 title,
# ## section, a 4-backtick YAML fence whose description field contains
# ##-prefixed headings, then structural H2/H3/H4/H5 below.
_API_REFERENCE_PAGE = (
    "> ## Documentation Index\n"  # 1
    "> Fetch the complete docs at: https://docs.langchain.com/llms.txt\n"  # 2
    "> Use this file before exploring further.\n"  # 3
    "\n"  # 4
    "# Authenticate\n"  # 5
    "\n"  # 6
    "> Get OAuth token or start authentication flow if needed.\n"  # 7
    "\n"  # 8
    "## OpenAPI\n"  # 9
    "\n"  # 10
    "````yaml https://api.host.langchain.com/openapi.json\n"  # 11
    "openapi: 3.1.0\n"  # 12
    "info:\n"  # 13
    "  description: >\n"  # 14
    "    ## Host\n"  # 15
    "    https://api.host.langchain.com\n"  # 16
    "\n"  # 17
    "    ## Authentication\n"  # 18
    "    Set the X-Api-Key header.\n"  # 19
    "\n"  # 20
    "    ## Versioning\n"  # 21
    "    Each endpoint is prefixed with a version.\n"  # 22
    "````\n"  # 23
    "\n"  # 24
    "## Error Codes\n"  # 25
    "\n"  # 26
    "### 401 Unauthorized\n"  # 27
    "\n"  # 28
    "#### 422 Validation Error\n"  # 29
    "\n"  # 30
    "##### H5 Captured\n"  # 31
    "###### H6 Captured\n"  # 32
    "####### Not Captured\n"  # 33
)

# Python tutorial with code blocks that contain # comments.
_PYTHON_TUTORIAL = (
    "# Streaming with LangChain\n"  # 1
    "\n"  # 2
    "## Overview\n"  # 3
    "\n"  # 4
    "Use `.stream()` for real-time output.\n"  # 5
    "\n"  # 6
    "## Basic Usage\n"  # 7
    "\n"  # 8
    "```python\n"  # 9
    "# Initialize the model\n"  # 10
    "model = ChatOpenAI()\n"  # 11
    "\n"  # 12
    "# Stream responses\n"  # 13
    'for chunk in model.stream("Hello"):\n'  # 14
    "    print(chunk.content)\n"  # 15
    "```\n"  # 16
    "\n"  # 17
    "### Async Streaming\n"  # 18
    "\n"  # 19
    "```python\n"  # 20
    "# Use astream for async\n"  # 21
    'async for chunk in model.astream("Hello"):\n'  # 22
    "    print(chunk.content)\n"  # 23
    "```\n"  # 24
    "\n"  # 25
    "## Advanced\n"  # 26
)


class TestDepthLimit:
    """H1–H6 all captured; 7+ hashes excluded in every context."""

    def test_all_heading_levels_in_all_contexts(self) -> None:
        content = (
            "# H1 out\n"  # 1
            "## H2 out\n"  # 2
            "### H3 out\n"  # 3
            "#### H4 out\n"  # 4
            "##### H5 out\n"  # 5
            "###### H6 out\n"  # 6
            "```\n"  # 7  fence opener
            "# H1 in\n"  # 8
            "## H2 in\n"  # 9
            "### H3 in\n"  # 10
            "#### H4 in\n"  # 11
            "##### H5 in\n"  # 12
            "###### H6 in\n"  # 13
            "```\n"  # 14 fence closer
            "> # H1 bq\n"  # 15
            "> ## H2 bq\n"  # 16
            "> ### H3 bq\n"  # 17
            "> #### H4 bq\n"  # 18
            "> ##### H5 bq\n"  # 19
            "> ###### H6 bq"  # 20
        )
        result = parse_outline(content)

        # H1–H6 captured in every context
        for heading in ("H1 out", "H2 out", "H3 out", "H4 out", "H5 out", "H6 out"):
            assert heading in result, f"expected {heading!r} in result"
        for heading in ("H1 in", "H2 in", "H3 in", "H4 in", "H5 in", "H6 in"):
            assert heading in result, f"expected {heading!r} in result"
        for heading in ("H1 bq", "H2 bq", "H3 bq", "H4 bq", "H5 bq", "H6 bq"):
            assert heading in result, f"expected {heading!r} in result"

    def test_seven_hashes_excluded_everywhere(self) -> None:
        content = "####### out\n```\n####### in\n```\n> ####### bq"
        result = parse_outline(content)
        assert "####### out" not in result
        assert "####### in" not in result
        assert "####### bq" not in result

    def test_h6_inside_fence_captured(self) -> None:
        content = "```\n###### deep inside fence\n```"
        assert "deep inside fence" in parse_outline(content)

    def test_h6_in_blockquote_captured(self) -> None:
        assert "###### deep in blockquote" in parse_outline("> ###### deep in blockquote")


class TestRealWorldPages:
    """Parser behaviour on realistic full-page documentation content."""

    def test_api_reference_page_structural_headings(self) -> None:
        result = parse_outline(_API_REFERENCE_PAGE)

        # Structural headings captured with exact line numbers
        assert "1:> ## Documentation Index" in result
        assert "5:# Authenticate" in result
        assert "9:## OpenAPI" in result
        assert "25:## Error Codes" in result
        assert "27:### 401 Unauthorized" in result
        assert "29:#### 422 Validation Error" in result

    def test_api_reference_page_fence_context(self) -> None:
        result = parse_outline(_API_REFERENCE_PAGE)

        # Fence opener and closer emitted so agent knows code block boundaries
        assert "11:````yaml https://api.host.langchain.com/openapi.json" in result
        assert "23:````" in result

        # YAML description headings captured with original indentation
        assert "15:    ## Host" in result
        assert "18:    ## Authentication" in result
        assert "21:    ## Versioning" in result

    def test_api_reference_page_exclusions(self) -> None:
        result = parse_outline(_API_REFERENCE_PAGE)

        # H5/H6 captured; 7+ hashes excluded
        assert "31:##### H5 Captured" in result
        assert "32:###### H6 Captured" in result
        assert "Not Captured" not in result

        # Prose blockquote lines (no # prefix) are not headings
        assert "Fetch the complete docs" not in result
        assert "Get OAuth token" not in result
        assert "Set the X-Api-Key" not in result

    def test_python_tutorial_structural_headings(self) -> None:
        result = parse_outline(_PYTHON_TUTORIAL)

        assert "1:# Streaming with LangChain" in result
        assert "3:## Overview" in result
        assert "7:## Basic Usage" in result
        assert "18:### Async Streaming" in result
        assert "26:## Advanced" in result

    def test_python_tutorial_code_comments_captured(self) -> None:
        result = parse_outline(_PYTHON_TUTORIAL)

        # # comments inside Python fences are captured
        assert "10:# Initialize the model" in result
        assert "13:# Stream responses" in result
        assert "21:# Use astream for async" in result

        # Fence lines bracket each code block
        assert "9:```python" in result
        assert "16:```" in result
        assert "20:```python" in result
        assert "24:```" in result

    def test_python_tutorial_non_heading_code_lines_excluded(self) -> None:
        result = parse_outline(_PYTHON_TUTORIAL)

        # Regular code lines are not captured
        assert "model = ChatOpenAI()" not in result
        assert "print(chunk.content)" not in result
        assert "async for chunk" not in result


class TestFalsePositives:
    """Lines that look heading-like but must not be captured."""

    def test_hash_in_prose_not_captured(self) -> None:
        # "Issue #42" has # in the middle of a line, not at the start
        assert parse_outline("Issue #42 was fixed in this release.") == ""

    def test_blockquote_without_hash_not_captured(self) -> None:
        # A blockquote with no heading content is just prose
        assert parse_outline("> This is just a note, not a heading.") == ""

    def test_dash_front_matter_not_a_fence(self) -> None:
        # "---" is a horizontal rule / setext underline / front matter delimiter,
        # not a fence marker. Headings after it are captured normally.
        content = "---\ntitle: My Page\n---\n\n# Real Heading"
        result = parse_outline(content)
        assert "5:# Real Heading" in result
        assert "---" not in result  # dash lines are invisible to the parser

    def test_unclosed_fence_does_not_suppress_subsequent_headings(self) -> None:
        # Stateless design: an unclosed fence has no effect on later headings
        content = "# Before\n```\n# Inside\n## Also inside\n# No close fence\n## After"
        result = parse_outline(content)
        assert "# Before" in result
        assert "# Inside" in result
        assert "## Also inside" in result
        assert "# No close fence" in result
        assert "## After" in result

    def test_table_cell_hash_not_captured(self) -> None:
        # Markdown table cells starting with | are not headings
        content = "| ## Column | Value |\n|------------|-------|\n| data | val |"
        assert parse_outline(content) == ""

    def test_inline_code_span_not_a_fence(self) -> None:
        # A single backtick is not a fence opener (requires 3+)
        content = "Use `# comment` to add comments.\n## Real heading"
        result = parse_outline(content)
        assert result == "2:## Real heading"


class TestEdgeCases:
    """Edge cases: empty input, large documents, BOM handling."""

    def test_empty_string(self) -> None:
        assert parse_outline("") == ""

    def test_only_code_fences_no_headings(self) -> None:
        content = "```\nsome code\n```"
        result = parse_outline(content)
        assert result == "1:```\n3:```"

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

        result = parse_outline(content)
        result_lines = result.split("\n")
        assert len(result_lines) == num_lines // 100

    def test_heading_at_last_line_no_trailing_newline(self) -> None:
        content = "Some text\n## Final heading"
        result = parse_outline(content)
        assert result == "2:## Final heading"

    def test_only_whitespace_lines(self) -> None:
        content = "   \n  \n   "
        assert parse_outline(content) == ""

    def test_utf8_bom_does_not_shift_line_numbers(self) -> None:
        """A UTF-8 BOM (U+FEFF) prepended to content must not shift line numbers."""
        bom = "\ufeff"
        content = f"{bom}# Title\n## Section"
        result = parse_outline(content)
        assert "# Title" in result
        assert result.startswith("1:")
