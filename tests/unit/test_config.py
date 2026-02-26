"""Unit tests for platform-aware configuration defaults."""

from __future__ import annotations

import platformdirs

from procontext.config import _DEFAULT_DATA_DIR, _DEFAULT_DB_PATH, CacheSettings


class TestPlatformDefaults:
    """Verify config defaults use platformdirs instead of hardcoded Unix paths."""

    def test_default_data_dir_matches_platformdirs(self) -> None:
        expected = platformdirs.user_data_dir("procontext")
        assert expected == _DEFAULT_DATA_DIR

    def test_default_db_path_under_data_dir(self) -> None:
        assert _DEFAULT_DB_PATH.startswith(_DEFAULT_DATA_DIR)
        assert _DEFAULT_DB_PATH.endswith("cache.db")

    def test_cache_settings_uses_platform_default(self) -> None:
        settings = CacheSettings()
        assert settings.db_path == _DEFAULT_DB_PATH
        # Ensure it's not the old hardcoded Unix path
        assert settings.db_path != "~/.local/share/procontext/cache.db"
