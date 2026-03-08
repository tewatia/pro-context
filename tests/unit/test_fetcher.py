"""Unit tests for procontext.fetcher."""

from __future__ import annotations

import httpx
import pytest
import respx

from procontext.config import FetcherSettings, Settings
from procontext.errors import ErrorCode, ProContextError
from procontext.fetcher import (
    Fetcher,
    _base_domain,
    build_allowlist,
    build_http_client,
    expand_allowlist_from_content,
    extract_base_domains_from_content,
    is_url_allowed,
)
from procontext.models.registry import RegistryEntry, RegistryIndexes
from procontext.state import AppState

# ---------------------------------------------------------------------------
# _base_domain
# ---------------------------------------------------------------------------


class TestBaseDomain:
    def test_three_labels(self) -> None:
        assert _base_domain("api.langchain.com") == "langchain.com"

    def test_two_labels(self) -> None:
        assert _base_domain("langchain.com") == "langchain.com"

    def test_single_label(self) -> None:
        assert _base_domain("localhost") == "localhost"

    def test_trailing_dot(self) -> None:
        assert _base_domain("api.langchain.com.") == "langchain.com"

    def test_four_labels(self) -> None:
        assert _base_domain("a.b.langchain.com") == "langchain.com"


# ---------------------------------------------------------------------------
# build_allowlist
# ---------------------------------------------------------------------------


class TestBuildAllowlist:
    def test_extracts_base_domains(self, sample_entries: list[RegistryEntry]) -> None:
        allowlist = build_allowlist(sample_entries)
        assert "langchain.com" in allowlist
        assert "pydantic.dev" in allowlist

    def test_deduplicates(self) -> None:
        entries = [
            RegistryEntry(
                id="lib1",
                name="Lib1",
                docs_url="https://docs.example.com",
                llms_txt_url="https://api.example.com/llms.txt",
                languages=["python"],
            ),
        ]
        allowlist = build_allowlist(entries)
        # Both URLs have base domain "example.com"
        assert allowlist == frozenset({"example.com"})

    def test_skips_none_docs_url(self) -> None:
        entries = [
            RegistryEntry(
                id="lib1",
                name="Lib1",
                docs_url=None,
                llms_txt_url="https://example.com/llms.txt",
                languages=["python"],
            ),
        ]
        allowlist = build_allowlist(entries)
        assert "example.com" in allowlist

    def test_extra_domains_merged(self, sample_entries: list[RegistryEntry]) -> None:
        allowlist = build_allowlist(
            sample_entries, extra_domains=["github.com", "githubusercontent.com"]
        )
        assert "github.com" in allowlist
        assert "githubusercontent.com" in allowlist

    def test_extra_domains_base_domain_normalised(
        self, sample_entries: list[RegistryEntry]
    ) -> None:
        # subdomain in extra_domains should be reduced to base domain
        allowlist = build_allowlist(sample_entries, extra_domains=["raw.githubusercontent.com"])
        assert "githubusercontent.com" in allowlist

    def test_extra_domains_none_is_noop(self, sample_entries: list[RegistryEntry]) -> None:
        without = build_allowlist(sample_entries)
        with_none = build_allowlist(sample_entries, extra_domains=None)
        assert without == with_none


# ---------------------------------------------------------------------------
# is_url_allowed
# ---------------------------------------------------------------------------


