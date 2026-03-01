"""Shared test fixtures for the procontext test suite."""

from __future__ import annotations

import pytest

from procontext.models.registry import RegistryEntry, RegistryIndexes, RegistryPackages
from procontext.registry import build_indexes


@pytest.fixture()
def sample_entries() -> list[RegistryEntry]:
    """Minimal registry entries for testing resolution logic."""
    return [
        RegistryEntry(
            id="langchain",
            name="LangChain",
            docs_url="https://python.langchain.com/docs/",
            repo_url="https://github.com/langchain-ai/langchain",
            languages=["python"],
            packages=RegistryPackages(
                pypi=["langchain", "langchain-openai", "langchain-core"],
                npm=[],
            ),
            aliases=["lang-chain"],
            llms_txt_url="https://python.langchain.com/llms.txt",
        ),
        RegistryEntry(
            id="pydantic",
            name="Pydantic",
            docs_url="https://docs.pydantic.dev/latest/",
            repo_url="https://github.com/pydantic/pydantic",
            languages=["python"],
            packages=RegistryPackages(
                pypi=["pydantic", "pydantic-settings"],
                npm=[],
            ),
            aliases=[],
            llms_txt_url="https://docs.pydantic.dev/llms.txt",
        ),
    ]


@pytest.fixture()
def indexes(sample_entries: list[RegistryEntry]) -> RegistryIndexes:
    """Pre-built indexes from sample_entries."""
    return build_indexes(sample_entries)
