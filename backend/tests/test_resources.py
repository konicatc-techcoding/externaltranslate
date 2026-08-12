from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from backend.app import resources


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Pretend to be a PyInstaller onedir build unpacked at `tmp_path`."""
    bundle = tmp_path / "app" / "_internal"
    bundle.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))
    return bundle


def test_a_source_checkout_uses_the_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    root = resources.bundled_root()

    # Running from source must keep reading and writing the repository's
    # config/, or a developer's settings would silently move on them.
    assert (root / "config" / "default.yaml").is_file()
    assert resources.user_data_root() == root
    assert resources.user_settings_path() == root / "config" / "user.yaml"


def test_a_frozen_build_reads_what_shipped_beside_it(frozen: Path) -> None:
    assert resources.bundled_root() == frozen
    assert resources.default_settings_path() == frozen / "config" / "default.yaml"
    assert resources.frontend_dist_path() == frozen / "frontend" / "dist"


def test_a_frozen_build_writes_under_localappdata(
    frozen: Path, tmp_path: Path
) -> None:
    # The program directory may be read-only — Program Files is — and settings
    # must survive replacing that directory with a new version.
    expected = tmp_path / "AppData" / "ExternalTranslate"

    assert resources.user_data_root() == expected
    assert resources.user_settings_path() == expected / "config" / "user.yaml"
    assert (
        resources.preset_store_path()
        == expected / "config" / "caption-presets.json"
    )


def test_writable_paths_never_land_inside_the_bundle(frozen: Path) -> None:
    # Writing into the bundle would be lost on every upgrade, and on a
    # read-only install it would fail outright.
    for path in (resources.user_settings_path(), resources.preset_store_path()):
        assert frozen not in path.parents


def test_a_frozen_build_without_localappdata_still_has_somewhere_to_write(
    frozen: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    root = resources.user_data_root()

    assert root.is_absolute()
    assert frozen not in root.parents


def test_the_bundle_root_falls_back_to_the_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # `_MEIPASS` is set by PyInstaller; if a future build stops setting it the
    # answer must still be the directory the program was started from, not the
    # source tree that no longer exists on that machine.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    executable = tmp_path / "app" / "ExternalTranslate.exe"
    executable.parent.mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert resources.bundled_root() == executable.parent


def test_the_helpers_are_the_only_place_that_knows(monkeypatch: Any) -> None:
    # Guards the reason this module exists: four call sites used to compute
    # `Path(__file__).parents[3]` for themselves, and every one of them would
    # point outside a frozen build.
    import backend.app.api.static as static_module
    import backend.app.cli.serve as serve_module

    assert "parents[3]" not in Path(static_module.__file__).read_text(
        encoding="utf-8"
    )
    assert "parents[3]" not in Path(serve_module.__file__).read_text(
        encoding="utf-8"
    )
