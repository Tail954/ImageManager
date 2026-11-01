"""File-operation results update only successful paths and unlock at real idle."""

import threading

from PIL import Image

from src.file_operation_types import FileOperationResult, FileSuccess
from src.main_window import MainWindow


def _wait_for(predicate, qapplication, timeout_ms=4000):
    from PyQt6.QtTest import QTest

    elapsed = 0
    while not predicate() and elapsed < timeout_ms:
        qapplication.processEvents()
        QTest.qWait(10)
        elapsed += 10
    qapplication.processEvents()
    assert predicate()


def test_partial_cancelled_move_removes_only_successful_path_once(tmp_path, qapplication, mocker):
    source_folder = tmp_path / "images"
    source_folder.mkdir()
    for name in ("one.png", "two.png"):
        Image.new("RGB", (12, 12), (30, 40, 50)).save(source_folder / name)
    destination = tmp_path / "destination"
    destination.mkdir()
    window = MainWindow()
    mocker.patch("src.file_operation_manager.QMessageBox.warning")
    try:
        assert window.request_folder_navigation(str(source_folder), source="tree").status == "accepted"
        _wait_for(lambda: not window.is_loading_thumbnails, qapplication)
        paths = window.thumbnail_controller.paths()
        first, second = paths
        window.selection_controller.set_copy_mode(True)
        window.selection_controller.toggle(first)
        window.selection_controller.toggle(second)

        result = FileOperationResult(
            23, "move", "cancelled", str(destination),
            (FileSuccess(first, str(destination / first.rsplit("/", 1)[-1])),),
            ("second failed",),
        )
        window._process_file_op_completion(result)
        window._process_file_op_completion(result)  # Duplicate result delivery is ignored.

        assert window.thumbnail_controller.paths() == (second,)
        assert window.selection_controller.selected_paths() == (second,)
        assert window.selection_controller.copy_paths() == (second,)
    finally:
        window.close()


def test_navigation_remains_busy_until_operation_thread_reaches_idle(
    tmp_path, qapplication, mocker,
):
    source = tmp_path / "source.bin"
    source.write_bytes(b"copy me")
    destination = tmp_path / "destination"
    destination.mkdir()
    entered, release = threading.Event(), threading.Event()
    real_copy = __import__("shutil").copy2

    def delayed_copy(src, dst):
        entered.set()
        release.wait(3)
        return real_copy(src, dst)

    mocker.patch("src.file_operations.shutil.copy2", side_effect=delayed_copy)
    window = MainWindow()
    busy_observations = []
    window.file_operations.result.connect(
        lambda _result: busy_observations.append(window.file_operations.is_busy())
    )
    try:
        assert window.file_operation_manager.start("copy", [str(source)], str(destination))
        assert entered.wait(2)
        assert window.file_operations.is_busy()
        assert window.request_folder_navigation(str(destination), source="favorite").status == "busy"
        assert window.ui_manager.thumbnail_view.isEnabled() is False

        release.set()
        _wait_for(lambda: not window.file_operations.is_busy(), qapplication)

        assert busy_observations == [True]
        assert window.ui_manager.thumbnail_view.isEnabled() is True
        assert (destination / "001_source.bin").read_bytes() == b"copy me"
    finally:
        release.set()
        if window.file_operations.is_busy():
            _wait_for(lambda: not window.file_operations.is_busy(), qapplication, 6000)
        window.close()
        qapplication.processEvents()
