"""Tests for anonymous client identity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from procontext.identity import get_client_id

if TYPE_CHECKING:
    from pathlib import Path


class TestGetClientId:
    def test_creates_id_on_first_call(self, tmp_path: Path) -> None:
        client_id = get_client_id(tmp_path)
        assert len(client_id) == 36  # UUID4 format: 8-4-4-4-12
        assert (tmp_path / "client_id").exists()
        assert (tmp_path / "client_id").read_text() == client_id

    def test_returns_same_id_on_subsequent_calls(self, tmp_path: Path) -> None:
        first = get_client_id(tmp_path)
        second = get_client_id(tmp_path)
        assert first == second

    def test_reads_existing_id_from_disk(self, tmp_path: Path) -> None:
        (tmp_path / "client_id").write_text("custom-test-id")
        assert get_client_id(tmp_path) == "custom-test-id"

    def test_strips_whitespace_from_stored_id(self, tmp_path: Path) -> None:
        (tmp_path / "client_id").write_text("  some-id\n")
        assert get_client_id(tmp_path) == "some-id"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        client_id = get_client_id(nested)
        assert len(client_id) == 36
        assert (nested / "client_id").exists()