class TestIsUrlAllowed:
    def test_allowed_domain(self) -> None:
        assert is_url_allowed("https://python.langchain.com/llms.txt", frozenset({"langchain.com"}))

    def test_subdomain_allowed(self) -> None:
        assert is_url_allowed("https://api.docs.langchain.com/path", frozenset({"langchain.com"}))

    def test_disallowed_domain(self) -> None:
        assert not is_url_allowed("https://evil.com/path", frozenset({"langchain.com"}))

    def test_private_ipv4_10(self) -> None:
        assert not is_url_allowed("http://10.0.0.1/secret", frozenset({"10.0.0.1"}))

    def test_private_ipv4_172(self) -> None:
        assert not is_url_allowed("http://172.16.0.1/secret", frozenset({"172.16.0.1"}))

    def test_private_ipv4_192(self) -> None:
        assert not is_url_allowed("http://192.168.1.1/secret", frozenset({"192.168.1.1"}))

    def test_private_ipv4_127(self) -> None:
        assert not is_url_allowed("http://127.0.0.1/secret", frozenset({"127.0.0.1"}))

    def test_private_ipv6_loopback(self) -> None:
        assert not is_url_allowed("http://[::1]/secret", frozenset({"::1"}))

    def test_private_ipv6_fc00(self) -> None:
        assert not is_url_allowed("http://[fc00::1]/secret", frozenset({"fc00::1"}))

    def test_empty_allowlist(self) -> None:
        assert not is_url_allowed("https://example.com", frozenset())

    def test_check_domain_false_bypasses_allowlist(self) -> None:
        # Any public domain allowed when check_domain=False
        assert is_url_allowed("https://unknown.org/path", frozenset(), check_domain=False)

    def test_check_domain_false_still_blocks_private_ip(self) -> None:
        # Private IPs remain blocked even with check_domain=False
        assert not is_url_allowed("http://192.168.1.1/path", frozenset(), check_domain=False)

    def test_check_private_ips_false_allows_internal_hostname(self) -> None:
        # Simulates an internal hostname (e.g. docs.internal.corp.com) that resolves to a
        # private IP. With check_private_ips=False the domain allowlist is the only gate.
        assert is_url_allowed(
            "https://docs.internal.corp.com/guide",
            frozenset({"corp.com"}),
            check_private_ips=False,
        )

    def test_both_checks_false_allows_anything(self) -> None:
        assert is_url_allowed(
            "http://10.0.0.1/internal",
            frozenset(),
            check_private_ips=False,
            check_domain=False,
        )

    def test_url_with_no_hostname_blocked(self) -> None:
        # urlparse("https://").hostname is None → falls back to "" → not in allowlist
        assert not is_url_allowed("https://", frozenset({"example.com"}))

    def test_url_with_empty_scheme_blocked(self) -> None:
        assert not is_url_allowed("://example.com/path", frozenset({"example.com"}))


# ---------------------------------------------------------------------------
# extract_base_domains_from_content
# ---------------------------------------------------------------------------


class TestExtractBaseDomainsFromContent:
    def test_extracts_inline_link(self) -> None:
        content = "See [guide](https://docs.example.com/guide) for details."
        assert "example.com" in extract_base_domains_from_content(content)

    def test_extracts_bare_url(self) -> None:
        content = "Visit https://api.example.com/reference for the API."
        assert "example.com" in extract_base_domains_from_content(content)

    def test_multiple_domains(self) -> None:
        content = "https://docs.foo.com/page\nhttps://bar.io/guide"
        result = extract_base_domains_from_content(content)
        assert "foo.com" in result
        assert "bar.io" in result

    def test_deduplicates(self) -> None:
        content = "https://docs.example.com/a https://api.example.com/b"
        result = extract_base_domains_from_content(content)
        assert result == frozenset({"example.com"})

    def test_empty_content(self) -> None:
        assert extract_base_domains_from_content("") == frozenset()

    def test_no_urls(self) -> None:
        assert extract_base_domains_from_content("No links here.") == frozenset()

    def test_ignores_non_http(self) -> None:
        content = "ftp://files.example.com/archive"
        assert extract_base_domains_from_content(content) == frozenset()


# ---------------------------------------------------------------------------
# build_http_client
# ---------------------------------------------------------------------------


class TestBuildHttpClient:
    def test_client_configuration(self) -> None:
        client = build_http_client()
        assert isinstance(client, httpx.AsyncClient)
        # follow_redirects is False (we handle redirects manually)
        assert client.follow_redirects is False


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------

