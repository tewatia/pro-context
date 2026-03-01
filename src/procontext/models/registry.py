from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, field_validator


class RegistryPackages(BaseModel):
    pypi: list[str] = []
    npm: list[str] = []


class RegistryEntry(BaseModel):
    """Single entry in known-libraries.json."""

    id: str
    name: str
    docs_url: str | None = None
    repo_url: str | None = None
    languages: list[str] = []
    packages: RegistryPackages = RegistryPackages()
    aliases: list[str] = []
    llms_txt_url: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", v):
            raise ValueError(f"Invalid library ID: {v!r}")
        return v


class LibraryMatch(BaseModel):
    """Single result returned by resolve_library."""

    library_id: str
    name: str
    languages: list[str]
    docs_url: str | None
    matched_via: str  # "package_name" | "library_id" | "alias" | "fuzzy"
    relevance: float  # 0.0–1.0


@dataclass
class RegistryIndexes:
    """In-memory indexes built from known-libraries.json at startup.

    Four dicts rebuilt in a single pass (<100ms for 1,000 entries).
    """

    # package name (lowercase) → library ID  e.g. "langchain-openai" → "langchain"
    by_package: dict[str, str] = field(default_factory=dict)

    # library ID → full registry entry
    by_id: dict[str, RegistryEntry] = field(default_factory=dict)

    # alias (lowercase) → library ID  e.g. "lang-chain" → "langchain"
    by_alias: dict[str, str] = field(default_factory=dict)

    # flat list of (term, library_id) pairs for fuzzy matching
    # populated from all IDs + package names + aliases (lowercased)
    fuzzy_corpus: list[tuple[str, str]] = field(default_factory=list)
