from __future__ import annotations

import os
from pathlib import Path

__DEFAULT_VERSION = "2.0.0"
_VERSION_FILE = "VERSION"
_APPEND_ENV = "KEELI_VERSION_APPEND"


def _read_base_version() -> str:
    root = Path(__file__).resolve().parents[2]
    version_file = root / _VERSION_FILE
    if version_file.exists():
        raw = version_file.read_text().strip()
        if raw:
            return raw
    return _DEFAULT_VERSION


def get_version() -> str:
    """Return project version from VERSION file with optional append suffix.

    Set KEELI_VERSION_APPEND to append arbitrary increment strings, e.g.:
    - KEELI_VERSION_APPEND=.dev1 -> 2.0.0.dev1
    - KEELI_VERSION_APPEND=+build.7 -> 2.0.0+build.7
    """
    base = _read_base_version()
    append = os.getenv(_APPEND_ENV, "").strip()
    return f"{base}{append}" if append else base
