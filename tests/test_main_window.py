import unittest
from unittest.mock import patch, MagicMock, call
import os
import sys
import shutil
import tempfile
import logging

# Ensure QApplication instance exists if not already (e.g. when running with pytest)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtWidgets import QMessageBox as OriginalQMessageBox # Import for type checking
from functools import partial # Import partial
# from PyQt6.QtGui import QStandardItemModel, QStandardItem # For potential future deeper mocking
# from PyQt6.QtCore import QModelIndex # For potential future deeper mocking
from PyQt6.QtGui import QStandardItem # For TestMainWindowUIActions

# Add project root to sys.path to allow importing src modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.main_window import MainWindow
from src.full_image_dialog import FullImageDialog # Import FullImageDialog
from src.image_metadata_dialog import ImageMetadataDialog # Import ImageMetadataDialog
from PyQt6.QtCore import Qt as QtConstants, QModelIndex # For Qt.ItemDataRole.UserRole and QModelIndex mock
from src.constants import (
    METADATA_ROLE, SELECTION_ORDER_ROLE, # Added SELECTION_ORDER_ROLE
    THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU
)
from src.renamed_files_dialog import RenamedFilesDialog # Import for mocking


# from src.constants import APP_SETTINGS_FILE # Not strictly needed as app_settings is mocked