ALLOWLIST = frozenset({"example.com", "docs.dev"})


class TestFetcher:
    async def test_successful_fetch(self) -> None:
        with respx.mock:
            respx.get("https://example.com/llms.txt").mock(
                return_value=httpx.Response(200, text="# Docs\nHello world")
            )
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                result = await fetcher.fetch("https://example.com/llms.txt", ALLOWLIST)
                assert result == "# Docs\nHello world"

    async def test_404_raises_error(self) -> None:
        with respx.mock:
            respx.get("https://example.com/missing").mock(return_value=httpx.Response(404))
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                with pytest.raises(ProContextError) as exc_info:
                    await fetcher.fetch("https://example.com/missing", ALLOWLIST)
                assert exc_info.value.code == ErrorCode.PAGE_NOT_FOUND
                assert exc_info.value.recoverable is False

    async def test_500_raises_error(self) -> None:
        with respx.mock:
            respx.get("https://example.com/error").mock(return_value=httpx.Response(500))
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                with pytest.raises(ProContextError) as exc_info:
                    await fetcher.fetch("https://example.com/error", ALLOWLIST)
                assert exc_info.value.code == ErrorCode.PAGE_FETCH_FAILED
                assert exc_info.value.recoverable is True

    async def test_network_error_raises_error(self) -> None:
        with respx.mock:
            respx.get("https://example.com/timeout").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                with pytest.raises(ProContextError) as exc_info:
                    await fetcher.fetch("https://example.com/timeout", ALLOWLIST)
                assert exc_info.value.code == ErrorCode.PAGE_FETCH_FAILED
                assert exc_info.value.recoverable is True

    async def test_redirect_followed(self) -> None:
        with respx.mock:
            respx.get("https://example.com/old").mock(
                return_value=httpx.Response(301, headers={"location": "https://example.com/new"})
            )
            respx.get("https://example.com/new").mock(
                return_value=httpx.Response(200, text="Redirected content")
            )
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                result = await fetcher.fetch("https://example.com/old", ALLOWLIST)
                assert result == "Redirected content"

    async def test_redirect_to_different_domain_is_followed(self) -> None:
        # Domain check is skipped on redirect hops — the originating domain was
        # already vetted. Private IP check still applies (see test below).
        with respx.mock:
            respx.get("https://example.com/redirect").mock(
                return_value=httpx.Response(
                    301, headers={"location": "https://otherdomain.com/page"}
                )
            )
            respx.get("https://otherdomain.com/page").mock(
                return_value=httpx.Response(200, text="Redirected content")
            )
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                result = await fetcher.fetch("https://example.com/redirect", ALLOWLIST)
                assert result == "Redirected content"

    async def test_redirect_to_private_ip(self) -> None:
        with respx.mock:
            respx.get("https://example.com/redirect").mock(
                return_value=httpx.Response(301, headers={"location": "http://127.0.0.1/internal"})
            )
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                with pytest.raises(ProContextError) as exc_info:
                    await fetcher.fetch("https://example.com/redirect", ALLOWLIST)
                assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED

    async def test_too_many_redirects(self) -> None:
        with respx.mock:
            # 4 redirects (max is 3)
            for i in range(4):
                respx.get(f"https://example.com/r{i}").mock(
                    return_value=httpx.Response(
                        301, headers={"location": f"https://example.com/r{i + 1}"}
                    )
                )
            respx.get("https://example.com/r4").mock(return_value=httpx.Response(200, text="Final"))
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                with pytest.raises(ProContextError) as exc_info:
                    await fetcher.fetch("https://example.com/r0", ALLOWLIST)
                assert exc_info.value.code == ErrorCode.TOO_MANY_REDIRECTS
                assert exc_info.value.recoverable is False

    async def test_url_not_in_allowlist(self) -> None:
        async with httpx.AsyncClient() as client:
            fetcher = Fetcher(client)
            with pytest.raises(ProContextError) as exc_info:
                await fetcher.fetch("https://unknown.org/path", ALLOWLIST)
            assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED

    async def test_ssrf_domain_check_false_bypasses_allowlist(self) -> None:
        settings = FetcherSettings(ssrf_domain_check=False)
        with respx.mock:
            respx.get("https://unknown.org/path").mock(
                return_value=httpx.Response(200, text="content")
            )
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client, settings)
                result = await fetcher.fetch("https://unknown.org/path", frozenset())
                assert result == "content"

    async def test_ssrf_domain_check_false_still_blocks_private_ip(self) -> None:
        settings = FetcherSettings(ssrf_domain_check=False)
        async with httpx.AsyncClient() as client:
            fetcher = Fetcher(client, settings)
            with pytest.raises(ProContextError) as exc_info:
                await fetcher.fetch("http://192.168.1.1/secret", frozenset())
            assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED

    async def test_redirect_without_location_header(self) -> None:
        # 3xx without Location: is_redirect is False in httpx (requires Location header),
        # so the response falls through to is_success check → PAGE_FETCH_FAILED.
        with respx.mock:
            respx.get("https://example.com/broken-redirect").mock(
                return_value=httpx.Response(301, headers={})
            )
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                with pytest.raises(ProContextError) as exc_info:
                    await fetcher.fetch("https://example.com/broken-redirect", ALLOWLIST)
                assert exc_info.value.code == ErrorCode.PAGE_FETCH_FAILED

    async def test_relative_redirect_resolved(self) -> None:
        with respx.mock:
            respx.get("https://example.com/old").mock(
                return_value=httpx.Response(301, headers={"location": "/new-path"})
            )
            respx.get("https://example.com/new-path").mock(
                return_value=httpx.Response(200, text="Relative redirect content")
            )
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                result = await fetcher.fetch("https://example.com/old", ALLOWLIST)
                assert result == "Relative redirect content"


