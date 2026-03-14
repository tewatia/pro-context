"""Tests for server startup error scenarios.

Covers:
- Wrong-type config values (both stdio and HTTP transports)
- Non-existent db_path parent directories (auto-created)
- Unwriteable db_path parent directory (server crash)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _run_and_wait(env: dict[str, str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    """Start the server with stdin closed and wait for it to exit.

    Suitable for crash scenarios where the server exits before reading any input.
    """
    return subprocess.run(
        [sys.executable, "-m", "procontext.cli.main"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


class TestBadConfigType:
    """Wrong-type config values crash the server before any transport starts."""

    def test_stdio_crashes_on_wrong_type(self, subprocess_env: dict[str, str]) -> None:
        """A non-integer port value causes a non-zero exit in stdio mode."""
        env = {**subprocess_env, "PROCONTEXT__SERVER__PORT": "not-a-number"}
        result = _run_and_wait(env)
        assert result.returncode != 0

    def test_http_crashes_on_wrong_type(self, subprocess_env: dict[str, str]) -> None:
        """Config validation runs before transport starts, so HTTP fails identically."""
        env = {
            **subprocess_env,
            "PROCONTEXT__SERVER__TRANSPORT": "http",
            "PROCONTEXT__SERVER__PORT": "not-a-number",
        }
        result = _run_and_wait(env)
        assert result.returncode != 0


class TestDbPathStartup:
    """db_path handling during server startup."""

    def test_missing_parent_dirs_are_auto_created(
        self, tmp_path: Path, subprocess_env: dict[str, str]
    ) -> None:
        """A db_path with non-existent parent dirs is created automatically.

        The server starts normally — missing directories are not a fatal error.
        """
        deep_path = tmp_path / "a" / "b" / "c" / "cache.db"
        assert not deep_path.parent.exists()

        env = {**subprocess_env, "PROCONTEXT__CACHE__DB_PATH": str(deep_path)}

        proc = subprocess.Popen(
            [sys.executable, "-m", "procontext.cli.main"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        assert proc.stderr is not None

        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                }
            )
            + "\n"
        )
        proc.stdin.flush()

        line = proc.stdout.readline()
        response = json.loads(line.strip())

        try:
            proc.stdin.write(
                json.dumps({"jsonrpc": "2.0", "id": 9999, "method": "shutdown"}) + "\n"
            )
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "exit"}) + "\n")
        except OSError:
            pass
        proc.stdin.close()
        proc.stderr.read()
        proc.wait(timeout=10)
        proc.stdout.close()
        proc.stderr.close()

        assert response.get("id") == 1
        assert "result" in response
        assert deep_path.parent.exists()

    @pytest.mark.skipif(
        os.name == "nt" or (hasattr(os, "getuid") and os.getuid() == 0),
        reason="Permission checks don't apply on Windows or when running as root.",
    )
    def test_unwriteable_db_path_crashes_server(
        self, tmp_path: Path, subprocess_env: dict[str, str]
    ) -> None:
        """A db parent dir with no write permission causes a non-zero exit.

        mkdir succeeds (the directory already exists with exist_ok=True), but
        SQLite cannot create the database file inside a read-only directory.
        The resulting OperationalError is currently unhandled — raw traceback.
        """
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        readonly.chmod(0o555)  # read+execute only: can list/enter, cannot create files

        try:
            env = {**subprocess_env, "PROCONTEXT__CACHE__DB_PATH": str(readonly / "cache.db")}
            result = _run_and_wait(env)
            assert result.returncode != 0
        finally:
            readonly.chmod(0o755)  # restore so pytest can clean up tmp_path
