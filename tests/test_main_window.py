"""MainWindow integration tests against the public controller contracts."""

import os

from PIL import Image
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtGui import QCloseEvent

from src.constants import SORT_BY_LOAD_ORDER_ALWAYS
from src.main_window import MainWindow, NavigationResult


def _make_images(folder, names=("a.png", "b.jpg")):
    folder.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(names):
        image = Image.new("RGB", (32, 24), (index * 80, 20, 200))
        image.save(folder / name)


def _wait_for_thumbnails(qapplication, window, timeout_ms=3000):
    from PyQt6.QtTest import QTest

    elapsed = 0
    while window.is_loading_thumbnails and elapsed < timeout_ms:
        qapplication.processEvents()
        QTest.qWait(10)
        elapsed += 10
    qapplication.processEvents()
    assert not window.is_loading_thumbnails


def test_navigation_uses_one_path_and_loads_generated_images(tmp_path, qapplication, mocker):
    folder = tmp_path / "日本語 assets"
    _make_images(folder)
    window = MainWindow()
    mocker.patch.object(window, "_try_delete_empty_subfolders")
    try:
        result = window.request_folder_navigation(str(folder), source="favorite")
        assert result.status == "accepted"
        assert os.path.normcase(window.current_folder_path) == os.path.normcase(str(folder))
        assert {os.path.normcase(path) for path in window.thumbnail_controller.paths()} == {
            os.path.normcase(str(folder / "a.png")),
            os.path.normcase(str(folder / "b.jpg")),
        }
        assert window.is_loading_thumbnails
        _wait_for_thumbnails(qapplication, window)
        assert window.ui_manager.source_thumbnail_model.rowCount() == 2
        first_path = next(path for path in window.thumbnail_controller.paths() if path.lower().endswith("a.png"))
        assert window.thumbnail_controller.metadata_for(first_path) is not None
        window._try_delete_empty_subfolders.assert_not_called()
    finally:
        window.close()


def test_same_folder_navigation_keeps_selection_and_does_not_start_a_generation(
    tmp_path, qapplication,
):
    folder = tmp_path / "images"
    _make_images(folder)
    window = MainWindow()
    try:
        assert window.request_folder_navigation(str(folder), source="tree").status == "accepted"
        _wait_for_thumbnails(qapplication, window)
        path = next(path for path in window.thumbnail_controller.paths() if path.lower().endswith("a.png"))
        window.selection_controller.toggle(path)
        generation = window.thumbnail_controller._generation

        result = window.request_folder_navigation(str(folder), source="favorite")

        assert result.status == "unchanged"
        assert window.thumbnail_controller._generation == generation
        assert window.selection_controller.selected_paths() == (path,)
    finally:
        window.close()


def test_same_current_path_permission_error_is_unavailable_and_keeps_state(
    tmp_path, qapplication, mocker,
):
    folder = tmp_path / "images"
    _make_images(folder)
    window = MainWindow()
    try:
        window.request_folder_navigation(str(folder), source="tree")
        _wait_for_thumbnails(qapplication, window)
        path = window.thumbnail_controller.paths()[0]
        window.selection_controller.toggle(path)
        before = (window.thumbnail_controller.paths(), window.selection_controller.selected_paths(),
                  window.thumbnail_controller._generation)
        mocker.patch("src.main_window.os.scandir", side_effect=PermissionError("access denied"))

        result = window.request_folder_navigation(str(folder), source="favorite")

        assert result.status == "unavailable"
        assert (window.thumbnail_controller.paths(), window.selection_controller.selected_paths(),
                window.thumbnail_controller._generation) == before
    finally:
        window.close()


