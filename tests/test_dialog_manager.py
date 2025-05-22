# tests/test_dialog_manager.py
import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure src directory is in Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.dialog_manager import DialogManager
from src.settings_dialog import SettingsDialog # To mock its methods
from src.full_image_dialog import FullImageDialog # To mock its methods
from src.image_metadata_dialog import ImageMetadataDialog # To mock its methods
from src.drop_window import DropWindow # To mock its methods
from src.wc_creator_dialog import WCCreatorDialog # To mock its methods
from src.constants import (
    PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM,
    RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU,
    WC_FORMAT_HASH_COMMENT,
    DELETE_EMPTY_FOLDERS_ENABLED, # ★★★ インポート追加 ★★★
    THUMBNAIL_RIGHT_CLICK_ACTION, WC_COMMENT_OUTPUT_FORMAT, # For app_settings keys
    METADATA_ROLE, Qt as ConstantsQt # For item data roles
)

# Mock QMessageBox for tests that might trigger it
from PyQt6.QtWidgets import QMessageBox, QApplication, QDialog # Added QApplication, QDialog


class TestDialogManager(unittest.TestCase):

    def setUp(self):
        # Mock MainWindow instance
        self.mock_main_window = MagicMock()
        self.mock_main_window.current_thumbnail_size = 128
        self.mock_main_window.available_sizes = [96, 128, 200]
        self.mock_main_window.image_preview_mode = PREVIEW_MODE_FIT
        self.mock_main_window.thumbnail_right_click_action = RIGHT_CLICK_ACTION_METADATA
        self.mock_main_window.wc_creator_comment_format = WC_FORMAT_HASH_COMMENT
        self.mock_main_window.is_loading_thumbnails = False
        self.mock_main_window.delete_empty_folders_enabled = True # ★★★ 追加: MainWindowのモックに属性を追加 ★★★
        self.mock_main_window.app_settings = {} # Mock app_settings dictionary
        self.mock_main_window._write_app_settings_file = MagicMock()
        self.mock_main_window.apply_thumbnail_size_change = MagicMock(return_value=True)

        # ★★★ UIManager のモックを追加 ★★★
        self.mock_ui_manager = MagicMock()
        self.mock_main_window.ui_manager = self.mock_ui_manager
        # UIManager が持つモデルやビューをモック化
        self.mock_ui_manager.filter_proxy_model = MagicMock()
        self.mock_ui_manager.source_thumbnail_model = MagicMock()
        self.mock_ui_manager.thumbnail_view = MagicMock()
        self.mock_ui_manager.thumbnail_view.selectionModel.return_value.selectedIndexes.return_value = [] # Default to no selection

        # MainWindow's METADATA_ROLE is used by DialogManager, so ensure it's available
        self.mock_main_window.METADATA_ROLE = METADATA_ROLE
        # Mocks for ImageMetadataDialog interaction
        self.mock_main_window.metadata_cache = {}
        self.mock_main_window.metadata_dialog_last_geometry = None



        self.dialog_manager = DialogManager(self.mock_main_window)

    @patch('src.dialog_manager.SettingsDialog') # Patch SettingsDialog where it's imported in dialog_manager
    def test_open_settings_dialog_accepted_no_changes(self, MockSettingsDialog):
        """Test opening settings dialog and accepting with no changes."""
        mock_dialog_instance = MockSettingsDialog.return_value
        mock_dialog_instance.exec.return_value = True # Simulate OK pressed

        # Simulate dialog returning the same values as current main_window settings
        mock_dialog_instance.get_selected_preview_mode.return_value = self.mock_main_window.image_preview_mode
        mock_dialog_instance.get_selected_right_click_action.return_value = self.mock_main_window.thumbnail_right_click_action
        mock_dialog_instance.get_selected_wc_comment_format.return_value = self.mock_main_window.wc_creator_comment_format
        mock_dialog_instance.get_selected_thumbnail_size.return_value = self.mock_main_window.current_thumbnail_size
        mock_dialog_instance.get_selected_delete_empty_folders_setting.return_value = self.mock_main_window.delete_empty_folders_enabled # ★★★ 追加 ★★★

        self.dialog_manager.open_settings_dialog()

        MockSettingsDialog.assert_called_once_with(
            current_thumbnail_size=self.mock_main_window.current_thumbnail_size,
            available_thumbnail_sizes=self.mock_main_window.available_sizes,
            current_preview_mode=self.mock_main_window.image_preview_mode,
            current_right_click_action=self.mock_main_window.thumbnail_right_click_action,
            current_wc_comment_format=self.mock_main_window.wc_creator_comment_format,
            current_delete_empty_folders_setting=self.mock_main_window.delete_empty_folders_enabled, # ★★★ 追加 ★★★
            parent=self.mock_main_window
        )
        mock_dialog_instance.exec.assert_called_once()
        self.mock_main_window._write_app_settings_file.assert_called_once() # Settings are always written on OK
        self.mock_main_window.apply_thumbnail_size_change.assert_not_called() # Size didn't change

    @patch('src.dialog_manager.SettingsDialog')
    @patch('src.dialog_manager.QMessageBox.question') # Patch QMessageBox.question directly
    def test_open_settings_dialog_accepted_thumbnail_size_changed(self, mock_qmessagebox_question, MockSettingsDialog):
        """Test changing thumbnail size and confirming."""
        mock_dialog_instance = MockSettingsDialog.return_value
        mock_dialog_instance.exec.return_value = True # OK

        new_thumb_size = 200
        mock_dialog_instance.get_selected_thumbnail_size.return_value = new_thumb_size
        # Other settings remain unchanged
        mock_dialog_instance.get_selected_preview_mode.return_value = self.mock_main_window.image_preview_mode
        mock_dialog_instance.get_selected_right_click_action.return_value = self.mock_main_window.thumbnail_right_click_action
        mock_dialog_instance.get_selected_wc_comment_format.return_value = self.mock_main_window.wc_creator_comment_format
        mock_dialog_instance.get_selected_delete_empty_folders_setting.return_value = self.mock_main_window.delete_empty_folders_enabled # ★★★ 追加 ★★★

        # Mock QMessageBox.question to simulate user confirming "Ok"
        mock_qmessagebox_question.return_value = QMessageBox.StandardButton.Ok


        self.dialog_manager.open_settings_dialog()

        mock_qmessagebox_question.assert_called_once() # Ensure confirmation was asked
        self.mock_main_window.apply_thumbnail_size_change.assert_called_once_with(new_thumb_size)
        self.assertEqual(self.mock_main_window.app_settings["thumbnail_size"], new_thumb_size)
        self.assertEqual(self.mock_main_window.app_settings[DELETE_EMPTY_FOLDERS_ENABLED], self.mock_main_window.delete_empty_folders_enabled) # ★★★ 追加 ★★★
        self.mock_main_window._write_app_settings_file.assert_called_once()

    @patch('src.dialog_manager.SettingsDialog')
    def test_open_settings_dialog_cancelled(self, MockSettingsDialog):
        """Test cancelling the settings dialog."""
        mock_dialog_instance = MockSettingsDialog.return_value
        mock_dialog_instance.exec.return_value = False # Simulate Cancel pressed

        self.dialog_manager.open_settings_dialog()

        mock_dialog_instance.exec.assert_called_once()
        self.mock_main_window._write_app_settings_file.assert_not_called()
        self.mock_main_window.apply_thumbnail_size_change.assert_not_called()

    # --- Tests for open_full_image_dialog ---

    def _prepare_mocks_for_full_image_dialog(self, file_path="path/to/image.jpg", visible_paths_count=1, item_exists=True):
        """Helper to set up mocks for open_full_image_dialog tests."""
        mock_proxy_index = MagicMock()
        mock_proxy_index.isValid.return_value = True

        mock_source_index = MagicMock()
        # self.mock_ui_manager.filter_proxy_model.mapToSource.return_value = mock_source_index # Overwritten by side_effect below

        if item_exists:
            mock_item = MagicMock()
            mock_item.data = MagicMock(side_effect=lambda role: file_path if role == ConstantsQt.ItemDataRole.UserRole else None)
            # self.mock_ui_manager.source_thumbnail_model.itemFromIndex.return_value = mock_item # Overwritten by side_effect below
        # else:
            # self.mock_ui_manager.source_thumbnail_model.itemFromIndex.return_value = None # Overwritten by side_effect below

        self.mock_ui_manager.filter_proxy_model.rowCount.return_value = visible_paths_count
        
        mock_loop_item = MagicMock()
        mock_loop_item.data = MagicMock(side_effect=lambda role: file_path if role == ConstantsQt.ItemDataRole.UserRole else None)

        mock_loop_proxy_idx = MagicMock()
        mock_loop_source_idx = MagicMock()
        self.mock_ui_manager.filter_proxy_model.index = MagicMock(return_value=mock_loop_proxy_idx)
        
        def map_to_source_side_effect(idx):
            if idx == mock_proxy_index:
                return mock_source_index
            elif idx == mock_loop_proxy_idx:
                return mock_loop_source_idx
            return MagicMock()
        self.mock_ui_manager.filter_proxy_model.mapToSource.side_effect = map_to_source_side_effect
        
        # This mock_item is for the initially clicked item
        initial_mock_item = MagicMock()
        initial_mock_item.data = MagicMock(side_effect=lambda role: file_path if role == ConstantsQt.ItemDataRole.UserRole else None)

        def item_from_index_side_effect(idx):
            if idx == mock_source_index: # For the initially clicked item
                return initial_mock_item
            elif idx == mock_loop_source_idx: # For items in the loop
                return mock_loop_item
            return None
        self.mock_ui_manager.source_thumbnail_model.itemFromIndex.side_effect = item_from_index_side_effect

        return mock_proxy_index

    @patch('src.dialog_manager.FullImageDialog')
    def test_open_full_image_dialog_new_instance(self, MockFullImageDialog):
        """Test opening a new FullImageDialog instance."""
        mock_proxy_idx = self._prepare_mocks_for_full_image_dialog(file_path="test/img.jpg", visible_paths_count=1)
        mock_dialog_instance = MockFullImageDialog.return_value
        self.dialog_manager.full_image_dialog_instance = None 

        self.dialog_manager.open_full_image_dialog(mock_proxy_idx)

        MockFullImageDialog.assert_called_once()
        call_args = MockFullImageDialog.call_args[0]
        call_kwargs = MockFullImageDialog.call_args[1] 
        self.assertIsInstance(call_args[0], list) 
        self.assertEqual(call_args[0], ["test/img.jpg"]) 
        self.assertEqual(call_args[1], 0)  
        self.assertEqual(call_kwargs['preview_mode'], self.mock_main_window.image_preview_mode) 
        self.assertIs(call_kwargs['parent'], self.mock_main_window) 

        mock_dialog_instance.setAttribute.assert_called_once_with(ConstantsQt.WidgetAttribute.WA_DeleteOnClose, True)
        mock_dialog_instance.finished.connect.assert_called_once_with(self.dialog_manager._on_full_image_dialog_finished)
        mock_dialog_instance.show.assert_called_once()
        self.assertIs(self.dialog_manager.full_image_dialog_instance, mock_dialog_instance)

    def test_on_full_image_dialog_finished_clears_instance(self):
        """Test that _on_full_image_dialog_finished clears the instance reference."""
        self.dialog_manager.full_image_dialog_instance = MagicMock(spec=FullImageDialog)
        self.dialog_manager._on_full_image_dialog_finished()
        self.assertIsNone(self.dialog_manager.full_image_dialog_instance)

    # --- Tests for open_metadata_dialog and related methods ---

    def _prepare_mocks_for_metadata_dialog(self, file_path="path/to/meta_image.png", item_exists=True, metadata_in_item=None, metadata_in_cache=None):
        """Helper to set up mocks for metadata dialog tests."""
        mock_proxy_index = MagicMock()
        mock_proxy_index.isValid.return_value = True

        mock_source_index = MagicMock()
        self.mock_ui_manager.filter_proxy_model.mapToSource.return_value = mock_source_index

        if item_exists:
            mock_item = MagicMock()
            def item_data_side_effect(role):
                if role == ConstantsQt.ItemDataRole.UserRole:
                    return file_path
                elif role == METADATA_ROLE: # Use METADATA_ROLE directly from constants
                    return metadata_in_item
                return None
            mock_item.data = MagicMock(side_effect=item_data_side_effect)
            self.mock_ui_manager.source_thumbnail_model.itemFromIndex.return_value = mock_item
        else:
            self.mock_ui_manager.source_thumbnail_model.itemFromIndex.return_value = None

        self.mock_main_window.metadata_cache.clear()
        if metadata_in_cache:
            self.mock_main_window.metadata_cache[file_path] = metadata_in_cache

        return mock_proxy_index

    @patch('src.dialog_manager.ImageMetadataDialog')
    @patch('src.dialog_manager.QApplication') 
    def test_open_metadata_dialog_new_instance_from_item(self, MockQApplication, MockImageMetadataDialog):
        """Test opening a new ImageMetadataDialog using metadata from the item."""
        mock_screen = MagicMock()
        mock_screen.availableGeometry.return_value = MagicMock() 
        MockQApplication.primaryScreen.return_value = mock_screen

        test_metadata = {"positive": "from item"}
        mock_proxy_idx = self._prepare_mocks_for_metadata_dialog(metadata_in_item=test_metadata)
        mock_dialog_instance = MockImageMetadataDialog.return_value
        self.dialog_manager.metadata_dialog_instance = None 

        self.dialog_manager.open_metadata_dialog(mock_proxy_idx)

        MockImageMetadataDialog.assert_called_once_with(
            test_metadata, self.mock_main_window, "path/to/meta_image.png"
        )
        mock_dialog_instance.setAttribute.assert_called_once_with(ConstantsQt.WidgetAttribute.WA_DeleteOnClose, True)
        mock_dialog_instance.finished.connect.assert_called_once_with(self.dialog_manager._on_metadata_dialog_finished)
        mock_dialog_instance.show.assert_called_once()
        self.assertIs(self.dialog_manager.metadata_dialog_instance, mock_dialog_instance)

    @patch('src.dialog_manager.ImageMetadataDialog')
    @patch('src.dialog_manager.QApplication')
    def test_open_metadata_dialog_existing_instance_update(self, MockQApplication, MockImageMetadataDialog):
        """Test updating an existing ImageMetadataDialog instance."""
        mock_screen = MagicMock()
        mock_screen.availableGeometry.return_value = MagicMock()
        MockQApplication.primaryScreen.return_value = mock_screen

        test_metadata_cache = {"positive": "from cache"}
        mock_proxy_idx = self._prepare_mocks_for_metadata_dialog(metadata_in_item=None, metadata_in_cache=test_metadata_cache)

        existing_mock_dialog = MagicMock(spec=ImageMetadataDialog)
        existing_mock_dialog.isVisible.return_value = True 
        self.dialog_manager.metadata_dialog_instance = existing_mock_dialog

        self.dialog_manager.open_metadata_dialog(mock_proxy_idx)

        MockImageMetadataDialog.assert_not_called() 
        existing_mock_dialog.update_metadata.assert_called_once_with(test_metadata_cache, "path/to/meta_image.png")
        existing_mock_dialog.raise_.assert_called_once()
        existing_mock_dialog.activateWindow.assert_called_once()

    def test_on_metadata_dialog_finished_clears_instance(self):
        """Test that _on_metadata_dialog_finished clears the instance reference."""
        mock_dialog = MagicMock(spec=QDialog) 
        mock_dialog.geometry.return_value = MagicMock() 
        self.dialog_manager.metadata_dialog_instance = mock_dialog
        
        with patch.object(self.mock_main_window, 'sender', return_value=mock_dialog):
            self.dialog_manager._on_metadata_dialog_finished(0) 
        self.assertIsNone(self.dialog_manager.metadata_dialog_instance)
        self.assertIsNotNone(self.mock_main_window.metadata_dialog_last_geometry)

    # --- Tests for DropWindow interaction ---

    @patch('src.dialog_manager.DropWindow')
    def test_toggle_drop_window_new_instance_show(self, MockDropWindow):
        """Test toggling DropWindow when it's not yet created (shows it)."""
        mock_drop_window_instance = MockDropWindow.return_value
        mock_drop_window_instance.isVisible.return_value = False # Assume not visible after creation
        self.dialog_manager.drop_window_instance = None

        self.dialog_manager.toggle_drop_window()

        MockDropWindow.assert_called_once_with(dialog_manager=self.dialog_manager)
        mock_drop_window_instance.show.assert_called_once()
        self.assertIs(self.dialog_manager.drop_window_instance, mock_drop_window_instance)

    @patch('src.dialog_manager.DropWindow')
    def test_toggle_drop_window_existing_instance_hide(self, MockDropWindow):
        """Test toggling DropWindow when it exists and is visible (hides it)."""
        mock_drop_window_instance = MagicMock(spec=DropWindow)
        mock_drop_window_instance.isVisible.return_value = True # Assume visible
        self.dialog_manager.drop_window_instance = mock_drop_window_instance

        self.dialog_manager.toggle_drop_window()

        MockDropWindow.assert_not_called() # Should not create a new one
        mock_drop_window_instance.hide.assert_called_once()

    @patch('src.dialog_manager.DropWindow')
    def test_toggle_drop_window_existing_instance_show(self, MockDropWindow):
        """Test toggling DropWindow when it exists and is hidden (shows it)."""
        mock_drop_window_instance = MagicMock(spec=DropWindow)
        mock_drop_window_instance.isVisible.return_value = False # Assume hidden
        self.dialog_manager.drop_window_instance = mock_drop_window_instance

        self.dialog_manager.toggle_drop_window()

        MockDropWindow.assert_not_called()
        mock_drop_window_instance.show.assert_called_once()

    @patch('src.dialog_manager.os.path.isfile', return_value=True)
    @patch('src.metadata_utils.extract_image_metadata') # Corrected patch target
    @patch.object(DialogManager, '_show_specific_metadata_dialog') 
    def test_show_metadata_for_dropped_file_valid_file_no_cache(self, mock_show_specific_dialog, mock_extract_metadata, mock_isfile):
        """Test showing metadata for a dropped file (not in cache)."""
        test_file_path = "dropped/image.png"
        expected_metadata = {"positive": "dropped metadata"}
        mock_extract_metadata.return_value = expected_metadata
        self.mock_main_window.metadata_cache.clear() 

        self.dialog_manager.show_metadata_for_dropped_file(test_file_path)

        mock_isfile.assert_called_once_with(test_file_path)
        mock_extract_metadata.assert_called_once_with(test_file_path)
        self.assertEqual(self.mock_main_window.metadata_cache[test_file_path], expected_metadata)
        mock_show_specific_dialog.assert_called_once_with(expected_metadata, item_file_path_for_debug=test_file_path)

    @patch('src.dialog_manager.os.path.isfile', return_value=True)
    @patch('src.metadata_utils.extract_image_metadata') # Corrected patch target
    @patch.object(DialogManager, '_show_specific_metadata_dialog')
    def test_show_metadata_for_dropped_file_valid_file_from_cache(self, mock_show_specific_dialog, mock_extract_metadata, mock_isfile):
        """Test showing metadata for a dropped file (from cache)."""
        test_file_path = "cached/image.jpg"
        cached_metadata = {"positive": "cached data"}
        self.mock_main_window.metadata_cache[test_file_path] = cached_metadata

        self.dialog_manager.show_metadata_for_dropped_file(test_file_path)

        mock_isfile.assert_called_once_with(test_file_path)
        mock_extract_metadata.assert_not_called() 
        mock_show_specific_dialog.assert_called_once_with(cached_metadata, item_file_path_for_debug=test_file_path)

    # --- Tests for WCCreatorDialog interaction ---

    def _prepare_mocks_for_wc_creator(self, selected_item_details=None):
        """Helper to set up mocks for open_wc_creator_dialog tests."""
        if selected_item_details is None:
            selected_item_details = [] 

        mock_selected_proxy_indexes = []
        
        map_to_source_dict = {}
        item_from_index_dict = {}

        self.mock_main_window.metadata_cache.clear()

        for i, (file_path, metadata_on_item, metadata_in_cache) in enumerate(selected_item_details):
            mock_proxy_idx = MagicMock(name=f"proxy_idx_{i}")
            mock_proxy_idx.column.return_value = 0
            mock_selected_proxy_indexes.append(mock_proxy_idx)

            mock_source_idx = MagicMock(name=f"source_idx_{i}")
            map_to_source_dict[mock_proxy_idx] = mock_source_idx
            
            mock_item = MagicMock(name=f"item_{i}")
            
            def create_item_data_side_effect(fp_local, meta_local):
                def item_data_side_effect(role):
                    if role == ConstantsQt.ItemDataRole.UserRole:
                        return fp_local
                    elif role == METADATA_ROLE:
                        return meta_local
                    return None
                return item_data_side_effect

            mock_item.data = MagicMock(side_effect=create_item_data_side_effect(file_path, metadata_on_item))
            item_from_index_dict[mock_source_idx] = mock_item

            if metadata_in_cache is not None: # Ensure None isn't added to cache
                self.mock_main_window.metadata_cache[file_path] = metadata_in_cache # metadata_cache is on main_window
        
        self.mock_ui_manager.filter_proxy_model.mapToSource = MagicMock(side_effect=lambda p_idx: map_to_source_dict.get(p_idx))
        self.mock_ui_manager.source_thumbnail_model.itemFromIndex = MagicMock(side_effect=lambda s_idx: item_from_index_dict.get(s_idx))
        self.mock_ui_manager.thumbnail_view.selectionModel.return_value.selectedIndexes.return_value = mock_selected_proxy_indexes

    @patch('src.dialog_manager.WCCreatorDialog')
    @patch('src.dialog_manager.QMessageBox') 
    @patch('src.metadata_utils.extract_image_metadata') 
    def test_open_wc_creator_dialog_with_selection(self, mock_extract_metadata, MockQMessageBox, MockWCCreatorDialog):
        """Test opening WCCreatorDialog when items are selected."""
        selected_details = [
            ("path/wc1.jpg", {"positive_prompt": "wc_item1_meta"}, None),
            ("path/wc2.png", None, {"positive_prompt": "wc_item2_cache_meta"}) 
        ]
        self._prepare_mocks_for_wc_creator(selected_item_details=selected_details)
        mock_extract_metadata.return_value = {"positive_prompt": "extracted_default"} 

        self.dialog_manager.open_wc_creator_dialog()

        MockWCCreatorDialog.assert_called_once()
        call_args = MockWCCreatorDialog.call_args[0]
        self.assertEqual(len(call_args[0]), 2) 
        self.assertEqual(len(call_args[1]), 2) 
        self.assertEqual(call_args[2], self.mock_main_window.wc_creator_comment_format) 
        self.assertIs(call_args[3], self.mock_main_window) 
        MockWCCreatorDialog.return_value.exec.assert_called_once()

    @patch('src.dialog_manager.WCCreatorDialog') 
    @patch('src.dialog_manager.QMessageBox.information') 
    def test_open_wc_creator_dialog_no_selection(self, mock_qmessagebox_info, MockWCCreatorDialog):
        """Test opening WCCreatorDialog when no items are selected."""
        self._prepare_mocks_for_wc_creator(selected_item_details=[]) 

        self.dialog_manager.open_wc_creator_dialog()

        mock_qmessagebox_info.assert_called_once_with(
            self.mock_main_window, "情報", "作成対象の画像をサムネイル一覧から選択してください。"
        )
        MockWCCreatorDialog.assert_not_called() 

    @patch('src.dialog_manager.WCCreatorDialog')
    @patch('src.metadata_utils.extract_image_metadata')
    def test_open_wc_creator_dialog_metadata_extraction_fallback(self, mock_extract_metadata, MockWCCreatorDialog):
        """Test that metadata is extracted if not on item or in cache."""
        file_path_for_extraction = "path/extract_this.webp"
        extracted_meta = {"positive_prompt": "extracted_for_wc"}
        mock_extract_metadata.return_value = extracted_meta

        selected_details = [
            (file_path_for_extraction, None, None), 
        ]
        self._prepare_mocks_for_wc_creator(selected_item_details=selected_details)

        self.dialog_manager.open_wc_creator_dialog()

        mock_extract_metadata.assert_called_once_with(file_path_for_extraction)
        MockWCCreatorDialog.assert_called_once()
        call_args = MockWCCreatorDialog.call_args[0]
        self.assertEqual(call_args[1], [extracted_meta]) 

if __name__ == '__main__':
    unittest.main()
