import json

from src.constants import DOUBLE_CLICK_ACTION_VIEWER_METADATA, FAVORITE_FOLDERS
from src.settings_store import SettingsStore


def test_load_validates_defaults_and_preserves_unknown_and_favorites(tmp_path):
    settings_path = tmp_path / "app_settings.json"
    settings_path.write_text(json.dumps({
        "thumbnail_size": 200,
        "double_click_action": DOUBLE_CLICK_ACTION_VIEWER_METADATA,
        FAVORITE_FOLDERS: ["C:\\Pictures"],
        "future_setting": {"keep": True},
        "recursive_search": 1,
    }), encoding="utf-8")

    store = SettingsStore(settings_path)
    loaded = store.load()

    assert loaded["thumbnail_size"] == 200
    assert loaded["double_click_action"] == DOUBLE_CLICK_ACTION_VIEWER_METADATA
    assert loaded[FAVORITE_FOLDERS] == ["C:\\Pictures"]
    assert loaded["future_setting"] == {"keep": True}
    assert loaded["recursive_search"] is True


def test_save_partial_update_preserves_existing_and_unknown_keys(tmp_path):
    settings_path = tmp_path / "app_settings.json"
    store = SettingsStore(settings_path)
    store.load()
    assert store.save({FAVORITE_FOLDERS: ["C:\\Models"], "extension_key": "preserved"})
    assert store.save({"double_click_action": DOUBLE_CLICK_ACTION_VIEWER_METADATA})

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved[FAVORITE_FOLDERS] == ["C:\\Models"]
    assert saved["extension_key"] == "preserved"
    assert saved["double_click_action"] == DOUBLE_CLICK_ACTION_VIEWER_METADATA


def test_failed_atomic_replace_keeps_file_and_memory_snapshot(tmp_path, mocker):
    settings_path = tmp_path / "app_settings.json"
    settings_path.write_text('{"keep":"old"}', encoding="utf-8")
    store = SettingsStore(settings_path)
    store.load()
    before = store.snapshot()
    mocker.patch("src.settings_store.os.replace", side_effect=OSError("disk full"))

    assert store.save({FAVORITE_FOLDERS: ["C:\\Models"]}) is False
    assert settings_path.read_text(encoding="utf-8") == '{"keep":"old"}'
    assert store.snapshot() == before


def test_invalid_updates_are_rejected_without_mutating_state(tmp_path):
    store = SettingsStore(tmp_path / "app_settings.json")
    before = store.snapshot()

    try:
        store.update({"thumbnail_size": True})
    except ValueError:
        pass
    else:
        raise AssertionError("bool must not be accepted as a thumbnail size")

    assert store.snapshot() == before