def test_unavailable_folder_keeps_current_model_selection_sort_and_generation(
    tmp_path, qapplication,
):
    folder = tmp_path / "images"
    _make_images(folder)
    window = MainWindow()
    try:
        assert window.request_folder_navigation(str(folder), source="tree").status == "accepted"
        _wait_for_thumbnails(qapplication, window)
        path = next(path for path in window.thumbnail_controller.paths() if path.lower().endswith("a.png"))
        window.selection_controller.set_copy_mode(True)
        window.selection_controller.toggle(path)
        before = (
            window.current_folder_path,
            window.thumbnail_controller.paths(),
            window.selection_controller.selected_paths(),
            window.selection_controller.copy_paths(),
            window.current_sort_button_id,
            window.thumbnail_controller._generation,
        )

        result = window.request_folder_navigation(str(tmp_path / "removed"), source="favorite")

        assert result.status == "unavailable"
        assert (
            window.current_folder_path,
            window.thumbnail_controller.paths(),
            window.selection_controller.selected_paths(),
            window.selection_controller.copy_paths(),
            window.current_sort_button_id,
            window.thumbnail_controller._generation,
        ) == before
    finally:
        window.close()


def test_dialog_navigation_calls_empty_folder_confirmation_path_once(
    tmp_path, qapplication, mocker,
):
    folder = tmp_path / "images"
    _make_images(folder)
    window = MainWindow()
    cleanup = mocker.patch.object(window, "_try_delete_empty_subfolders")
    try:
        assert window.request_folder_navigation(str(folder), source="dialog").status == "accepted"
        cleanup.assert_called_once_with(os.path.normpath(str(folder)))
        _wait_for_thumbnails(qapplication, window)
    finally:
        window.close()


def test_favorites_tab_switch_keeps_navigation_and_selection_and_preserves_sort_source(
    tmp_path, qapplication,
):
    folder_a, folder_b = tmp_path / "a", tmp_path / "b"
    _make_images(folder_a, ("a.png",))
    _make_images(folder_b, ("b.png",))
    window = MainWindow()
    try:
        window.initial_folder_sort_setting = SORT_BY_LOAD_ORDER_ALWAYS
        window.current_sort_button_id = 1
        window.request_folder_navigation(str(folder_a), source="tree")
        _wait_for_thumbnails(qapplication, window)
        path_a = window.thumbnail_controller.paths()[0]
        window.selection_controller.toggle(path_a)
        generation = window.thumbnail_controller._generation

        tabs = window.ui_manager.folder_navigation_tabs
        tabs.setCurrentIndex(1)
        tabs.setCurrentIndex(0)

        assert window.thumbnail_controller._generation == generation
        assert window.selection_controller.selected_paths() == (path_a,)
        assert window.current_sort_button_id == 1

        window.request_folder_navigation(str(folder_b), source="favorite")
        _wait_for_thumbnails(qapplication, window)
        assert window.current_sort_button_id == 1
        window.request_folder_navigation(str(folder_a), source="dialog")
        _wait_for_thumbnails(qapplication, window)
        assert window.current_sort_button_id == 4
    finally:
        window.close()


def test_recursive_toggle_changes_enumeration_on_refresh(tmp_path, qapplication):
    folder = tmp_path / "images"
    _make_images(folder, ("root.png",))
    _make_images(folder / "nested", ("nested.jpg",))
    window = MainWindow()
    try:
        window.recursive_search_enabled = False
        window.request_folder_navigation(str(folder), source="tree")
        _wait_for_thumbnails(qapplication, window)
        assert len(window.thumbnail_controller.paths()) == 1

        window.recursive_search_enabled = True
        window.request_folder_navigation(str(folder), source="refresh", force_reload=True)
        _wait_for_thumbnails(qapplication, window)
        assert len(window.thumbnail_controller.paths()) == 2
    finally:
        window.close()


def test_thumbnail_size_refreshes_and_rolls_back_when_navigation_fails(
    tmp_path, qapplication, mocker,
):
    folder = tmp_path / "images"
    _make_images(folder, ("one.png",))
    window = MainWindow()
    try:
        window.request_folder_navigation(str(folder), source="tree")
        _wait_for_thumbnails(qapplication, window)
        generation = window.thumbnail_controller._generation

        assert window.apply_thumbnail_size_change(200)
        assert window.current_thumbnail_size == 200
        assert window.thumbnail_controller._generation == generation + 1
        _wait_for_thumbnails(qapplication, window)

        update_sizes = mocker.spy(window.ui_manager, "update_thumbnail_view_sizes")
        mocker.patch.object(window, "request_folder_navigation",
                            return_value=NavigationResult("unavailable", "denied"))
        assert not window.apply_thumbnail_size_change(96)
        assert window.current_thumbnail_size == 200
        assert update_sizes.call_count == 2
    finally:
        window.close()


