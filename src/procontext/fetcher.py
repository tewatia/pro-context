"""HTTP documentation fetcher with SSRF protection.

All network I/O for fetching documentation goes through a single Fetcher
instance shared across tool calls. The Fetcher receives an httpx.AsyncClient
via constructor injection — the lifespan owns the client lifecycle.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from procontext.errors import ErrorCode, ProContextError

if TYPE_CHECKING:
    from procontext.models.registry import RegistryEntry

log = structlog.get_logger()

PRIVATE_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def build_http_client() -> httpx.AsyncClient:
    """Create the shared httpx client. Called once at startup."""
    return httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": "procontext/1.0"},
        limits=httpx.Limits(
            max_connections=10,
            max_keepalive_connections=5,
        ),
    )


def _base_domain(hostname: str) -> str:
    """Return the last two DNS labels: ``'api.langchain.com'`` → ``'langchain.com'``."""
    parts = hostname.rstrip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else hostname


def build_allowlist(entries: list[RegistryEntry]) -> frozenset[str]:
    """Build the SSRF domain allowlist from registry entries.

    Extracts base domains from all ``docs_url`` and ``llms_txt_url`` fields.
    """
    base_domains: set[str] = set()
    for entry in entries:
        for url in [entry.llms_txt_url, entry.docs_url]:
            if url:
                hostname = urlparse(url).hostname or ""
                if hostname:
                    base_domains.add(_base_domain(hostname))
    return frozenset(base_domains)


def is_url_allowed(url: str, allowlist: frozenset[str]) -> bool:
    """Check whether a URL is permitted by the SSRF allowlist.

    Private IP ranges are blocked unconditionally, regardless of allowlist.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Block private IPs unconditionally
    try:
        addr = ipaddress.ip_address(hostname)
        if any(addr in net for net in PRIVATE_NETWORKS):
            return False
    except ValueError:
        pass  # hostname is a domain name, not an IP — proceed to allowlist check

    return _base_domain(hostname) in allowlist


class Fetcher:
    """HTTP documentation fetcher with SSRF-safe redirect handling."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(
        self,
        url: str,
        allowlist: frozenset[str],
        max_redirects: int = 3,  # Implementation detail, not part of FetcherProtocol
    ) -> str:
        """Fetch a URL with per-hop SSRF validation.

        Returns the response text content on success. Raises ProContextError
        on SSRF violations, network errors, and non-2xx responses.
        """
        current_url = url

        try:
            for hop in range(max_redirects + 1):
                if not is_url_allowed(current_url, allowlist):
                    log.warning("ssrf_blocked", url=current_url, reason="not_in_allowlist")
                    raise ProContextError(
                        code=ErrorCode.URL_NOT_ALLOWED,
                        message=f"URL not in allowlist: {current_url}",
                        suggestion="Only URLs from known documentation domains are permitted.",
                        recoverable=False,
                    )

                response = await self._client.get(current_url)

                if response.is_redirect and "location" in response.headers:
                    if hop == max_redirects:
                        raise ProContextError(
                            code=ErrorCode.PAGE_FETCH_FAILED,
                            message=f"Too many redirects fetching {url}",
                            suggestion=(
                                "The documentation URL has an unusually long redirect chain."
                            ),
                            recoverable=False,
                        )
                    location = response.headers["location"]
                    current_url = urljoin(current_url, location)
                    continue

                if not response.is_success:
                    if response.status_code == 404:
                        raise ProContextError(
                            code=ErrorCode.PAGE_NOT_FOUND,
                            message=f"HTTP 404 fetching {url}",
                            suggestion=(
                                "The requested documentation page does not exist at this URL."
                            ),
                            recoverable=False,
                        )
                    raise ProContextError(
                        code=ErrorCode.PAGE_FETCH_FAILED,
                        message=f"HTTP {response.status_code} fetching {url}",
                        suggestion="The documentation source may be temporarily unavailable.",
                        recoverable=True,
                    )

                log.info(
                    "fetch_complete",
                    url=url,
                    status_code=response.status_code,
                    content_length=len(response.text),
                )
                return response.text

        except ProContextError:
            raise
        except httpx.HTTPError as exc:
            raise ProContextError(
                code=ErrorCode.PAGE_FETCH_FAILED,
                message=f"Network error fetching {url}: {exc}",
                suggestion="The documentation source may be temporarily unavailable.",
                recoverable=True,
            ) from exc

        # Unreachable but satisfies the type checker
        raise ProContextError(
            code=ErrorCode.PAGE_FETCH_FAILED,
            message="Redirect loop",
            suggestion="",
            recoverable=False,
        )
