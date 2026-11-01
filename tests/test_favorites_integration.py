import json
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QListWidget

from src.constants import FAVORITE_FOLDERS
from src.favorite_folders import FavoriteFolders, normalize_folder_path
from src.favorites_panel import FavoritesPanel
from src.main_window import MainWindow
from src.settings_store import SettingsStore


def test_windows_drive_roots_unc_and_extended_paths():
    assert normalize_folder_path("C:/")[0] == "C:\\"
    assert normalize_folder_path("C:\\Pictures\\..\\Models\\")[0] == "C:\\Models"
    assert normalize_folder_path("\\\\server\\share\\")[0] == "\\\\server\\share\\"
    assert normalize_folder_path("\\\\?\\C:\\Pictures")[0] == "C:\\Pictures"
    assert normalize_folder_path("\\\\?\\UNC\\server\\share\\Models")[0] == "\\\\server\\share\\Models"


@pytest.mark.parametrize("path", ["relative", "\\\\.\\PhysicalDrive0", "\\\\?\\GLOBALROOT\\Device\\HarddiskVolume1", "C:\\bad\x00path"])
def test_invalid_or_device_paths_are_rejected(path):
    with pytest.raises(ValueError):
        normalize_folder_path(path)


def test_restore_normalizes_deduplicates_and_keeps_missing_paths():
    model = FavoriteFolders(
        ["C:\\Gone\\", "c:/gone", "\\\\server\\share\\folder"],
        lambda _paths: True,
    )
    entries = model.entries()
    assert [entry.path for entry in entries] == ["C:\\Gone", "\\\\server\\share\\folder"]
    assert len(entries) == 2


def test_add_duplicate_names_show_parent_and_order_is_persisted():
    writes = []
    model = FavoriteFolders([], lambda paths: writes.append(paths) or True)
    assert model.add("C:\\One\\Assets").status == "added"
    assert model.add("C:\\Two\\Assets").status == "added"
    assert [entry.display_name for entry in model.entries()] == [
        "Assets — C:\\One", "Assets — C:\\Two"
    ]
    assert model.add("c:/one/assets/").status == "duplicate"
    keys = [entry.key for entry in reversed(model.entries())]
    assert model.reorder(keys).status == "reordered"
    assert [entry.path for entry in model.entries()] == ["C:\\Two\\Assets", "C:\\One\\Assets"]
    assert writes[-1] == ["C:\\Two\\Assets", "C:\\One\\Assets"]


def test_failed_add_remove_and_reorder_restore_previous_state():
    allow_save = True
    saved = []

    def persist(paths):
        saved.append(paths)
        return allow_save

    model = FavoriteFolders(["C:\\Keep", "C:\\Keep2"], persist)
    before = model.entries()
    allow_save = False
    assert model.add("C:\\New").status == "save_failed"
    assert model.remove(before[0].key).status == "save_failed"
    original_order = [entry.key for entry in before]
    assert model.reorder(list(reversed(original_order))).status == "save_failed"
    assert model.entries() == before


def test_favorites_internal_drop_reorders_model_once_without_activation(qapplication, mocker):
    panel = FavoritesPanel()
    entries = FavoriteFolders(
        ["C:\\One", "C:\\Two", "C:\\Three"], lambda _paths: True
    ).entries()
    panel.set_entries(entries)
    order_changes, activations = [], []
    panel.orderChanged.connect(order_changes.append)
    panel.activateRequested.connect(activations.append)
    widget = panel.list_widget
    before = [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count())]

    class DropEvent:
        def source(self):
            return widget

        def isAccepted(self):
            return self.accepted

        def accept(self):
            self.accepted = True

        def ignore(self):
            self.accepted = False

    event = DropEvent()
    event.accepted = False

    def simulate_qt_internal_move(list_widget, drop_event):
        item = list_widget.takeItem(0)
        list_widget.insertItem(2, item)
        drop_event.accept()

    mocker.patch.object(QListWidget, "dropEvent", simulate_qt_internal_move)
    widget.dropEvent(event)

    expected = [before[1], before[2], before[0]]
    assert [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count())] == expected
    assert order_changes == [expected]
    assert activations == []


def test_external_drop_is_rejected_without_reorder_or_activation(qapplication, mocker):
    panel = FavoritesPanel()
    entry = FavoriteFolders(["C:\\One"], lambda _paths: True).entries()
    panel.set_entries(entry)
    orders, activations = [], []
    panel.orderChanged.connect(orders.append)
    panel.activateRequested.connect(activations.append)
    base_drop = mocker.patch.object(QListWidget, "dropEvent")

    class ExternalDrop:
        accepted = True

        def source(self):
            return object()

        def ignore(self):
            self.accepted = False

    event = ExternalDrop()
    panel.list_widget.dropEvent(event)

    assert event.accepted is False
    base_drop.assert_not_called()
    assert orders == activations == []
    assert panel.list_widget.count() == 1


