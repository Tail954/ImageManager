"""GUI coordinator for immutable file requests and one-time result application."""

import itertools
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog

from .file_operation_types import FileOperationRequest
from .renamed_files_dialog import RenamedFilesDialog


class FileOperationManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.progress_dialog = None
        self._ids = itertools.count(1)
        self._active_id = None
        self._applied = set()

    def bind_service(self):
        service = self.main_window.file_operations
        service.progress.connect(self._handle_file_op_progress)
        service.result.connect(self._handle_file_op_finished)

    def _handle_move_files_button_clicked(self):
        self._start_dialog("move")

    def _handle_copy_files_button_clicked(self):
        self._start_dialog("copy")

    def _start_dialog(self, operation_type):
        mw = self.main_window
        if mw._closing or mw.is_loading_thumbnails or mw.file_operations.is_busy():
            return
        paths = (mw.selection_controller.copy_paths() if operation_type == "copy"
                 else mw.selection_controller.selected_paths())
        if not paths:
            mw.statusBar.showMessage("操作するファイルを選択してください。", 3000)
            return
        last = (mw.last_copy_destination_folder if operation_type == "copy"
                else mw.last_move_destination_folder)
        start = last if last and os.path.isdir(last) else (mw.current_folder_path or "")
        destination = QFileDialog.getExistingDirectory(
            mw, "コピー先フォルダを選択" if operation_type == "copy" else "移動先フォルダを選択", start)
        if not destination:
            return
        self.start(operation_type, paths, destination)

    def start(self, operation_type, paths, destination_folder):
        mw = self.main_window
        if mw._closing or mw.is_loading_thumbnails or mw.file_operations.is_busy() or self._active_id is not None:
            return False
        request = FileOperationRequest(next(self._ids), operation_type,
                                       tuple(paths), destination_folder)
        if not mw.file_operations.start(request):
            return False
        self._active_id = request.operation_id
        total = len(request.source_paths)
        dialog = QProgressDialog(f"処理中... 0/{total}", "キャンセル", 0, total, mw)
        dialog.setWindowTitle("ファイルコピー" if operation_type == "copy" else "ファイル移動")
        dialog.setMinimumDuration(0)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.canceled.connect(mw.file_operations.stop_operation)
        self.progress_dialog = dialog
        dialog.setValue(0)
        mw._update_operation_locks()
        return True

    def _handle_copy_mode_toggled(self, checked):
        mw = self.main_window
        mw.is_copy_mode = checked
        mw.selection_controller.set_copy_mode(checked)
        mw.ui_manager.update_copy_mode_button_text(checked)
        mw._update_operation_locks()

    def _handle_file_op_progress(self, operation_id, processed, total):
        dialog = self.progress_dialog
        if operation_id != self._active_id or dialog is None or dialog.wasCanceled():
            return
        dialog.setMaximum(total)
        dialog.setValue(processed)
        dialog.setLabelText(f"処理中: {processed}/{total} ファイル...")

    def _handle_file_op_finished(self, result):
        if result.operation_id != self._active_id:
            return
        if self.progress_dialog is not None:
            self.progress_dialog.canceled.disconnect(self.main_window.file_operations.stop_operation)
            self.progress_dialog.close()
            self.progress_dialog = None
        self.apply_result(result)
        self._active_id = None

    def apply_result(self, result):
        if result.operation_id in self._applied:
            return
        self._applied.add(result.operation_id)
        mw = self.main_window
        successes = result.successes
        if result.operation_type == "move":
            moved = tuple(success.source_path for success in successes)
            mw.selection_controller.remove_paths(moved)
            mw.thumbnail_controller.remove_paths(moved)
            renamed = [{"original": os.path.basename(success.source_path),
                        "new": os.path.basename(success.destination_path)}
                       for success in successes
                       if os.path.basename(success.source_path) != os.path.basename(success.destination_path)]
            if renamed:
                RenamedFilesDialog(renamed, mw).exec()
            if successes and os.path.isdir(result.destination_folder):
                mw.last_move_destination_folder = result.destination_folder
        elif result.operation_type == "copy" and successes and os.path.isdir(result.destination_folder):
            mw.last_copy_destination_folder = result.destination_folder
        if result.errors:
            QMessageBox.warning(mw, "ファイル操作エラー", "\n".join(result.errors))
        if result.status == "completed" and not result.errors:
            mw.selection_controller.clear()
        if result.status == "cancelled":
            mw.statusBar.showMessage(f"{len(successes)}個を処理後、キャンセルしました。", 5000)
        elif result.status == "error":
            mw.statusBar.showMessage("ファイル操作中にエラーが発生しました。", 5000)
        else:
            verb = "コピー" if result.operation_type == "copy" else "移動"
            mw.statusBar.showMessage(f"{len(successes)}個のファイルを{verb}しました。", 5000)

    def _handle_cancel_op_button_clicked(self):
        self.main_window.file_operations.stop_operation()
