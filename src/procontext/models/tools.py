from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from procontext.models.registry import LibraryMatch


class ResolveLibraryInput(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        if len(v) > 500:
            raise ValueError("query must not exceed 500 characters")
        return v


class ResolveLibraryOutput(BaseModel):
    matches: list[LibraryMatch] = Field(
        description="Ranked list of matching libraries, sorted by relevance descending."
    )


class ReadPageInput(BaseModel):
    url: str
    offset: int = 1
    limit: int = 500
    view: Literal["outline", "full"] = "full"

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 2048:
            raise ValueError("url must not exceed 2048 characters")
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must use http or https scheme")
        return v

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 1:
            raise ValueError("offset must be >= 1")
        return v

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v < 1:
            raise ValueError("limit must be >= 1")
        return v


class ReadPageOutput(BaseModel):
    url: str = Field(description="The URL of the fetched page.")
    outline: str = Field(
        description=(
            "H1–H6 headings and fence markers with 1-based line numbers,"
            ' e.g. "1: # Title\\n42: ## Usage".'
        )
    )
    total_lines: int = Field(
        description="Total number of lines in the full page. Always present regardless of view."
    )
    offset: int = Field(description="1-based line number where the content window starts.")
    limit: int = Field(description="Maximum number of lines in the content window.")
    content: str | None = Field(
        default=None,
        description="Content window lines. Present when view='full'; absent when view='outline'.",
    )
    cached: bool = Field(description="True if served from cache.")
    cached_at: datetime | None = Field(
        description="When this page was last fetched. Null for fresh network fetches."
    )
    stale: bool = Field(
        default=False,
        description="True if cache entry is expired; a background refresh is already in progress.",
    )


class SearchPageInput(BaseModel):
    url: str
    query: str
    mode: Literal["literal", "regex"] = "literal"
    case_mode: Literal["smart", "insensitive", "sensitive"] = "smart"
    whole_word: bool = False
    offset: int = 1
    max_results: int = 20

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 2048:
            raise ValueError("url must not exceed 2048 characters")
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must use http or https scheme")
        return v

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        if len(v) > 200:
            raise ValueError("query must not exceed 200 characters")
        return v

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 1:
            raise ValueError("offset must be >= 1")
        return v

    @field_validator("max_results")
    @classmethod
    def validate_max_results(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_results must be >= 1")
        return v


class LineMatchOutput(BaseModel):
    line_number: int = Field(description="1-based line number of the matching line.")
    content: str = Field(description="The full text of the matching line.")


class SearchPageOutput(BaseModel):
    url: str = Field(description="The URL that was searched.")
    query: str = Field(description="The search query as provided.")
    outline: str = Field(description="Plain-text structural outline of the full page.")
    matches: list[LineMatchOutput] = Field(
        description="Lines matching the query, in document order."
    )
    total_lines: int = Field(description="Total number of lines in the page.")
    has_more: bool = Field(description="True if more matches exist beyond the returned set.")
    next_offset: int | None = Field(
        description="Line number to pass as offset to continue paginating. Null if no more."
    )
    cached: bool = Field(description="True if served from cache.")
    cached_at: datetime | None = Field(
        description="When this page was last fetched. Null for fresh network fetches."
    )
