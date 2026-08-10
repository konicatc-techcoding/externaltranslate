from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.captions.presets import (
    CaptionPreset,
    PresetError,
    PresetStore,
)


def _preset(name: str = "主畫面") -> CaptionPreset:
    return CaptionPreset(
        name=name,
        chars_per_line=20,
        max_lines=2,
        font="jhenghei",
        size=48,
        color="#FFFFFF",
        scroll=True,
        scroll_ms=250,
    )


@pytest.fixture
def store(tmp_path: Path) -> PresetStore:
    return PresetStore(tmp_path / "caption-presets.json")


def test_starts_empty_without_a_file(store: PresetStore) -> None:
    assert store.list() == []


def test_save_then_read_back(store: PresetStore) -> None:
    store.save(_preset())
    assert [item.name for item in store.list()] == ["主畫面"]
    assert store.get("主畫面").size == 48


def test_saving_the_same_name_overwrites(store: PresetStore) -> None:
    store.save(_preset())
    store.save(
        CaptionPreset(**{**_preset().__dict__, "size": 72})  # same name
    )
    assert len(store.list()) == 1
    assert store.get("主畫面").size == 72


def test_presets_survive_a_new_store_on_the_same_file(tmp_path: Path) -> None:
    path = tmp_path / "caption-presets.json"
    PresetStore(path).save(_preset())
    assert [item.name for item in PresetStore(path).list()] == ["主畫面"]


def test_delete(store: PresetStore) -> None:
    store.save(_preset())
    store.delete("主畫面")
    assert store.list() == []


def test_unknown_name_fails_closed(store: PresetStore) -> None:
    with pytest.raises(PresetError):
        store.get("不存在")
    with pytest.raises(PresetError):
        store.delete("不存在")


def test_name_is_data_not_a_path(store: PresetStore, tmp_path: Path) -> None:
    # Names live inside one JSON file precisely so a name can never become a
    # filesystem path.
    store.save(_preset(name="../../evil"))
    assert [item.name for item in store.list()] == ["../../evil"]
    assert list(tmp_path.iterdir()) == [tmp_path / "caption-presets.json"]


def test_blank_and_oversized_names_are_rejected(store: PresetStore) -> None:
    for name in ("", "   ", "x" * 200):
        with pytest.raises(PresetError):
            store.save(_preset(name=name))


def test_invalid_values_are_rejected(store: PresetStore) -> None:
    for field, value in (
        ("chars_per_line", 0),
        ("chars_per_line", 999),
        ("max_lines", 0),
        ("max_lines", 99),
        ("size", 4),
        ("size", 9999),
        ("scroll_ms", 10),
        ("font", "comic-sans"),
        ("color", "red"),
        ("color", "#FFF"),
    ):
        with pytest.raises(PresetError):
            store.save(CaptionPreset(**{**_preset().__dict__, field: value}))


def test_a_corrupt_file_does_not_take_the_app_down(tmp_path: Path) -> None:
    path = tmp_path / "caption-presets.json"
    path.write_text("{ this is not json", encoding="utf-8")
    # Reading falls back to empty rather than crashing the control page.
    assert PresetStore(path).list() == []


def test_entries_that_fail_validation_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "caption-presets.json"
    path.write_text(
        json.dumps(
            {
                "good": {**_preset(name="good").__dict__},
                "bad": {"name": "bad", "size": "huge"},
            }
        ),
        encoding="utf-8",
    )
    assert [item.name for item in PresetStore(path).list()] == ["good"]


def test_saving_never_writes_a_secret_looking_field(store: PresetStore) -> None:
    store.save(_preset())
    written = store.path.read_text(encoding="utf-8").lower()
    for secret in ("api_key", "apikey", "token", "secret", "password"):
        assert secret not in written
