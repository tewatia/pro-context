"""Integration tests for CLI commands (subprocess-based).

Tests run the CLI as a subprocess to verify end-to-end behavior including
argument parsing, exit codes, and output.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _run_cli(
    args: list[str], env: dict[str, str], timeout: int = 10
) -> subprocess.CompletedProcess[str]:
    """Run the CLI with the given subcommand args."""
    return subprocess.run(
        [sys.executable, "-m", "procontext.cli.main", *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


class TestHelpOutput:
    """--help exits 0 for all subcommands."""

    def test_main_help(self, subprocess_env: dict[str, str]) -> None:
        result = _run_cli(["--help"], subprocess_env)
        assert result.returncode == 0
        assert "setup" in result.stdout
        assert "doctor" in result.stdout

    def test_setup_help(self, subprocess_env: dict[str, str]) -> None:
        result = _run_cli(["setup", "--help"], subprocess_env)
        assert result.returncode == 0

    def test_doctor_help(self, subprocess_env: dict[str, str]) -> None:
        result = _run_cli(["doctor", "--help"], subprocess_env)
        assert result.returncode == 0

    def test_db_help(self, subprocess_env: dict[str, str]) -> None:
        result = _run_cli(["db", "--help"], subprocess_env)
        assert result.returncode == 0


class TestDoctorCommand:
    """End-to-end doctor command tests."""

    def test_doctor_passes_local_checks(self, subprocess_env: dict[str, str]) -> None:
        """Data directory, Registry, and Cache checks pass when registry is seeded.

        Network check is expected to fail (subprocess_env points to a
        non-routable URL), so we verify individual check results rather
        than the exit code.
        """
        result = _run_cli(["doctor"], subprocess_env)
        lines = result.stdout.splitlines()
        data_line = next(line for line in lines if "Data directory" in line)
        registry_line = next(line for line in lines if "Registry" in line)
        assert "ok" in data_line
        assert "ok" in registry_line

    def test_doctor_without_registry_exits_1(
        self, tmp_path: Path, subprocess_env: dict[str, str]
    ) -> None:
        """Doctor fails when no registry is present."""
        empty_data = tmp_path / "empty_data"
        empty_data.mkdir()
        env = {**subprocess_env, "PROCONTEXT__DATA_DIR": str(empty_data)}
        result = _run_cli(["doctor"], env)
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_doctor_fix_flag_accepted(self, subprocess_env: dict[str, str]) -> None:
        """--fix flag is parsed without error."""
        result = _run_cli(["doctor", "--fix"], subprocess_env)
        assert "ProContext Doctor (--fix)" in result.stdout

    def test_doctor_fix_suggests_db_recreate_for_corrupt_cache(
        self, tmp_path: Path, subprocess_env: dict[str, str]
    ) -> None:
        """--fix does not destroy unreadable DBs; it suggests the recreate command."""
        cache_path = tmp_path / "corrupt_cache.db"
        cache_path.write_text("not a database")
        env = {**subprocess_env, "PROCONTEXT__CACHE__DB_PATH": str(cache_path)}
        result = _run_cli(["doctor", "--fix"], env)
        assert result.returncode == 1
        assert "Cache" in result.stdout
        assert "FAIL" in result.stdout
        assert "procontext db recreate" in result.stdout

    def test_db_recreate_replaces_corrupt_cache(
        self, tmp_path: Path, subprocess_env: dict[str, str]
    ) -> None:
        """The dedicated recreate command replaces the cache DB with a fresh schema."""
        cache_path = tmp_path / "corrupt_cache.db"
        cache_path.write_text("not a database")
        env = {**subprocess_env, "PROCONTEXT__CACHE__DB_PATH": str(cache_path)}

        recreate = _run_cli(["db", "recreate"], env)
        assert recreate.returncode == 0
        assert "Recreated cache database" in recreate.stdout

        doctor = _run_cli(["doctor"], env)
        lines = doctor.stdout.splitlines()
        cache_line = next(line for line in lines if "Cache" in line)
        assert "ok" in cache_line


class TestSetupCommand:
    def test_setup_failure_suggests_doctor(
        self, tmp_path: Path, subprocess_env: dict[str, str]
    ) -> None:
        env = {
            **subprocess_env,
            "PROCONTEXT__DATA_DIR": str(tmp_path),
            "PROCONTEXT__CACHE__DB_PATH": str(tmp_path / "cache.db"),
            "PROCONTEXT__REGISTRY__METADATA_URL": "http://127.0.0.1:1/registry_metadata.json",
        }

        result = _run_cli(["setup"], env)
        assert result.returncode == 1
        assert "procontext doctor --fix" in result.stderr


class TestLegacyEntrypoint:
    """The old mcp.startup module still works as a shim."""

    def test_legacy_module_help(self, subprocess_env: dict[str, str]) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "procontext.mcp.startup", "--help"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            env=subprocess_env,
        )
        assert result.returncode == 0
        assert "setup" in result.stdout
