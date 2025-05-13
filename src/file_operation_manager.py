# src/file_operation_manager.py
import logging
import os
from PyQt6.QtWidgets import QFileDialog, QProgressDialog, QMessageBox
from PyQt6.QtCore import Qt

from .renamed_files_dialog import RenamedFilesDialog
from .constants import SELECTION_ORDER_ROLE # SELECTION_ORDER_ROLE をインポート

logger = logging.getLogger(__name__)

class FileOperationManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.progress_dialog = None

    def _handle_move_files_button_clicked(self):
        logger.debug(f"Move files button clicked. Selected files: {self.main_window.selected_file_paths}")
        if not self.main_window.selected_file_paths:
            logger.info("移動するファイルが選択されていません。")
            self.main_window.statusBar.showMessage("移動するファイルを選択してください。", 3000)
            return
        destination_folder = QFileDialog.getExistingDirectory(self.main_window, "移動先フォルダを選択", self.main_window.current_folder_path or "")
        if destination_folder:
            logger.info(f"移動先フォルダが選択されました: {destination_folder}")
            logger.info(f"移動対象ファイル: {self.main_window.selected_file_paths}")
            if self.main_window.file_operations.start_operation("move", self.main_window.selected_file_paths, destination_folder):
                self._set_file_op_buttons_enabled(False)
                total_files_to_move = len(self.main_window.selected_file_paths)
                self.progress_dialog = QProgressDialog(
                    f"ファイルを移動中... (0/{total_files_to_move})",
                    "キャンセル", 0, total_files_to_move, self.main_window
                )
                self.progress_dialog.setWindowTitle("ファイル移動")
                self.progress_dialog.setMinimumDuration(0)
                self.progress_dialog.canceled.connect(self.main_window.file_operations.stop_operation)
                self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                self.progress_dialog.setValue(0)
            else:
                self.main_window.statusBar.showMessage("別のファイル操作が実行中です。", 3000)
        else:
            logger.info("移動先フォルダの選択がキャンセルされました。")

    def _handle_copy_files_button_clicked(self):
        logger.debug(f"Copy files button clicked. Copy selection order: {[item.data(Qt.ItemDataRole.UserRole) for item in self.main_window.copy_selection_order]}")
        if not self.main_window.copy_selection_order:
            logger.info("コピーするファイルが選択されていません (選択順)。")
            self.main_window.statusBar.showMessage("コピーするファイルを順番に選択してください。", 3000)
            return
        destination_folder = QFileDialog.getExistingDirectory(self.main_window, "コピー先フォルダを選択", self.main_window.current_folder_path or "")
        if destination_folder:
            if self.main_window.file_operations.start_operation("copy", None, destination_folder, copy_selection_order=self.main_window.copy_selection_order):
                self._set_file_op_buttons_enabled(False)
                total_files_to_copy = len(self.main_window.copy_selection_order)
                self.progress_dialog = QProgressDialog(
                    f"ファイルをコピー中... (0/{total_files_to_copy})",
                    "キャンセル", 0, total_files_to_copy, self.main_window
                )
                self.progress_dialog.setWindowTitle("ファイルコピー")
                self.progress_dialog.setMinimumDuration(0)
                self.progress_dialog.canceled.connect(self.main_window.file_operations.stop_operation)
                self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                self.progress_dialog.setValue(0)
            else:
                self.main_window.statusBar.showMessage("別のファイル操作が実行中です。", 3000)
        else:
            logger.info("コピー先フォルダの選択がキャンセルされました。")

    def _handle_copy_mode_toggled(self, checked):
        self.main_window.is_copy_mode = checked
        if checked:
            self.main_window.copy_mode_button.setText("Copy Mode Exit")
            self.main_window.move_files_button.setEnabled(False)
            self.main_window.copy_files_button.setEnabled(True)
            self.main_window.deselect_all_thumbnails()
            self.main_window.copy_selection_order.clear()
            logger.info("Copy Mode Enabled.")
        else:
            self.main_window.copy_mode_button.setText("Copy Mode")
            self.main_window.move_files_button.setEnabled(True)
            self.main_window.copy_files_button.setEnabled(False)
            self.main_window.deselect_all_thumbnails()
            self.main_window.copy_selection_order.clear()
            logger.info("Copy Mode Disabled (Move Mode Enabled).")
            for row_idx in range(self.main_window.source_thumbnail_model.rowCount()): # Renamed row to row_idx
                item = self.main_window.source_thumbnail_model.item(row_idx) # Use row_idx
                if item and item.data(SELECTION_ORDER_ROLE) is not None: # 定数 SELECTION_ORDER_ROLE を直接使用
                    item.setData(None, SELECTION_ORDER_ROLE) # 定数 SELECTION_ORDER_ROLE を直接使用
                    source_idx = self.main_window.source_thumbnail_model.indexFromItem(item)
                    proxy_idx = self.main_window.filter_proxy_model.mapFromSource(source_idx)
                    if proxy_idx.isValid():
                         self.main_window.thumbnail_view.update(proxy_idx)

    def _set_file_op_buttons_enabled(self, enabled):
        self.main_window.move_files_button.setEnabled(enabled and not self.main_window.is_copy_mode)
        self.main_window.copy_files_button.setEnabled(enabled and self.main_window.is_copy_mode)
        self.main_window.copy_mode_button.setEnabled(enabled)
        self.main_window.folder_select_button.setEnabled(enabled)
        self.main_window.folder_tree_view.setEnabled(enabled)

    def _handle_file_op_progress(self, processed_count, total_count):
        dialog = self.progress_dialog
        if dialog:
            if dialog.wasCanceled():
                logger.debug(f"Progress update ({processed_count}/{total_count}) received but progress_dialog was canceled by user.")
                return
            try:
                dialog.setMaximum(total_count)
                dialog.setValue(processed_count)
                dialog.setLabelText(f"処理中: {processed_count}/{total_count} ファイル...")
            except RuntimeError as e:
                logger.warning(f"Error updating progress dialog (likely already closed or invalid): {e}")
        else:
            logger.debug(f"Progress update ({processed_count}/{total_count}) received but self.progress_dialog was already None.")

    def _handle_file_op_error(self, error_message):
        logger.error(f"File operation error: {error_message}")
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        QMessageBox.critical(self.main_window, "ファイル操作エラー", f"エラーが発生しました:\n{error_message}")
        self.main_window.statusBar.showMessage("ファイル操作中にエラーが発生しました。", 5000)
        self._set_file_op_buttons_enabled(True)

    def _handle_file_op_finished(self, result):
        logger.info(f"File operation finished. Result: {result}")
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        self._set_file_op_buttons_enabled(True)
        # status = result.get('status', 'unknown') # No longer directly used here
        # operation_type = result.get('operation_type', 'unknown') # No longer directly used here

        # Call MainWindow's method to process the completion details
        self.main_window._process_file_op_completion(result)

    def _handle_cancel_op_button_clicked(self): # Not directly used by FileOperations, but for completeness if UI had explicit cancel
        logger.info("Cancel button clicked. Requesting to stop file operation.")
        if self.main_window.file_operations:
            self.main_window.file_operations.stop_operation()