def test_main_window_reorder_success_and_save_failure_restore_visual_order(
    tmp_path, qapplication, mocker,
):
    window = MainWindow()
    paths = ["C:\\One", "C:\\Two"]
    window.favorites = FavoriteFolders(
        paths, lambda candidate: window.settings_store.save({FAVORITE_FOLDERS: candidate})
    )
    panel = window.ui_manager.favorites_panel
    window._refresh_favorites_panel()
    before = [entry.key for entry in window.favorites.entries()]
    proposed = list(reversed(before))
    item = panel.list_widget.takeItem(0)
    panel.list_widget.insertItem(1, item)
    panel.list_widget.reordered.emit(proposed)

    assert [entry.key for entry in window.favorites.entries()] == proposed
    assert window.settings_store.get(FAVORITE_FOLDERS) == ["C:\\Two", "C:\\One"]

    item = panel.list_widget.takeItem(0)
    panel.list_widget.insertItem(1, item)
    mocker.patch.object(window.settings_store, "save", return_value=False)
    panel.list_widget.reordered.emit(before)

    assert [entry.key for entry in window.favorites.entries()] == proposed
    assert [panel.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(panel.list_widget.count())] == proposed
    window.close()


def test_favorites_panel_programmatic_restore_is_silent_and_has_full_tooltips(qapplication):
    panel = FavoritesPanel()
    entries = FavoriteFolders(
        ["C:\\One\\Assets", "C:\\Two\\Assets"], lambda _paths: True
    ).entries()
    panel.activateRequested.connect(lambda _key: pytest.fail("restore must not navigate"))
    panel.orderChanged.connect(lambda _keys: pytest.fail("restore must not persist a reorder"))
    panel.set_entries(entries)
    panel.set_current_key(entries[1].key)

    assert panel.list_widget.count() == 2
    assert panel.list_widget.item(0).toolTip() == "C:\\One\\Assets"
    assert panel.list_widget.item(0).text() == "Assets — C:\\One"
    assert panel.list_widget.item(0).font().bold() is False
    assert panel.list_widget.item(1).font().bold() is True


def test_favorites_panel_add_and_left_release_emit_expected_requests(qapplication):
    panel = FavoritesPanel()
    entries = FavoriteFolders(["C:\\Models"], lambda _paths: True).entries()
    additions, activations = [], []
    panel.addRequested.connect(lambda: additions.append(True))
    panel.activateRequested.connect(activations.append)
    panel.set_entries(entries)
    panel.show()

    QTest.mouseClick(panel.add_button, Qt.MouseButton.LeftButton)
    rect = panel.list_widget.visualItemRect(panel.list_widget.item(0))
    QTest.mouseClick(panel.list_widget.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())

    assert additions == [True]
    assert activations == [entries[0].key]


def test_favorites_panel_context_actions_emit_keys_without_removing_or_navigating(qapplication, mocker):
    panel = FavoritesPanel()
    entries = FavoriteFolders(["C:\\Models"], lambda _paths: True).entries()
    removed, copied, opened = [], [], []
    panel.removeRequested.connect(removed.append)
    panel.copyPathRequested.connect(copied.append)
    panel.openInExplorerRequested.connect(opened.append)
    panel.set_entries(entries)
    item = panel.list_widget.item(0)

    menu = MagicMock()
    remove_action, copy_action, explorer_action = object(), object(), object()
    menu.addAction.side_effect = [remove_action, copy_action, explorer_action]
    menu.exec.return_value = remove_action
    mocker.patch("src.favorites_panel.QMenu", return_value=menu)
    panel._context_menu(panel.list_widget.visualItemRect(item).center())

    assert removed == [entries[0].key]
    assert copied == opened == []
    assert panel.list_widget.count() == 1


def test_favorites_settings_survive_partial_updates(tmp_path):
    settings = SettingsStore(tmp_path / "app_settings.json")
    settings.load()
    assert settings.save({FAVORITE_FOLDERS: ["C:\\Missing", "\\\\server\\share\\Folder"]})
    restored = SettingsStore(settings.path)
    assert restored.load()[FAVORITE_FOLDERS] == ["C:\\Missing", "\\\\server\\share\\Folder"]
    assert restored.save({"double_click_action": "viewer_metadata"})
    assert SettingsStore(settings.path).load()[FAVORITE_FOLDERS] == [
        "C:\\Missing", "\\\\server\\share\\Folder"
    ]

