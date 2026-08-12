from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "ExternalTranslate"


def is_frozen() -> bool:
    """Whether this is a packaged build rather than a source checkout."""
    return bool(getattr(sys, "frozen", False))


def bundled_root() -> Path:
    """Where the read-only files that ship with the program live.

    In a source checkout that is the repository. In a PyInstaller build it is
    the directory PyInstaller unpacked the data into — `sys._MEIPASS`, which
    for a onedir build is `_internal` beside the executable. Every path derived
    from source layout would point at a machine that never had the source.
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass is not None:
            return Path(str(meipass))
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def user_data_root() -> Path:
    """Where the files the program writes live.

    A source checkout keeps using the repository's `config/`, so a developer's
    settings do not move when this is introduced. A packaged build writes to
    `%LOCALAPPDATA%\\ExternalTranslate` instead: the program directory can be
    read-only, and anything written inside it would be lost the moment that
    directory is replaced by a new version.
    """
    if not is_frozen():
        return bundled_root()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME.lower()}"


def default_settings_path() -> Path:
    """The shipped defaults; read-only, and never written back to."""
    return bundled_root() / "config" / "default.yaml"


def user_settings_path() -> Path:
    """The operator's settings — the one file worth copying between machines."""
    return user_data_root() / "config" / "user.yaml"


def preset_store_path() -> Path:
    return user_data_root() / "config" / "caption-presets.json"


def frontend_dist_path() -> Path:
    """The built control page and overlay, served by the API process."""
    return bundled_root() / "frontend" / "dist"
