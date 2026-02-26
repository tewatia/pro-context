"""Unit tests for procontext.fetcher."""

from __future__ import annotations

import httpx
import pytest
import respx

from procontext.errors import ErrorCode, ProContextError
from procontext.fetcher import (
    Fetcher,
    _base_domain,
    build_allowlist,
    build_http_client,
    is_url_allowed,
)
from procontext.models.registry import RegistryEntry

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

    async def test_redirect_to_disallowed_domain(self) -> None:
        with respx.mock:
            respx.get("https://example.com/redirect").mock(
                return_value=httpx.Response(301, headers={"location": "https://evil.com/steal"})
            )
            async with httpx.AsyncClient() as client:
                fetcher = Fetcher(client)
                with pytest.raises(ProContextError) as exc_info:
                    await fetcher.fetch("https://example.com/redirect", ALLOWLIST)
                assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED

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
                assert exc_info.value.code == ErrorCode.PAGE_FETCH_FAILED

    async def test_url_not_in_allowlist(self) -> None:
        async with httpx.AsyncClient() as client:
            fetcher = Fetcher(client)
            with pytest.raises(ProContextError) as exc_info:
                await fetcher.fetch("https://unknown.org/path", ALLOWLIST)
            assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED

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
