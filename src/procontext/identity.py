"""Anonymous client identity.

Generates a random UUID on first call and persists it to ``data_dir/client_id``.
Subsequent calls return the stored value.  The ID is never derived from hardware
so there are no platform-specific code paths and no PII concerns.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import platformdirs
import structlog

log = structlog.get_logger()

_DEFAULT_DATA_DIR = platformdirs.user_data_dir("procontext")


def get_client_id(data_dir: str | Path = _DEFAULT_DATA_DIR) -> str:
    """Return a stable anonymous client ID, creating one if it doesn't exist."""
    path = Path(data_dir) / "client_id"
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        client_id = str(uuid.uuid4())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(client_id)
        log.info("client_id_created", path=str(path))
        return client_id
