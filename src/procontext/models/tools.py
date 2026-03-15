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
    content: str = Field(description="Content window lines.")
    outline: str = Field(
        description=(
            "Compacted structural outline (target ≤50 entries). "
            "Each entry formatted as '<line_number>:<original line>'."
        )
    )
    total_lines: int = Field(description="Total number of lines in the full page.")
    offset: int = Field(description="1-based line number where the content window starts.")
    limit: int = Field(description="Maximum number of lines in the content window.")
    has_more: bool = Field(description="True if more content exists beyond the current window.")
    next_offset: int | None = Field(
        description="Line number to pass as offset to continue reading. Null if no more content."
    )
    content_hash: str = Field(
        description=(
            "Truncated SHA-256 of the page content (12 hex chars). "
            "Compare across paginated calls to detect if the underlying page changed."
        )
    )
    cached: bool = Field(description="True if served from cache.")
    cached_at: datetime | None = Field(
        description="When this page was last fetched. Null for fresh network fetches."
    )
    stale: bool = Field(
        default=False,
        description=(
            "True if the cache entry has expired. A background refresh has been"
            " triggered. Content is stale but usable."
        ),
    )


class ReadOutlineInput(BaseModel):
    url: str
    offset: int = 1
    limit: int = 1000

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


class ReadOutlineOutput(BaseModel):
    url: str = Field(description="The URL of the fetched page.")
    outline: str = Field(
        description="Paginated outline entries in '<line_number>:<original line>' format."
    )
    total_entries: int = Field(description="Total outline entries after stripping empty fences.")
    has_more: bool = Field(description="True if more entries exist beyond the current window.")
    next_offset: int | None = Field(
        description="Entry index to pass as offset to continue. Null if no more entries."
    )
    content_hash: str = Field(
        description=(
            "Truncated SHA-256 of the page content (12 hex chars). "
            "Compare across paginated calls to detect if the underlying page changed."
        )
    )
    cached: bool = Field(description="True if served from cache.")
    cached_at: datetime | None = Field(
        description="When this page was last fetched. Null for fresh network fetches."
    )
    stale: bool = Field(
        default=False,
        description=(
            "True if the cache entry has expired. A background refresh has been"
            " triggered. Content is stale but usable."
        ),
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


class SearchPageOutput(BaseModel):
    url: str = Field(description="The URL that was searched.")
    query: str = Field(description="The search query as provided.")
    matches: str = Field(
        description=(
            "Matching lines formatted as '<line_number>:<content>', one per line. "
            "Empty string when no matches found."
        )
    )
    outline: str = Field(
        description=(
            "Compacted outline trimmed to match range. Empty string when no matches found."
        )
    )
    total_lines: int = Field(description="Total number of lines in the page.")
    has_more: bool = Field(description="True if more matches exist beyond the returned set.")
    next_offset: int | None = Field(
        description="Line number to pass as offset to continue paginating. Null if no more."
    )
    content_hash: str = Field(
        description=(
            "Truncated SHA-256 of the page content (12 hex chars). "
            "Compare across calls to detect if the underlying page changed."
        )
    )
    cached: bool = Field(description="True if served from cache.")
    cached_at: datetime | None = Field(
        description="When this page was last fetched. Null for fresh network fetches."
    )