# Dummy app_settings for MainWindow instantiation
DEFAULT_TEST_APP_SETTINGS = {
    "thumbnail_size": 128,
    "show_hidden_files": False,
    "sort_column": 0,
    "sort_order": 0, # Qt.AscendingOrder
    "window_geometry": "",
    "full_image_dialog_geometry": "",
    "metadata_dialog_geometry": "",
    "splitter_sizes": [200, 600],
    "recent_folders": [],
    "view_mode": "thumbnails",
    "full_image_view_mode": "fit",
    "language": "en"
}

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestMainWindowEmptyFolderFunctions(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.base_path = self.test_dir.name

        self.mock_app_settings = DEFAULT_TEST_APP_SETTINGS.copy()

        # Patch parts of MainWindow's __init__ to avoid full UI setup and external dependencies.
        patches = [
            patch('src.main_window.MainWindow._load_app_settings', MagicMock()),
            patch('src.main_window.MainWindow._create_menu_bar', MagicMock()),
            # patch('src.main_window.MainWindow._load_settings', MagicMock()), # _load_settings is now part of _load_app_settings
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop) # Ensures patches are stopped even if setUp fails

        self.window = MainWindow()
        self.window.logger = MagicMock(spec=logging.Logger)

        # Helper methods to create test files/directories
        self.create_file = lambda path_suffix: open(os.path.join(self.base_path, path_suffix), 'w').close()
        self.create_dir = lambda path_suffix: os.makedirs(os.path.join(self.base_path, path_suffix), exist_ok=True)

    def tearDown(self):
        self.test_dir.cleanup()

    # Tests for _is_dir_empty_recursive
    def test_is_dir_empty_recursive_truly_empty(self):
        dir_path = os.path.join(self.base_path, "empty_dir")
        os.makedirs(dir_path)
        self.assertTrue(self.window._is_dir_empty_recursive(dir_path))

    def test_is_dir_empty_recursive_with_file(self):
        dir_path = os.path.join(self.base_path, "dir_with_file")
        os.makedirs(dir_path)
        open(os.path.join(dir_path, "file.txt"), 'w').close()
        self.assertFalse(self.window._is_dir_empty_recursive(dir_path))

    def test_is_dir_empty_recursive_with_empty_subdir(self):
        parent_dir = os.path.join(self.base_path, "parent_has_empty_subdir")
        empty_subdir = os.path.join(parent_dir, "empty_subdir")
        os.makedirs(empty_subdir)
        self.assertTrue(self.window._is_dir_empty_recursive(parent_dir))

    def test_is_dir_empty_recursive_with_non_empty_subdir(self):
        parent_dir = os.path.join(self.base_path, "parent_has_non_empty_subdir")
        non_empty_subdir = os.path.join(parent_dir, "non_empty_subdir")
        os.makedirs(non_empty_subdir)
        open(os.path.join(non_empty_subdir, "file.txt"), 'w').close()
        self.assertFalse(self.window._is_dir_empty_recursive(parent_dir))

    def test_is_dir_empty_recursive_nested_empty(self):
        dir1 = os.path.join(self.base_path, "dir1")
        dir2 = os.path.join(dir1, "dir2")
        dir3 = os.path.join(dir2, "dir3")
        os.makedirs(dir3)
        self.assertTrue(self.window._is_dir_empty_recursive(dir1))
        self.assertTrue(self.window._is_dir_empty_recursive(dir2))
        self.assertTrue(self.window._is_dir_empty_recursive(dir3))

    def test_is_dir_empty_recursive_mixed_subdirs(self):
        parent_dir = os.path.join(self.base_path, "parent_mixed")
        os.makedirs(os.path.join(parent_dir, "empty_child"))
        non_empty_child_path = os.path.join(parent_dir, "non_empty_child")
        os.makedirs(non_empty_child_path)
        open(os.path.join(non_empty_child_path, "file.txt"), 'w').close()
        self.assertFalse(self.window._is_dir_empty_recursive(parent_dir))

    # Tests for _find_empty_subfolders
    def test_find_empty_subfolders_complex_structure(self):
        self.create_dir("empty1")
        self.create_dir("not_empty_with_file")
        self.create_file("not_empty_with_file/file.txt")
        self.create_dir("parent_of_empty_child/empty_child")
        self.create_dir("parent_of_mixed_children/empty_grandchild_holder/empty_grandchild")
        self.create_dir("parent_of_mixed_children/non_empty_child_with_file")
        self.create_file("parent_of_mixed_children/non_empty_child_with_file/file.txt")
        self.create_dir("another_empty")
        self.create_dir("not_empty_contains_non_empty_subdir/sub_not_empty")
        self.create_file("not_empty_contains_non_empty_subdir/sub_not_empty/file.txt")

        found_folders = self.window._find_empty_subfolders(self.base_path)
        
        expected_folders = sorted([
            os.path.normpath(os.path.join(self.base_path, "empty1")),
            os.path.normpath(os.path.join(self.base_path, "parent_of_empty_child")),
            os.path.normpath(os.path.join(self.base_path, "another_empty"))
        ])
        self.assertListEqual(sorted(map(os.path.normpath, found_folders)), expected_folders)

    def test_find_empty_subfolders_no_empty_folders(self):
        self.create_dir("dir1_with_file")
        self.create_file("dir1_with_file/file.txt")
        self.create_dir("dir2_with_file")
        self.create_file("dir2_with_file/another.txt")
        
        found_folders = self.window._find_empty_subfolders(self.base_path)
        self.assertEqual(len(found_folders), 0)

    def test_find_empty_subfolders_on_empty_base(self):
        found_folders = self.window._find_empty_subfolders(self.base_path)
        self.assertEqual(len(found_folders), 0)

    @patch('src.main_window.send2trash.send2trash')
    @patch('src.main_window.QMessageBox.question') # Corrected patch target
    @patch('src.main_window.QMessageBox.information') # Corrected patch target
    @patch('src.main_window.QMessageBox.warning') 
    @patch('src.main_window.logger')
    @patch('os.path.exists', return_value=True) 
    @patch('src.main_window.MainWindow.update_folder_tree') 
    def test_handle_send_empty_folders_found_confirm_yes(self, mock_update_tree, mock_path_exists, mock_logger, mock_msgbox_warn, mock_msgbox_info, mock_msgbox_question, mock_send2trash):
        parent_context_path = os.path.join(self.base_path, "parent_for_empty_deletion")
        self.create_dir(parent_context_path)
        
        empty_folder1 = os.path.join(parent_context_path, "empty_child1")
        empty_folder2 = os.path.join(parent_context_path, "empty_child2")
        self.create_dir(empty_folder1)
        self.create_dir(empty_folder2)
        
        empty_folders_to_delete = [empty_folder1, empty_folder2]
        
        mock_msgbox_question.return_value = QMessageBox.StandardButton.Yes
        
        self.window._handle_send_empty_folders_to_trash(parent_context_path, empty_folders_to_delete)
        
        expected_q_msg = "空のサブフォルダが見つかりました。ゴミ箱に移動しますか？\n\n" \
                         f"- {empty_folder1}\n" \
                         f"- {empty_folder2}\n"
        mock_msgbox_question.assert_called_once_with(self.window, "空フォルダ削除の確認", expected_q_msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        
        mock_send2trash.assert_has_calls([call(os.path.normpath(empty_folder1)), call(os.path.normpath(empty_folder2))], any_order=True) # Use normpath
        self.assertEqual(mock_send2trash.call_count, len(empty_folders_to_delete))
            
        expected_summary_title = f"空フォルダ削除完了 ({os.path.basename(parent_context_path)})"
        mock_msgbox_info.assert_called_once_with(self.window, expected_summary_title, f"{len(empty_folders_to_delete)}個のフォルダをゴミ箱に移動しました。")
        mock_update_tree.assert_called_once_with(parent_context_path)


    @patch('src.main_window.send2trash.send2trash')
    @patch('src.main_window.QMessageBox.question') # Corrected patch target
    @patch('src.main_window.logger')
    def test_handle_send_empty_folders_found_confirm_no(self, mock_logger, mock_msgbox_question, mock_send2trash):
        parent_context_path = os.path.join(self.base_path, "parent_for_no_confirm")
        self.create_dir(parent_context_path)
        empty_folder1 = os.path.join(parent_context_path, "empty_child_no_confirm")
        self.create_dir(empty_folder1)
        empty_folders_to_delete = [empty_folder1]

        mock_msgbox_question.return_value = QMessageBox.StandardButton.No
        
        self.window._handle_send_empty_folders_to_trash(parent_context_path, empty_folders_to_delete)
        
        mock_send2trash.assert_not_called()
        mock_logger.info.assert_called_with(f"'{parent_context_path}' 内の空のサブフォルダのゴミ箱への移動はキャンセルされました。")

    @patch('src.main_window.send2trash.send2trash')
    @patch('src.main_window.QMessageBox.question') # Corrected patch target
    @patch('src.main_window.QMessageBox.warning') # Corrected patch target
    @patch('src.main_window.logger')
    @patch('os.path.exists', return_value=True)
    @patch('src.main_window.MainWindow.update_folder_tree')
    def test_handle_send_empty_folders_send2trash_exception(self, mock_update_tree, mock_path_exists, mock_logger, mock_msgbox_warn, mock_msgbox_question, mock_send2trash):
        parent_context_path = os.path.join(self.base_path, "parent_for_exception")
        self.create_dir(parent_context_path)
        
        empty_folder_path = os.path.join(parent_context_path, "problematic_empty_child")
        self.create_dir(empty_folder_path)
        empty_folders_to_delete = [empty_folder_path]
        
        mock_msgbox_question.return_value = QMessageBox.StandardButton.Yes
        test_exception = OSError("Test send2trash error")
        mock_send2trash.side_effect = test_exception
        
        self.window._handle_send_empty_folders_to_trash(parent_context_path, empty_folders_to_delete)
        
        mock_send2trash.assert_called_once_with(os.path.normpath(empty_folder_path))
        mock_logger.error.assert_any_call(f"フォルダ '{os.path.normpath(empty_folder_path)}' のゴミ箱への移動に失敗: {test_exception}", exc_info=True)
        
        expected_summary_title = f"空フォルダ削除完了 ({os.path.basename(parent_context_path)})（一部エラー）"
        expected_warn_msg = f"0個のフォルダをゴミ箱に移動しました。\n\n以下のフォルダの移動に失敗しました:\n{os.path.normpath(empty_folder_path)}: {test_exception}"
        mock_msgbox_warn.assert_called_once_with(self.window, expected_summary_title, expected_warn_msg)
        mock_update_tree.assert_called_once_with(parent_context_path)

    @patch('src.main_window.MainWindow._find_empty_subfolders')
    @patch('src.main_window.MainWindow._handle_send_empty_folders_to_trash')
    @patch('os.path.isdir', return_value=True) 
    @patch('src.main_window.logger')
    def test_try_delete_empty_subfolders_calls_handler_when_found(self, mock_logger, mock_os_isdir, mock_handle_send, mock_find_empty):
        target_folder = os.path.join(self.base_path, "target_for_try_delete")
        self.create_dir(target_folder)
        
        found_empty_folders = [os.path.join(target_folder, "empty1"), os.path.join(target_folder, "empty2")]
        mock_find_empty.return_value = found_empty_folders
        
        self.window._try_delete_empty_subfolders(target_folder)
        
        mock_find_empty.assert_called_once_with(target_folder)
        mock_handle_send.assert_called_once_with(target_folder, found_empty_folders) 
        mock_logger.info.assert_any_call(f"'{target_folder}' 内に {len(found_empty_folders)} 個の空サブフォルダが見つかりました。削除処理を開始します。")

    @patch('src.main_window.MainWindow._find_empty_subfolders')
    @patch('src.main_window.MainWindow._handle_send_empty_folders_to_trash')
    @patch('os.path.isdir', return_value=True)
    @patch('src.main_window.logger')
    def test_try_delete_empty_subfolders_no_handler_call_when_none_found(self, mock_logger, mock_os_isdir, mock_handle_send, mock_find_empty):
        target_folder = os.path.join(self.base_path, "target_for_try_delete_none")
        self.create_dir(target_folder)
        
        mock_find_empty.return_value = [] 
        
        self.window._try_delete_empty_subfolders(target_folder)
        
        mock_find_empty.assert_called_once_with(target_folder)
        mock_handle_send.assert_not_called()
        mock_logger.info.assert_any_call(f"'{target_folder}' 内に空のサブフォルダは見つかりませんでした。")

    @patch('src.main_window.MainWindow._find_empty_subfolders', side_effect=Exception("Find error"))
    @patch('src.main_window.MainWindow._handle_send_empty_folders_to_trash')
    @patch('os.path.isdir', return_value=True)
    @patch('src.main_window.logger')
    def test_try_delete_empty_subfolders_find_exception(self, mock_logger, mock_os_isdir, mock_handle_send, mock_find_empty):
        target_folder = os.path.join(self.base_path, "target_for_try_find_exception")
        self.create_dir(target_folder)

        self.window._try_delete_empty_subfolders(target_folder)

        mock_find_empty.assert_called_once_with(target_folder)
        mock_handle_send.assert_not_called()
        mock_logger.error.assert_called_once_with(f"'{target_folder}' の空フォルダ検索中にエラー: Find error", exc_info=True)

    @patch('os.path.isdir', return_value=False) 
    @patch('src.main_window.MainWindow._find_empty_subfolders')
    @patch('src.main_window.MainWindow._handle_send_empty_folders_to_trash')
    @patch('src.main_window.logger')
    def test_try_delete_empty_subfolders_invalid_path(self, mock_logger, mock_handle_send, mock_find_empty, mock_os_isdir):
        target_folder = os.path.join(self.base_path, "invalid_target_for_try")
        
        self.window._try_delete_empty_subfolders(target_folder)

        mock_os_isdir.assert_called_once_with(target_folder)
        mock_find_empty.assert_not_called()
        mock_handle_send.assert_not_called()
        mock_logger.debug.assert_called_once_with(f"指定されたフォルダパス '{target_folder}' が無効なため、空フォルダ削除をスキップします。")

    @patch('src.main_window.MainWindow._try_delete_empty_subfolders')
    @patch('src.main_window.MainWindow.load_thumbnails_from_folder') 
    @patch('os.path.isdir', return_value=True) 
    def test_on_folder_tree_clicked_calls_try_delete(self, mock_os_isdir, mock_load_thumbnails, mock_try_delete):
        mock_index = MagicMock()
        test_folder_path = os.path.join(self.base_path, "clicked_folder")
        self.create_dir(test_folder_path)

        self.window.file_system_model = MagicMock()
        self.window.file_system_model.filePath.return_value = test_folder_path
        self.window.file_system_model.isDir.return_value = True

        self.window.on_folder_tree_clicked(mock_index)

        mock_load_thumbnails.assert_called_once_with(test_folder_path)
        mock_try_delete.assert_called_once_with(test_folder_path)

    @patch('src.main_window.MainWindow._try_delete_empty_subfolders')
    @patch('src.main_window.MainWindow.load_thumbnails_from_folder')
    @patch('os.path.isdir', return_value=True)
    def test_update_folder_tree_calls_try_delete(self, mock_os_isdir, mock_load_thumbnails, mock_try_delete):
        test_folder_path = os.path.join(self.base_path, "selected_folder_via_button")
        self.create_dir(test_folder_path)

        self.window.file_system_model = MagicMock()
        self.window.folder_tree_view = MagicMock()
        
        self.window.update_folder_tree(test_folder_path)

        mock_load_thumbnails.assert_called_once_with(test_folder_path)
        mock_try_delete.assert_called_once_with(test_folder_path)

    @patch('src.main_window.MainWindow._try_delete_empty_subfolders')
    @patch('src.main_window.MainWindow.deselect_all_thumbnails') 
    def test_handle_file_op_finished_move_calls_try_delete(self, mock_deselect, mock_try_delete):
        source_folder_to_check = os.path.join(self.base_path, "source_of_move")
        self.create_dir(source_folder_to_check)
        
        result = {
            'status': 'completed',
            'operation_type': 'move',
            'moved_count': 1,
            'errors': [],
            'successfully_moved_src_paths': [os.path.join(source_folder_to_check, "moved_file.txt")],
            'destination_folder': os.path.join(self.base_path, "destination_of_move")
        }
        
        self.window.current_folder_path = os.path.join(self.base_path, "some_other_current_folder")
        self.create_dir(self.window.current_folder_path)

        with patch('os.path.isdir', return_value=True): 
             self.window._handle_file_op_finished(result)
        
        called_with_source_folder = False
        for call_args in mock_try_delete.call_args_list:
            if call_args[0][0] == source_folder_to_check:
                called_with_source_folder = True
                break
        self.assertTrue(called_with_source_folder, f"_try_delete_empty_subfolders not called with {source_folder_to_check}")


class TestMainWindowFileOperations(unittest.TestCase):
    def setUp(self):
        self.mock_app_settings = DEFAULT_TEST_APP_SETTINGS.copy()
        patches = [
            patch('src.main_window.MainWindow._load_app_settings', MagicMock()),
            patch('src.main_window.MainWindow._create_menu_bar', MagicMock()),
            patch('src.main_window.MainWindow._read_app_settings_file', return_value=self.mock_app_settings.copy()),
            patch('src.main_window.MainWindow._write_app_settings_file', MagicMock(return_value=None))
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        self.window = MainWindow()
        self.window.logger = MagicMock(spec=logging.Logger)
        self.window.statusBar = MagicMock() 

        self.window.file_operations = MagicMock()
        self.window.file_operations.start_operation = MagicMock(return_value=True) 

        self.window.move_files_button = MagicMock()
        self.window.copy_mode_button = MagicMock()
        self.window.copy_files_button = MagicMock()
        self.window.folder_select_button = MagicMock()
        self.window.folder_tree_view = MagicMock()

        self.mock_qprogress_dialog_patcher = patch('src.main_window.QProgressDialog')
        self.MockQProgressDialog = self.mock_qprogress_dialog_patcher.start()
        self.addCleanup(self.mock_qprogress_dialog_patcher.stop)


    @patch('src.main_window.QFileDialog.getExistingDirectory')
    def test_handle_move_files_button_clicked_no_selection(self, mock_get_existing_directory):
        self.window.selected_file_paths = [] 

        self.window._handle_move_files_button_clicked()

        self.window.statusBar.showMessage.assert_called_once_with("移動するファイルを選択してください。", 3000)
        mock_get_existing_directory.assert_not_called()
        self.window.file_operations.start_operation.assert_not_called()

    @patch('src.main_window.QFileDialog.getExistingDirectory')
    def test_handle_move_files_button_clicked_destination_selected(self, mock_get_existing_directory):
        self.window.selected_file_paths = ["/path/file1.jpg", "/path/file2.png"]
        mock_get_existing_directory.return_value = "/destination/folder"

        mock_progress_dialog_instance = self.MockQProgressDialog.return_value

        self.window._handle_move_files_button_clicked()

        mock_get_existing_directory.assert_called_once()
        self.window.file_operations.start_operation.assert_called_once_with(
            "move", self.window.selected_file_paths, "/destination/folder"
        )
        self.MockQProgressDialog.assert_called_once_with(
            f"ファイルを移動中... (0/{len(self.window.selected_file_paths)})",
            "キャンセル", 0, len(self.window.selected_file_paths), self.window
        )
        mock_progress_dialog_instance.setWindowTitle.assert_called_once_with("ファイル移動")
        mock_progress_dialog_instance.setMinimumDuration.assert_called_once_with(0)
        mock_progress_dialog_instance.canceled.connect.assert_called_once_with(self.window.file_operations.stop_operation)
        mock_progress_dialog_instance.setWindowModality.assert_called_once_with(QtConstants.WindowModality.WindowModal)
        mock_progress_dialog_instance.setValue.assert_called_once_with(0)

        with patch.object(self.window, '_set_file_op_buttons_enabled') as mock_set_enabled:
            # Re-run the method to check the side effect on buttons
            self.window.file_operations.start_operation.return_value = True # Ensure it's true for this path
            self.window._handle_move_files_button_clicked() # Call again
            mock_set_enabled.assert_called_with(False)


    @patch('src.main_window.QFileDialog.getExistingDirectory')
    def test_handle_move_files_button_clicked_destination_cancelled(self, mock_get_existing_directory):
        self.window.selected_file_paths = ["/path/file1.jpg"]
        mock_get_existing_directory.return_value = "" 

        self.window._handle_move_files_button_clicked()

        mock_get_existing_directory.assert_called_once()
        self.window.file_operations.start_operation.assert_not_called()
        self.MockQProgressDialog.assert_not_called() 

    def test_handle_copy_mode_toggled_on(self):
        """Test toggling copy mode ON."""
        self.window.is_copy_mode = False 
        self.window.copy_selection_order = [MagicMock()] 
        self.window.deselect_all_thumbnails = MagicMock() 

        self.window._handle_copy_mode_toggled(True) # Toggle ON

        self.assertTrue(self.window.is_copy_mode)
        self.window.copy_mode_button.setText.assert_called_once_with("Copy Mode Exit")
        self.window.move_files_button.setEnabled.assert_called_once_with(False)
        self.window.copy_files_button.setEnabled.assert_called_once_with(True)
        self.window.deselect_all_thumbnails.assert_called_once()
        self.assertEqual(self.window.copy_selection_order, [])

    def test_handle_copy_mode_toggled_off(self):
        """Test toggling copy mode OFF."""
        self.window.is_copy_mode = True 
        self.window.copy_selection_order = [MagicMock()]
        self.window.deselect_all_thumbnails = MagicMock()

        mock_item_with_role = MagicMock()
        mock_item_with_role.data.return_value = 1 
        mock_item_without_role = MagicMock()
        mock_item_without_role.data.return_value = None 
        self.window.source_thumbnail_model = MagicMock()
        self.window.source_thumbnail_model.rowCount.return_value = 2
        self.window.source_thumbnail_model.item = MagicMock(side_effect=[mock_item_with_role, mock_item_without_role])
        
        self.window.thumbnail_view = MagicMock() 
        self.window.filter_proxy_model = MagicMock() 
        # Mock mapFromSource to return a valid QModelIndex
        self.window.filter_proxy_model.mapFromSource.return_value = MagicMock(spec=QModelIndex)
        self.window.filter_proxy_model.mapFromSource.return_value.isValid.return_value = True


        self.window._handle_copy_mode_toggled(False) # Toggle OFF

        self.assertFalse(self.window.is_copy_mode)
        self.window.copy_mode_button.setText.assert_called_once_with("Copy Mode")
        self.window.move_files_button.setEnabled.assert_called_once_with(True)
        self.window.copy_files_button.setEnabled.assert_called_once_with(False)
        self.window.deselect_all_thumbnails.assert_called_once()
        self.assertEqual(self.window.copy_selection_order, [])
        
        mock_item_with_role.setData.assert_called_once_with(None, SELECTION_ORDER_ROLE)
        self.assertTrue(self.window.thumbnail_view.update.called)

    @patch('src.main_window.QFileDialog.getExistingDirectory')
    def test_handle_copy_files_button_clicked_no_selection(self, mock_get_existing_directory):
        """Test copy files button click when no files are in copy_selection_order."""
        self.window.copy_selection_order = [] 

        self.window._handle_copy_files_button_clicked()

        self.window.statusBar.showMessage.assert_called_once_with("コピーするファイルを順番に選択してください。", 3000)
        mock_get_existing_directory.assert_not_called()
        self.window.file_operations.start_operation.assert_not_called()

    @patch('src.main_window.QFileDialog.getExistingDirectory')
    def test_handle_copy_files_button_clicked_destination_selected(self, mock_get_existing_directory):
        """Test copy files button click when files are selected and destination is chosen."""
        mock_item1 = MagicMock()
        mock_item1.data.return_value = "/path/copy_file1.jpg" 
        self.window.copy_selection_order = [mock_item1]
        mock_get_existing_directory.return_value = "/copy_destination/folder"

        mock_progress_dialog_instance = self.MockQProgressDialog.return_value

        self.window._handle_copy_files_button_clicked()

        mock_get_existing_directory.assert_called_once()
        self.window.file_operations.start_operation.assert_called_once_with(
            "copy", None, "/copy_destination/folder", copy_selection_order=self.window.copy_selection_order
        )
        self.MockQProgressDialog.assert_called_once_with(
            f"ファイルをコピー中... (0/{len(self.window.copy_selection_order)})",
            "キャンセル", 0, len(self.window.copy_selection_order), self.window
        )
        mock_progress_dialog_instance.setWindowTitle.assert_called_once_with("ファイルコピー")
        
        with patch.object(self.window, '_set_file_op_buttons_enabled') as mock_set_enabled:
            self.window.file_operations.start_operation.return_value = True
            self.window._handle_copy_files_button_clicked() # Call again
            mock_set_enabled.assert_called_with(False)


    @patch('src.main_window.QFileDialog.getExistingDirectory')
    def test_handle_copy_files_button_clicked_destination_cancelled(self, mock_get_existing_directory):
        """Test copy files button click when destination selection is cancelled."""
        self.window.copy_selection_order = [MagicMock()]
        mock_get_existing_directory.return_value = "" 

        self.window._handle_copy_files_button_clicked()

        mock_get_existing_directory.assert_called_once()
        self.window.file_operations.start_operation.assert_not_called()
        self.MockQProgressDialog.assert_not_called()

    def test_set_file_op_buttons_enabled_true(self):
        """Test _set_file_op_buttons_enabled when enabling buttons."""
        self.window.is_copy_mode = False # Move mode
        self.window._set_file_op_buttons_enabled(True)
        self.window.move_files_button.setEnabled.assert_called_with(True)
        self.window.copy_files_button.setEnabled.assert_called_with(False) # Should be false in move mode
        self.window.copy_mode_button.setEnabled.assert_called_with(True)
        self.window.folder_select_button.setEnabled.assert_called_with(True)
        self.window.folder_tree_view.setEnabled.assert_called_with(True)

    def test_set_file_op_buttons_enabled_false(self):
        """Test _set_file_op_buttons_enabled when disabling buttons."""
        self.window._set_file_op_buttons_enabled(False)
        self.window.move_files_button.setEnabled.assert_called_with(False)
        self.window.copy_files_button.setEnabled.assert_called_with(False)
        self.window.copy_mode_button.setEnabled.assert_called_with(False)
        self.window.folder_select_button.setEnabled.assert_called_with(False)
        self.window.folder_tree_view.setEnabled.assert_called_with(False)

    def test_handle_file_op_progress(self):
        """Test _handle_file_op_progress updates the progress dialog."""
        # Ensure a progress dialog instance is set up for the window
        self.window.progress_dialog = self.MockQProgressDialog() # Create an instance
        # Ensure wasCanceled returns False for this test path
        self.window.progress_dialog.wasCanceled.return_value = False

        self.window._handle_file_op_progress(5, 10)

        self.window.progress_dialog.setMaximum.assert_called_once_with(10)
        self.window.progress_dialog.setValue.assert_called_once_with(5)
        self.window.progress_dialog.setLabelText.assert_called_once_with("処理中: 5/10 ファイル...")

    def test_handle_file_op_progress_dialog_cancelled(self):
        """Test _handle_file_op_progress when dialog was cancelled."""
        mock_progress_dialog_instance = self.MockQProgressDialog.return_value
        mock_progress_dialog_instance.wasCanceled.return_value = True
        self.window.progress_dialog = mock_progress_dialog_instance

        self.window._handle_file_op_progress(1, 2)

        mock_progress_dialog_instance.setValue.assert_not_called() # Should not update if cancelled

    @patch('src.main_window.QMessageBox.critical')
    def test_handle_file_op_error(self, mock_qmessagebox_critical):
        """Test _handle_file_op_error shows error message and enables buttons."""
        # Simulate an existing progress dialog
        mock_dialog_instance = self.MockQProgressDialog()
        self.window.progress_dialog = mock_dialog_instance

        with patch.object(self.window, '_set_file_op_buttons_enabled') as mock_set_enabled:
            self.window._handle_file_op_error("Test Error Message")

            mock_dialog_instance.close.assert_called_once() # Check close on the instance
            self.assertIsNone(self.window.progress_dialog)
            mock_qmessagebox_critical.assert_called_once_with(self.window, "ファイル操作エラー", "エラーが発生しました:\nTest Error Message")
            self.window.statusBar.showMessage.assert_called_once_with("ファイル操作中にエラーが発生しました。", 5000)
            mock_set_enabled.assert_called_once_with(True)

    @patch('src.main_window.RenamedFilesDialog')
    @patch('src.main_window.MainWindow._try_delete_empty_subfolders') # Mock this to avoid its complexities
    def test_handle_file_op_finished_move_success_with_rename(self, mock_try_delete, MockRenamedFilesDialog): # Added mock_try_delete
        """Test _handle_file_op_finished for a successful move operation with renamed files."""        
        mock_dialog_instance = self.MockQProgressDialog() # Create a mock instance
        self.window.progress_dialog = mock_dialog_instance # Assign it
        self.window.selected_file_paths = ["/original/path.txt"] 
        self.window.source_thumbnail_model = MagicMock() 
        self.window.source_thumbnail_model.rowCount.return_value = 1
        mock_item = MagicMock()
        mock_item.data.return_value = "/original/path.txt" # UserRole
        self.window.source_thumbnail_model.item.return_value = mock_item
        mock_item.row.return_value = 0 # Simulate it's the first row
        mock_item.model.return_value = self.window.source_thumbnail_model # Ensure model matches
        self.window.source_thumbnail_model.indexFromItem.return_value = MagicMock() 
        self.window.filter_proxy_model = MagicMock() 

        result = {
            'status': 'completed', 'operation_type': 'move', 'moved_count': 1,
            'renamed_files': [{'original': 'old.txt', 'new': 'new.txt'}], 'errors': [],
            'successfully_moved_src_paths': ["/original/path.txt"]
        }
        # Ensure os.path.isdir returns True for the paths that will be checked
        with patch('src.main_window.os.path.isdir', return_value=True), \
             patch.object(self.window, '_set_file_op_buttons_enabled') as mock_set_enabled:
            self.window._handle_file_op_finished(result) # mock_try_delete is now passed as arg
            mock_dialog_instance.close.assert_called_once() # Check close on the instance
            self.assertIsNone(self.window.progress_dialog)
            mock_set_enabled.assert_called_once_with(True)
            self.window.statusBar.showMessage.assert_any_call("1個のファイルを移動しました。", 5000) # Check if it was called at least once with these args
            MockRenamedFilesDialog.assert_called_once()
            self.window.source_thumbnail_model.removeRow.assert_called_once()
            self.assertEqual(self.window.selected_file_paths, []) 
            mock_try_delete.assert_called() 


class TestMainWindowSortFilterUI(unittest.TestCase):
    def setUp(self):
        self.mock_app_settings = DEFAULT_TEST_APP_SETTINGS.copy()
        patches = [
            patch('src.main_window.MainWindow._load_app_settings', MagicMock()),
            patch('src.main_window.MainWindow._create_menu_bar', MagicMock()),
            patch('src.main_window.MainWindow._read_app_settings_file', return_value=self.mock_app_settings.copy()),
            patch('src.main_window.MainWindow._write_app_settings_file', MagicMock(return_value=None))
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        self.window = MainWindow()
        self.window.logger = MagicMock(spec=logging.Logger)
        self.window.statusBar = MagicMock()

        # Mock UI elements related to sort/filter
        self.window.sort_key_combo = MagicMock()
        self.window.sort_order_button = MagicMock()
        self.window.positive_prompt_filter_edit = MagicMock()
        self.window.negative_prompt_filter_edit = MagicMock()
        self.window.generation_info_filter_edit = MagicMock()
        self.window.and_radio_button = MagicMock()
        self.window.or_radio_button = MagicMock()
        self.window.apply_filter_button = MagicMock() # Though not directly tested here, good to have

        # Mock methods that are called by the UI handlers
        self.window._perform_sort = MagicMock()
        self.window.filter_proxy_model = MagicMock() # Mock the proxy model
        self.window.deselect_all_thumbnails = MagicMock()
        self.window._update_status_bar_info = MagicMock()

    def test_toggle_sort_order_and_apply_from_ascending(self):
        """Test toggling sort order from Ascending to Descending."""
        self.window.current_sort_order = QtConstants.SortOrder.AscendingOrder
        self.window.sort_order_button.text.return_value = "昇順 ▲" # Initial text

        self.window._toggle_sort_order_and_apply()

        self.assertEqual(self.window.current_sort_order, QtConstants.SortOrder.DescendingOrder)
        self.window.sort_order_button.setText.assert_called_once_with("降順 ▼")
        self.window._perform_sort.assert_called_once() # _apply_sort_and_filter_update calls _perform_sort

    def test_toggle_sort_order_and_apply_from_descending(self):
        """Test toggling sort order from Descending to Ascending."""
        self.window.current_sort_order = QtConstants.SortOrder.DescendingOrder
        self.window.sort_order_button.text.return_value = "降順 ▼" # Initial text

        self.window._toggle_sort_order_and_apply()

        self.assertEqual(self.window.current_sort_order, QtConstants.SortOrder.AscendingOrder)
        self.window.sort_order_button.setText.assert_called_once_with("昇順 ▲")
        self.window._perform_sort.assert_called_once()

    def test_apply_sort_and_filter_update_calls_perform_sort(self):
        """Test that _apply_sort_and_filter_update calls _perform_sort."""
        self.window.sort_key_combo.currentIndex.return_value = 1 # Simulate "Update Date"
        
        self.window._apply_sort_and_filter_update()

        self.assertEqual(self.window.current_sort_key_index, 1)
        self.window._perform_sort.assert_called_once()

    def test_apply_filters_sets_proxy_filters(self):
        """Test that apply_filters correctly sets filters on the proxy model."""
        self.window.and_radio_button.isChecked.return_value = True # Simulate AND mode
        self.window.positive_prompt_filter_edit.text.return_value = "positive_test"
        self.window.negative_prompt_filter_edit.text.return_value = "negative_test"
        self.window.generation_info_filter_edit.text.return_value = "gen_info_test"

        self.window.apply_filters(preserve_selection=False)

        self.window.deselect_all_thumbnails.assert_called_once()
        self.window.filter_proxy_model.set_search_mode.assert_called_once_with("AND")
        self.window.filter_proxy_model.set_positive_prompt_filter.assert_called_once_with("positive_test")
        self.window.filter_proxy_model.set_negative_prompt_filter.assert_called_once_with("negative_test")
        self.window.filter_proxy_model.set_generation_info_filter.assert_called_once_with("gen_info_test")
        self.window._update_status_bar_info.assert_called_once()

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
