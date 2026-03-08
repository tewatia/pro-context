"""Unit tests for read_page private helper functions.

Tests _should_probe_md and _with_md_extension in isolation — no network,
no cache, no AppState. Covers the full space of URL shapes these helpers
will encounter in the wild.
"""

from __future__ import annotations

from procontext.tools.read_page import _should_probe_md, _with_md_extension

# ---------------------------------------------------------------------------
# _should_probe_md
# ---------------------------------------------------------------------------


class TestShouldProbeMd:
    # --- should probe ---

    def test_no_extension(self) -> None:
        assert _should_probe_md("https://example.com/docs/streaming") is True

    def test_no_extension_deep_path(self) -> None:
        assert _should_probe_md("https://example.com/a/b/c/d") is True

    def test_no_extension_single_segment(self) -> None:
        assert _should_probe_md("https://example.com/about") is True

    def test_version_segment_major_minor(self) -> None:
        # v1.2 — the suffix .2 is numeric, not a real extension
        assert _should_probe_md("https://example.com/docs/v1.2") is True

    def test_version_segment_patch(self) -> None:
        # v1.2.3 — splitext gives .3 (numeric)
        assert _should_probe_md("https://example.com/docs/v1.2.3") is True

    def test_bare_version(self) -> None:
        assert _should_probe_md("https://example.com/docs/1.0") is True

    def test_year_month(self) -> None:
        # 2024.01 — numeric suffix
        assert _should_probe_md("https://example.com/releases/2024.01") is True

    def test_mixed_alphanumeric_extension(self) -> None:
        # .v2rc — has a digit, not all alphabetic
        assert _should_probe_md("https://example.com/page.v2rc") is True

    def test_h5_extension(self) -> None:
        # .h5 — has digit, treated as not a real doc extension
        assert _should_probe_md("https://example.com/data.h5") is True

    def test_fragment_only(self) -> None:
        # Fragment is client-side — server sees the same path, still worth probing
        assert _should_probe_md("https://example.com/docs/page#section") is True

    def test_hidden_file_dot_prefix(self) -> None:
        # splitext('.hidden') = ('.hidden', '') — treated as extensionless
        assert _should_probe_md("https://example.com/docs/.hidden") is True

    # --- should NOT probe ---

    def test_md_extension(self) -> None:
        assert _should_probe_md("https://example.com/docs/page.md") is False

    def test_txt_extension(self) -> None:
        assert _should_probe_md("https://example.com/llms.txt") is False

    def test_html_extension(self) -> None:
        assert _should_probe_md("https://example.com/docs/index.html") is False

    def test_css_extension(self) -> None:
        assert _should_probe_md("https://example.com/style.css") is False

    def test_json_extension(self) -> None:
        assert _should_probe_md("https://example.com/openapi.json") is False

    def test_rst_extension(self) -> None:
        assert _should_probe_md("https://example.com/README.rst") is False

    def test_uppercase_extension(self) -> None:
        assert _should_probe_md("https://example.com/CHANGELOG.MD") is False
        assert _should_probe_md("https://example.com/index.HTML") is False

    def test_compound_extension_tar_gz(self) -> None:
        # splitext gives .gz — alphabetic, skip probe
        assert _should_probe_md("https://example.com/archive.tar.gz") is False

    def test_trailing_slash(self) -> None:
        # Empty last segment — appending .md would produce /docs/page/.md
        assert _should_probe_md("https://example.com/docs/page/") is False

    def test_trailing_slash_root(self) -> None:
        assert _should_probe_md("https://example.com/") is False

    def test_domain_only_no_path(self) -> None:
        assert _should_probe_md("https://example.com") is False

    def test_query_string_skips_probe(self) -> None:
        # Query params → dynamic server, .md probe would always 404
        assert _should_probe_md("https://example.com/docs/page?v=1") is False

    def test_query_string_multiple_params(self) -> None:
        assert _should_probe_md("https://example.com/docs/page?a=1&b=2") is False

    def test_query_and_fragment(self) -> None:
        assert _should_probe_md("https://example.com/docs/page?v=1#section") is False

    def test_md_extension_with_query(self) -> None:
        # Already has extension AND query — both independently skip probe
        assert _should_probe_md("https://example.com/docs/page.md?v=1") is False

    def test_md_extension_with_fragment(self) -> None:
        assert _should_probe_md("https://example.com/docs/page.md#section") is False


# ---------------------------------------------------------------------------
# _with_md_extension
# ---------------------------------------------------------------------------


class TestWithMdExtension:
    def test_plain_path(self) -> None:
        result = _with_md_extension("https://example.com/docs/page")
        assert result == "https://example.com/docs/page.md"

    def test_deep_path(self) -> None:
        result = _with_md_extension("https://example.com/a/b/c/page")
        assert result == "https://example.com/a/b/c/page.md"

    def test_fragment_goes_after_md(self) -> None:
        # .md must be in the path, not inside the fragment
        result = _with_md_extension("https://example.com/docs/page#section")
        assert result == "https://example.com/docs/page.md#section"

    def test_fragment_complex(self) -> None:
        result = _with_md_extension("https://example.com/docs/page#heading-1-2")
        assert result == "https://example.com/docs/page.md#heading-1-2"

    def test_query_string(self) -> None:
        # .md must be in the path, not inside the query string
        result = _with_md_extension("https://example.com/docs/page?v=latest")
        assert result == "https://example.com/docs/page.md?v=latest"

    def test_query_with_multiple_params(self) -> None:
        result = _with_md_extension("https://example.com/docs/page?a=1&b=2")
        assert result == "https://example.com/docs/page.md?a=1&b=2"

    def test_query_and_fragment(self) -> None:
        # Both must be preserved, .md in path only
        result = _with_md_extension("https://example.com/docs/page?v=1#section")
        assert result == "https://example.com/docs/page.md?v=1#section"

    def test_preserves_scheme_and_host(self) -> None:
        result = _with_md_extension("https://docs.python.org/3/library/asyncio")
        assert result.startswith("https://docs.python.org")
        assert result.endswith(".md")

    def test_port_preserved(self) -> None:
        result = _with_md_extension("https://example.com:8080/docs/page")
        assert result == "https://example.com:8080/docs/page.md"

    def test_version_in_path(self) -> None:
        result = _with_md_extension("https://example.com/docs/v1.2")
        assert result == "https://example.com/docs/v1.2.md"
