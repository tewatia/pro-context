"""Unit tests for package version resolution."""

from __future__ import annotations

import importlib.metadata
import importlib.util
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

import procontext


def test_dunder_version_matches_package_metadata_or_fallback() -> None:
    """__version__ should come from package metadata when available."""
    try:
        expected = version("procontext")
    except PackageNotFoundError:
        expected = "0.0.0+unknown"

    assert procontext.__version__ == expected


def test_missing_package_metadata_emits_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing package metadata should trigger a warning and fallback version."""

    def _raise_package_not_found(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", _raise_package_not_found)

    init_path = Path(__file__).resolve().parents[2] / "src" / "procontext" / "__init__.py"
    spec = importlib.util.spec_from_file_location("procontext_version_test", init_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    with pytest.warns(
        RuntimeWarning,
        match="Package metadata for 'procontext' not found",
    ):
        spec.loader.exec_module(module)

    assert module.__version__ == "0.0.0+unknown"
