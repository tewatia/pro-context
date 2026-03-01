"""Unit tests for procontext.resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from procontext.resolver import normalise_query, resolve_library

if TYPE_CHECKING:
    from procontext.models.registry import RegistryIndexes


# ---------------------------------------------------------------------------
# normalise_query
# ---------------------------------------------------------------------------


class TestNormaliseQuery:
    def test_extras_stripping(self) -> None:
        assert normalise_query("langchain[openai]") == "langchain"

    def test_extras_multiple(self) -> None:
        assert normalise_query("langchain[openai,anthropic]") == "langchain"

    def test_version_spec_gte(self) -> None:
        assert normalise_query("langchain>=0.3") == "langchain"

    def test_version_spec_complex(self) -> None:
        assert normalise_query("langchain>=0.3,<1.0") == "langchain"

    def test_version_spec_exact(self) -> None:
        assert normalise_query("httpx==0.28.0") == "httpx"

    def test_version_spec_compatible(self) -> None:
        assert normalise_query("httpx~=0.28") == "httpx"

    def test_lowercase(self) -> None:
        assert normalise_query("LangChain") == "langchain"

    def test_whitespace(self) -> None:
        assert normalise_query("  langchain  ") == "langchain"

    def test_combined(self) -> None:
        """Extras + version + case + whitespace all at once."""
        assert normalise_query("  LangChain[openai]>=0.3  ") == "langchain"

    def test_empty_after_strip(self) -> None:
        assert normalise_query("   ") == ""

    def test_caret_version(self) -> None:
        assert normalise_query("pydantic^2.0") == "pydantic"


# ---------------------------------------------------------------------------
# resolve_library — 5-step algorithm
# ---------------------------------------------------------------------------


class TestResolveLibraryStep1PackageName:
    """Step 1: Exact package name match."""

    def test_exact_pypi_package(self, indexes: RegistryIndexes) -> None:
        matches = resolve_library("langchain-openai", indexes)
        assert len(matches) == 1
        assert matches[0].library_id == "langchain"
        assert matches[0].matched_via == "package_name"
        assert matches[0].relevance == 1.0

    def test_monorepo_package(self, indexes: RegistryIndexes) -> None:
        """Monorepo sub-package resolves to the parent library."""
        matches = resolve_library("langchain-core", indexes)
        assert len(matches) == 1
        assert matches[0].library_id == "langchain"
        assert matches[0].matched_via == "package_name"

    def test_case_insensitive(self, indexes: RegistryIndexes) -> None:
        """Package lookup is case-insensitive because normalise_query lowercases."""
        matches = resolve_library("Pydantic-Settings", indexes)
        assert len(matches) == 1
        assert matches[0].library_id == "pydantic"

    def test_pip_extras_stripped(self, indexes: RegistryIndexes) -> None:
        """Pip extras are stripped before lookup."""
        matches = resolve_library("langchain[openai]>=0.3", indexes)
        assert len(matches) == 1
        assert matches[0].library_id == "langchain"
        assert matches[0].matched_via == "package_name"


class TestResolveLibraryStep2LibraryId:
    """Step 2: Exact library ID match."""

    def test_exact_id(self, indexes: RegistryIndexes) -> None:
        matches = resolve_library("pydantic", indexes)
        # "pydantic" is both a library ID and a package name.
        # Step 1 (package match) fires first, which is fine — it still resolves.
        assert len(matches) == 1
        assert matches[0].library_id == "pydantic"
        assert matches[0].relevance == 1.0

    def test_id_not_in_packages(self, indexes: RegistryIndexes) -> None:
        """When a library ID doesn't collide with any package name, step 2 fires.

        In our sample data, 'langchain' IS also a package name so step 1 fires.
        This test documents the behaviour — both paths produce the same result.
        """
        matches = resolve_library("langchain", indexes)
        assert len(matches) == 1
        assert matches[0].library_id == "langchain"
        assert matches[0].relevance == 1.0


class TestResolveLibraryStep3Alias:
    """Step 3: Alias match."""

    def test_alias(self, indexes: RegistryIndexes) -> None:
        matches = resolve_library("lang-chain", indexes)
        assert len(matches) == 1
        assert matches[0].library_id == "langchain"
        assert matches[0].matched_via == "alias"
        assert matches[0].relevance == 1.0

    def test_alias_case_insensitive(self, indexes: RegistryIndexes) -> None:
        matches = resolve_library("Lang-Chain", indexes)
        assert len(matches) == 1
        assert matches[0].library_id == "langchain"


class TestResolveLibraryStep4Fuzzy:
    """Step 4: Fuzzy match."""

    def test_fuzzy_typo(self, indexes: RegistryIndexes) -> None:
        matches = resolve_library("langchan", indexes)
        assert len(matches) >= 1
        assert matches[0].library_id == "langchain"
        assert matches[0].matched_via == "fuzzy"
        assert 0.0 < matches[0].relevance < 1.0

    def test_fuzzy_results_sorted_descending(self, indexes: RegistryIndexes) -> None:
        """Multiple fuzzy results are sorted by relevance descending."""
        matches = resolve_library("langchan", indexes)
        for i in range(len(matches) - 1):
            assert matches[i].relevance >= matches[i + 1].relevance


class TestResolveLibraryStep5NoMatch:
    """Step 5: No match."""

    def test_no_match(self, indexes: RegistryIndexes) -> None:
        matches = resolve_library("xyzzy-nonexistent", indexes)
        assert matches == []

    def test_empty_query(self, indexes: RegistryIndexes) -> None:
        matches = resolve_library("   ", indexes)
        assert matches == []


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


class TestMatchStructure:
    """Verify the shape of returned LibraryMatch objects."""

    def test_match_fields(self, indexes: RegistryIndexes) -> None:
        matches = resolve_library("langchain-openai", indexes)
        match = matches[0]
        assert match.library_id == "langchain"
        assert match.name == "LangChain"
        assert "python" in match.languages
        assert match.docs_url == "https://python.langchain.com/docs/"
        assert match.matched_via == "package_name"
        assert match.relevance == 1.0
