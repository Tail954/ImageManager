"""Empty-folder discovery is read-only; deletion stays behind explicit UI confirmation."""

from PyQt6.QtWidgets import QMessageBox

from src.folder_cleanup import find_empty_subfolders, is_dir_empty_recursive
from src.main_window import MainWindow


def test_empty_folder_discovery_is_recursive_but_only_returns_direct_children(tmp_path):
    parent = tmp_path / "source"
    direct_empty = parent / "empty"
    nested_empty = parent / "nested" / "empty"
    occupied = parent / "occupied"
    direct_empty.mkdir(parents=True)
    nested_empty.mkdir(parents=True)
    (occupied / "nested").mkdir(parents=True)
    (occupied / "nested" / "file.txt").write_text("keep", encoding="utf-8")

    found = find_empty_subfolders(str(parent))

    assert set(found) == {str(direct_empty), str(parent / "nested")}
    assert is_dir_empty_recursive(str(parent / "nested"))
    assert direct_empty.exists() and nested_empty.exists()


def test_empty_folder_send_cancel_and_confirm_paths(tmp_path, qapplication, mocker):
    parent = tmp_path / "source"
    empty = parent / "empty"
    empty.mkdir(parents=True)
    window = MainWindow()
    send = mocker.patch("src.main_window.send2trash.send2trash")
    information = mocker.patch("src.main_window.QMessageBox.information")
    question = mocker.patch("src.main_window.QMessageBox.question")
    try:
        question.return_value = QMessageBox.StandardButton.No
        window._handle_send_empty_folders_to_trash(str(parent), [str(empty)])
        send.assert_not_called()
        assert empty.exists()

        question.return_value = QMessageBox.StandardButton.Yes
        window._handle_send_empty_folders_to_trash(str(parent), [str(empty)])
        send.assert_called_once_with(str(empty))
        information.assert_called_once()
    finally:
        window.close()


def test_empty_folder_trash_failure_is_reported_without_retry(tmp_path, qapplication, mocker):
    parent = tmp_path / "source"
    empty = parent / "empty"
    empty.mkdir(parents=True)
    window = MainWindow()
    mocker.patch("src.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes)
    send = mocker.patch("src.main_window.send2trash.send2trash", side_effect=PermissionError("denied"))
    warning = mocker.patch("src.main_window.QMessageBox.warning")
    try:
        window._handle_send_empty_folders_to_trash(str(parent), [str(empty)])
        send.assert_called_once_with(str(empty))
        warning.assert_called_once()
        assert empty.exists()
    finally:
        window.close()