def test_close_waits_for_both_workers_and_retries_after_both_are_idle(
    tmp_path, qapplication, mocker,
):
    window = MainWindow()
    thumb_idle = [False]
    file_busy = [True]
    mocker.patch.object(window.thumbnail_controller, "is_idle", side_effect=lambda: thumb_idle[0])
    mocker.patch.object(window.thumbnail_controller, "shutdown")
    mocker.patch.object(window.file_operations, "is_busy", side_effect=lambda: file_busy[0])
    stop_file = mocker.patch.object(window.file_operations, "stop_operation")
    mocker.patch.object(window, "_save_settings")
    close_spy = mocker.patch.object(window, "close")

    try:
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted()
        assert window._closing
        assert window.request_folder_navigation(str(tmp_path), source="favorite").status == "busy"
        stop_file.assert_called_once()

        thumb_idle[0] = True
        window._maybe_finish_close()
        qapplication.processEvents()
        close_spy.assert_not_called()  # File operations are still active.

        file_busy[0] = False
        window._maybe_finish_close()
        qapplication.processEvents()
        close_spy.assert_called_once()
    finally:
        # Restore mocked state so the test does not leave a Qt window/controller alive.
        thumb_idle[0] = True
        file_busy[0] = False
        window.thumbnail_controller.is_idle = lambda: True
        window.file_operations.is_busy = lambda: False
        window.close = lambda: None


def test_select_folder_routes_through_common_navigation(tmp_path, qapplication, mocker):
    folder = tmp_path / "chosen"
    _make_images(folder)
    window = MainWindow()
    mocker.patch.object(QFileDialog, "getExistingDirectory", return_value=str(folder))
    navigation = mocker.spy(window, "request_folder_navigation")
    try:
        window.select_folder()
        navigation.assert_called_once_with(str(folder), source="dialog")
        _wait_for_thumbnails(qapplication, window)
    finally:
        window.close()


def test_favorite_remove_keeps_current_images_and_never_trashes_folder(
    tmp_path, qapplication, mocker,
):
    folder = tmp_path / "images"
    _make_images(folder, ("one.png",))
    window = MainWindow()
    trash = mocker.patch("src.main_window.send2trash.send2trash")
    try:
        window.request_folder_navigation(str(folder), source="tree")
        _wait_for_thumbnails(qapplication, window)
        path = window.thumbnail_controller.paths()[0]
        window.selection_controller.toggle(path)
        window._favorite_add()
        entry = window.favorites.entries()[0]
        before = (window.current_folder_path, window.thumbnail_controller.paths(),
                  window.selection_controller.selected_paths())

        window._favorite_remove(entry.key)

        assert window.favorites.entries() == ()
        assert (window.current_folder_path, window.thumbnail_controller.paths(),
                window.selection_controller.selected_paths()) == before
        assert folder.exists()
        trash.assert_not_called()
    finally:
        window.close()


def test_explorer_failure_keeps_current_navigation_and_reports_message(
    tmp_path, qapplication, mocker,
):
    folder = tmp_path / "current"
    _make_images(folder, ("one.png",))
    missing = tmp_path / "missing"
    window = MainWindow()
    mocker.patch("src.main_window.os.startfile", side_effect=OSError("denied"))
    try:
        window.request_folder_navigation(str(folder), source="tree")
        _wait_for_thumbnails(qapplication, window)
        window.favorites = type(window.favorites)(
            [str(missing)], lambda candidate: window.settings_store.save({"favorite_folders": candidate})
        )
        window._refresh_favorites_panel()
        before = (window.current_folder_path, window.thumbnail_controller.paths())

        window._favorite_open_explorer(window.favorites.entries()[0].key)

        assert (window.current_folder_path, window.thumbnail_controller.paths()) == before
        assert "Explorer" in window.statusBar.currentMessage()
    finally:
        window.close()


def test_app_settings_property_returns_isolated_snapshot(tmp_path, qapplication):
    window = MainWindow()
    try:
        snapshot = window.app_settings
        snapshot["future_key"] = "local mutation"
        assert "future_key" not in window.settings_store.snapshot()
    finally:
        window.close()
