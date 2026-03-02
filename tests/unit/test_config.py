"""Unit tests for platform-aware configuration defaults."""

from __future__ import annotations

import platformdirs
import pytest
from pydantic import ValidationError

from procontext.config import _DEFAULT_DATA_DIR, _DEFAULT_DB_PATH, CacheSettings, Settings


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

    def test_data_dir_override_does_not_change_default_db_path(self) -> None:
        settings = Settings(data_dir="/tmp/custom-procontext-data")
        assert settings.data_dir == "/tmp/custom-procontext-data"
        assert settings.cache.db_path == _DEFAULT_DB_PATH


class TestConfigValidation:
    """Verify config validation behaviour — including known gaps."""

    def test_wrong_type_raises_validation_error(self) -> None:
        """A non-integer port raises ValidationError immediately."""
        with pytest.raises(ValidationError):
            # type: ignore comment is intentional — we are deliberately passing
            # a wrong type to verify that Pydantic catches and rejects it.
            Settings(server={"port": "not-a-number"})  # type: ignore[arg-type]

    def test_unknown_top_level_field_raises_validation_error(self) -> None:
        """pydantic-settings already raises for unknown top-level fields.

        A YAML typo at the top level (e.g. 'cach:' instead of 'cache:') is caught.
        """
        with pytest.raises(ValidationError):
            Settings(completely_unknown_field="oops")  # type: ignore[call-arg]

    def test_unknown_nested_field_raises_validation_error(self) -> None:
        """Unknown nested model fields raise ValidationError (extra='forbid').

        A typo like 'db_paht' instead of 'db_path' is caught immediately rather
        than silently falling back to the platform default.
        """
        with pytest.raises(ValidationError):
            CacheSettings(db_paht="/intended/path/cache.db")  # type: ignore[call-arg]

    def test_negative_ttl_hours_accepted_but_causes_immediate_expiry(self) -> None:
        """Pydantic does not reject negative ttl_hours — document the consequence.

        A negative TTL means expires_at is set in the past on every write, so
        every cache read returns stale=True immediately. No crash, but silent
        misconfiguration. Operators must be warned via docs.
        """
        from datetime import UTC, datetime, timedelta

        from procontext.config import CacheSettings

        settings = CacheSettings(ttl_hours=-1)
        assert settings.ttl_hours == -1
        # Demonstrate: timedelta(hours=-1) puts expires_at in the past
        expires_at = datetime.now(UTC) + timedelta(hours=settings.ttl_hours)
        assert expires_at < datetime.now(UTC)

    def test_empty_auth_key_with_auth_enabled(self) -> None:
        """auth_key='' with auth_enabled=True is accepted by pydantic.

        The security implication: the middleware will only admit a request whose
        Authorization header is exactly 'Bearer ' (empty token). Document this
        so it is a conscious choice, not an oversight.
        """
        from procontext.config import ServerSettings

        settings = ServerSettings(auth_enabled=True, auth_key="")
        assert settings.auth_enabled is True
        assert settings.auth_key == ""
