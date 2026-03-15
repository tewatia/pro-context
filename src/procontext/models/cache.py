from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PageCacheEntry(BaseModel):
    """Cached content for a single documentation page."""

    url: str
    url_hash: str  # SHA-256 of url (primary key)
    content: str  # Full page markdown
    outline: str  # Plain-text outline: "<line>:<original line>\n..."
    discovered_domains: frozenset[str] = frozenset()  # Base domains found in content
    fetched_at: datetime
    expires_at: datetime
    last_checked_at: datetime | None = None  # Last time a background refresh was attempted
    stale: bool = False
