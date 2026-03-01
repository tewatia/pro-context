"""ProContext: MCP server for accurate, up-to-date library documentation."""

from __future__ import annotations

import warnings
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("procontext")
except PackageNotFoundError:
    # Source-tree execution without installed package metadata.
    warnings.warn(
        "Package metadata for 'procontext' not found; using fallback version '0.0.0+unknown'.",
        RuntimeWarning,
        stacklevel=2,
    )
    __version__ = "0.0.0+unknown"