# ---------------------------------------------------------------------------
# expand_allowlist_from_content
# ---------------------------------------------------------------------------


def _make_state_with_allowlist(allowlist_expansion: str, allowlist: frozenset[str]) -> AppState:
    settings = Settings(fetcher={"allowlist_expansion": allowlist_expansion})
    return AppState(
        settings=settings,
        indexes=RegistryIndexes(),
        allowlist=allowlist,
    )


class TestExpandAllowlistFromContent:
    def test_expands_allowlist_when_discovered(self) -> None:
        """New domains are added to state.allowlist when expansion is 'discovered'."""
        state = _make_state_with_allowlist(
            allowlist_expansion="discovered", allowlist=frozenset({"example.com"})
        )
        content = "See https://newdocs.io/guide for details."

        discovered = expand_allowlist_from_content(content, state)

        assert "newdocs.io" in discovered
        assert "newdocs.io" in state.allowlist  # live allowlist was expanded

    def test_returns_domains_but_does_not_expand_when_registry(self) -> None:
        """With expansion='registry', discovered domains are returned but allowlist is unchanged."""
        state = _make_state_with_allowlist(
            allowlist_expansion="registry", allowlist=frozenset({"example.com"})
        )
        original_allowlist = state.allowlist
        content = "See https://newdocs.io/guide for details."

        discovered = expand_allowlist_from_content(content, state)

        assert "newdocs.io" in discovered  # still returned for cache persistence
        assert state.allowlist == original_allowlist  # allowlist is NOT mutated

    def test_no_mutation_when_domain_already_in_allowlist(self) -> None:
        """Domains already in the allowlist leave state.allowlist unchanged."""
        initial = frozenset({"example.com"})
        state = _make_state_with_allowlist(allowlist_expansion="discovered", allowlist=initial)
        content = "See https://example.com/guide for details."

        discovered = expand_allowlist_from_content(content, state)

        assert "example.com" in discovered
        assert state.allowlist is initial  # same object — no new frozenset was created
