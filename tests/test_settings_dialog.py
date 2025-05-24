# g:\vscodeGit\ImageManager\tests\test_settings_dialog.py
import pytest
import json # Added import
from PyQt6.QtWidgets import QApplication, QWidget, QDialog # Added QDialog

import sys
import os
# Ensure src directory is in Python path for imports
from unittest.mock import patch # ★★★ patch をインポート ★★★
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPainter, QColor, QPaintEvent # Added QPaintEvent for paintEvent test

# Assuming src is in PYTHONPATH or tests are run from project root
from src.settings_dialog import ThumbnailSizePreviewWidget, SettingsDialog, PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM
# FIX: Import WC_FORMAT_HASH_COMMENT and other constants
from src.constants import THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU, WC_FORMAT_HASH_COMMENT, DELETE_EMPTY_FOLDERS_ENABLED, INITIAL_SORT_ORDER_ON_FOLDER_SELECT, SORT_BY_LOAD_ORDER_ALWAYS, SORT_BY_LAST_SELECTED


# Fixture to create a QApplication instance for tests that need it
@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

class TestThumbnailSizePreviewWidget:
    def test_initialization(self, qt_app):
        widget = ThumbnailSizePreviewWidget()
        assert widget._size == 96 # Default size
        # Check minimum size based on its internal calculation
        expected_min_width = 3 * 96 + 2 * 5 + 40 # 288 + 10 + 40 = 338
        expected_min_height = 200 + 40 # 240
        assert widget.minimumSize() == QSize(expected_min_width, expected_min_height)
        assert widget.sizeHint() == QSize(expected_min_width, expected_min_height)

    def test_set_size(self, qt_app, mocker):
        widget = ThumbnailSizePreviewWidget()
        mock_update = mocker.patch.object(widget, 'update')
        widget.set_size(128)
        assert widget._size == 128
        mock_update.assert_called_once()

    @pytest.mark.parametrize("size, expected_rect_count", [
        (96, 3),
        (128, 2),
        (200, 1),
        (50, 1) # Test with a non-standard size
    ])
    def test_paint_event_rect_counts(self, qt_app, mocker, size, expected_rect_count):
        widget = ThumbnailSizePreviewWidget()
        widget.set_size(size)
        
        # Mock QPainter methods
        # mock_painter = mocker.MagicMock(spec=QPainter) # This mock is not used directly

        # To make QPainter(self) use a mock, we can patch QPainter itself.
        # The QPainter instance is created inside paintEvent.
        # We need to ensure that when `QPainter(self)` is called, it uses our mock.
        mock_painter_instance = mocker.MagicMock(spec=QPainter)
        mocker.patch('src.settings_dialog.QPainter', return_value=mock_painter_instance)

        # Create a dummy QPaintEvent
        from PyQt6.QtCore import QRect # QRect is already imported, but good to be explicit
        
        # Ensure widget has a size for paintEvent calculations
        widget.resize(widget.minimumSizeHint()) 
        
        # Call paintEvent directly
        widget.paintEvent(QPaintEvent(QRect(0,0,widget.width(), widget.height())))

        assert mock_painter_instance.drawRect.call_count == expected_rect_count
        
        # Verify text drawn
        expected_text = f"{size} x {size} px"
        # Check if drawText was called with the expected text.
        called_with_expected_text = False
        for call_args in mock_painter_instance.drawText.call_args_list:
            # drawText has several overloads. Check if any string argument contains the expected text.
            if any(isinstance(arg, str) and expected_text in arg for arg in call_args.args):
                called_with_expected_text = True
                break
        assert called_with_expected_text, f"drawText not called with '{expected_text}'"


class TestSettingsDialog:
    # Dummy available sizes for testing the dialog
    AVAILABLE_SIZES = [96, 128, 200]
    DEFAULT_THUMBNAIL_SIZE = 128
    DEFAULT_PREVIEW_MODE = PREVIEW_MODE_FIT
    DEFAULT_RIGHT_CLICK_ACTION = RIGHT_CLICK_ACTION_METADATA # Default for tests
    DEFAULT_DELETE_EMPTY_FOLDERS = True # ★★★ 追加: デフォルト値を定義 ★★★
    DEFAULT_INITIAL_FOLDER_SORT = SORT_BY_LAST_SELECTED # ★★★ 追加: デフォルト値を定義 ★★★

    @pytest.fixture
    def dialog(self, qt_app, mocker):
        # FIX: Mock _load_settings_for_dialog_display instead of _load_preview_mode_setting
        mocker.patch.object(SettingsDialog, '_load_settings_for_dialog_display', 
                            return_value={"image_preview_mode": self.DEFAULT_PREVIEW_MODE})
        
        dialog_instance = SettingsDialog(
            current_thumbnail_size=self.DEFAULT_THUMBNAIL_SIZE,
            available_thumbnail_sizes=self.AVAILABLE_SIZES,
            current_preview_mode=self.DEFAULT_PREVIEW_MODE,
            current_right_click_action=self.DEFAULT_RIGHT_CLICK_ACTION, # Pass new arg
            # FIX: Add current_wc_comment_format argument
            current_wc_comment_format=WC_FORMAT_HASH_COMMENT, # Use a default value from constants
            current_delete_empty_folders_setting=self.DEFAULT_DELETE_EMPTY_FOLDERS, # ★★★ 追加 ★★★
            current_initial_folder_sort_setting=self.DEFAULT_INITIAL_FOLDER_SORT # ★★★ 追加 ★★★
        )
        return dialog_instance

    def test_dialog_initialization(self, dialog):
        assert dialog.windowTitle() == "設定"
        assert dialog.initial_thumbnail_size == self.DEFAULT_THUMBNAIL_SIZE
        assert dialog.available_thumbnail_sizes == self.AVAILABLE_SIZES
        assert dialog.initial_preview_mode == self.DEFAULT_PREVIEW_MODE
        assert dialog.initial_right_click_action == self.DEFAULT_RIGHT_CLICK_ACTION
        # FIX: Add assertion for initial_wc_comment_format
        assert dialog.initial_folder_sort_setting == self.DEFAULT_INITIAL_FOLDER_SORT # ★★★ 追加 ★★★
        assert dialog.initial_delete_empty_folders_setting == self.DEFAULT_DELETE_EMPTY_FOLDERS # ★★★ 追加 ★★★
        assert dialog.initial_wc_comment_format == WC_FORMAT_HASH_COMMENT # Check if the passed value is stored

        # Check slider initialization
        assert dialog.thumbnail_size_slider.minimum() == 0
        assert dialog.thumbnail_size_slider.maximum() == len(self.AVAILABLE_SIZES) - 1
        # Use try-except as index() might raise ValueError if default size is not in available sizes
        try:
            expected_slider_value = self.AVAILABLE_SIZES.index(self.DEFAULT_THUMBNAIL_SIZE)
            assert dialog.thumbnail_size_slider.value() == expected_slider_value
        except ValueError:
            pytest.fail(f"Default thumbnail size {self.DEFAULT_THUMBNAIL_SIZE} not found in available sizes {self.AVAILABLE_SIZES}")


        # Check radio button initialization
        if self.DEFAULT_PREVIEW_MODE == PREVIEW_MODE_FIT:
            assert dialog.fit_mode_radio.isChecked()
            assert not dialog.original_zoom_mode_radio.isChecked()
        else:
            assert not dialog.fit_mode_radio.isChecked()
            assert dialog.original_zoom_mode_radio.isChecked()
        
        # Check preview widget initialization
        assert dialog.thumbnail_preview_widget._size == self.DEFAULT_THUMBNAIL_SIZE
        assert dialog.thumbnail_size_label.text() == f"選択中: {self.DEFAULT_THUMBNAIL_SIZE}px"

        # Check right-click action radio button initialization
        assert dialog.metadata_action_radio is not None
        assert dialog.menu_action_radio is not None
        assert dialog.right_click_action_button_group is not None
        if self.DEFAULT_RIGHT_CLICK_ACTION == RIGHT_CLICK_ACTION_METADATA:
            assert dialog.metadata_action_radio.isChecked()
            assert not dialog.menu_action_radio.isChecked()
        else: # RIGHT_CLICK_ACTION_MENU
            assert not dialog.metadata_action_radio.isChecked()
            assert dialog.menu_action_radio.isChecked()

        # FIX: Add WC Creator comment format combo box initialization check
        assert dialog.wc_comment_format_combo is not None
        # Check that the correct item is selected based on initial_wc_comment_format
        expected_combo_index = dialog.wc_comment_format_combo.findData(dialog.initial_wc_comment_format)
        assert dialog.wc_comment_format_combo.currentIndex() == expected_combo_index

        # ★★★ 追加: delete_empty_folders_checkbox の初期化チェック ★★★
        assert dialog.delete_empty_folders_checkbox is not None
        assert dialog.delete_empty_folders_checkbox.isChecked() == self.DEFAULT_DELETE_EMPTY_FOLDERS

        # ★★★ 追加: initial_folder_sort radio buttons の初期化チェック ★★★
        assert dialog.sort_load_order_radio is not None
        assert dialog.sort_last_selected_radio is not None
        if self.DEFAULT_INITIAL_FOLDER_SORT == SORT_BY_LOAD_ORDER_ALWAYS:
            assert dialog.sort_load_order_radio.isChecked()
        else: # SORT_BY_LAST_SELECTED
            assert dialog.sort_last_selected_radio.isChecked()

    def test_thumbnail_slider_changes_preview(self, dialog, mocker):
        mock_preview_set_size = mocker.patch.object(dialog.thumbnail_preview_widget, 'set_size')
        
        # Simulate changing slider to the last available size (200px)
        target_size_index = len(self.AVAILABLE_SIZES) - 1
        target_size = self.AVAILABLE_SIZES[target_size_index]
        
        dialog.thumbnail_size_slider.setValue(target_size_index) # This should trigger valueChanged signal

        assert dialog.thumbnail_size_label.text() == f"選択中: {target_size}px"
        mock_preview_set_size.assert_called_with(target_size)
        assert dialog.current_selected_thumbnail_size == target_size

    def test_get_selected_thumbnail_size(self, dialog):
        target_size_index = 0 # First size (96px)
        target_size = self.AVAILABLE_SIZES[target_size_index]
        dialog.thumbnail_size_slider.setValue(target_size_index)
        assert dialog.get_selected_thumbnail_size() == target_size

    def test_get_selected_preview_mode(self, dialog):
        dialog.original_zoom_mode_radio.setChecked(True)
        assert dialog.get_selected_preview_mode() == PREVIEW_MODE_ORIGINAL_ZOOM

        dialog.fit_mode_radio.setChecked(True)
        assert dialog.get_selected_preview_mode() == PREVIEW_MODE_FIT

    def test_get_selected_right_click_action(self, dialog):
        # Select "メタデータを表示"
        dialog.metadata_action_radio.setChecked(True)
        # QButtonGroup should handle exclusivity, but for robustness:
        dialog.menu_action_radio.setChecked(False) 
        assert dialog.get_selected_right_click_action() == RIGHT_CLICK_ACTION_METADATA

        # Select "メニューを表示"
        dialog.menu_action_radio.setChecked(True)
        dialog.metadata_action_radio.setChecked(False)
        assert dialog.get_selected_right_click_action() == RIGHT_CLICK_ACTION_MENU
        
    # FIX: Add test for get_selected_wc_comment_format
    def test_get_selected_wc_comment_format(self, dialog):
        # Select the second item (assuming it's BRACKET_COMMENT)
        dialog.wc_comment_format_combo.setCurrentIndex(1)
        assert dialog.get_selected_wc_comment_format() == dialog.wc_comment_format_combo.itemData(1)

        # Select the first item (assuming it's HASH_COMMENT)
        dialog.wc_comment_format_combo.setCurrentIndex(0)
        assert dialog.get_selected_wc_comment_format() == dialog.wc_comment_format_combo.itemData(0)

    # ★★★ 追加: get_selected_delete_empty_folders_setting のテスト ★★★
    def test_get_selected_delete_empty_folders_setting(self, dialog):
        dialog.delete_empty_folders_checkbox.setChecked(True)
        assert dialog.get_selected_delete_empty_folders_setting() is True

        dialog.delete_empty_folders_checkbox.setChecked(False)
        assert dialog.get_selected_delete_empty_folders_setting() is False

    # ★★★ 追加: get_selected_initial_folder_sort_setting のテスト ★★★
    def test_get_selected_initial_folder_sort_setting(self, dialog):
        dialog.sort_load_order_radio.setChecked(True)
        assert dialog.get_selected_initial_folder_sort_setting() == SORT_BY_LOAD_ORDER_ALWAYS

        dialog.sort_last_selected_radio.setChecked(True)
        assert dialog.get_selected_initial_folder_sort_setting() == SORT_BY_LAST_SELECTED


    def test_accept_dialog(self, dialog, mocker):
        mock_super_accept = mocker.patch.object(QDialog, 'accept') # Mock QDialog.accept
        # _save_dialog_specific_settings was removed from SettingsDialog.accept
        # mock_save_specific = mocker.patch.object(dialog, '_save_dialog_specific_settings', return_value=True)

        dialog.accept()

        # mock_save_specific.assert_called_once() # Removed
        mock_super_accept.assert_called_once() # Ensure dialog's accept is called

    # ★★★ 追加: DialogManagerが設定を保存する際のダイアログの値取得を模倣するテスト ★★★
    @patch('PyQt6.QtWidgets.QDialog.accept') # QDialog.accept() をモック化
    def test_dialog_returns_correct_values_on_accept(self, mock_qdialog_accept, dialog, tmp_path):
        """Test that dialog returns correct values via getters when accepted, simulating DialogManager."""
        # Simulate changing settings in the dialog
        new_thumb_size_index = 0 # 96px
        new_thumb_size = self.AVAILABLE_SIZES[new_thumb_size_index]
        dialog.thumbnail_size_slider.setValue(new_thumb_size_index)

        dialog.original_zoom_mode_radio.setChecked(True)
        dialog.menu_action_radio.setChecked(True)
        dialog.wc_comment_format_combo.setCurrentIndex(1) # Assuming index 1 is different
        dialog.delete_empty_folders_checkbox.setChecked(False)
        dialog.sort_load_order_radio.setChecked(True) # Change to "always load order"

        # Simulate DialogManager calling accept (which we've mocked to do nothing for QDialog itself)
        # and then retrieving values
        
        # These would be called by DialogManager after dialog.exec() == True
        retrieved_thumb_size = dialog.get_selected_thumbnail_size()
        retrieved_preview_mode = dialog.get_selected_preview_mode()
        retrieved_right_click_action = dialog.get_selected_right_click_action()
        retrieved_wc_format = dialog.get_selected_wc_comment_format()
        retrieved_delete_empty = dialog.get_selected_delete_empty_folders_setting()
        retrieved_initial_sort = dialog.get_selected_initial_folder_sort_setting()

        assert retrieved_thumb_size == new_thumb_size
        assert retrieved_preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM
        assert retrieved_right_click_action == RIGHT_CLICK_ACTION_MENU
        assert retrieved_wc_format == dialog.wc_comment_format_combo.itemData(1)
        assert retrieved_delete_empty is False
        assert retrieved_initial_sort == SORT_BY_LOAD_ORDER_ALWAYS


    # _save_dialog_specific_settings was removed from SettingsDialog, so this test is no longer applicable
    # def test_save_dialog_specific_settings(self, dialog):
    #     # Test saving PREVIEW_MODE_ORIGINAL_ZOOM
    #     dialog.original_zoom_mode_radio.setChecked(True)
    #     dialog.fit_mode_radio.setChecked(False) # Ensure other is not checked
    #     dialog._save_dialog_specific_settings()
    #     assert dialog.current_settings["image_preview_mode"] == PREVIEW_MODE_ORIGINAL_ZOOM

    #     # Test saving PREVIEW_MODE_FIT
    #     dialog.fit_mode_radio.setChecked(True)
    #     dialog.original_zoom_mode_radio.setChecked(False)
    #     dialog._save_dialog_specific_settings()
    #     assert dialog.current_settings["image_preview_mode"] == PREVIEW_MODE_FIT

    # Test _load_settings_for_dialog_display with file operations (requires more setup or finer mocking)
    def test_load_settings_for_dialog_display_file_exists(self, qt_app, tmp_path, mocker):
        # This test will not use the dialog fixture to avoid its _load_settings_for_dialog_display mock
        settings_file = tmp_path / "app_settings.json"
        
        # Case 1: File exists with the setting
        with open(settings_file, 'w') as f:
            json.dump({"image_preview_mode": PREVIEW_MODE_ORIGINAL_ZOOM, "other_value": "test"}, f)
        
        mocker.patch('src.settings_dialog.APP_SETTINGS_FILE', str(settings_file))
        # FIX: Add current_wc_comment_format argument
        dialog_instance = SettingsDialog(
            current_thumbnail_size=self.DEFAULT_THUMBNAIL_SIZE,
            available_thumbnail_sizes=self.AVAILABLE_SIZES,
            current_preview_mode=self.DEFAULT_PREVIEW_MODE,
            current_right_click_action=self.DEFAULT_RIGHT_CLICK_ACTION,
            current_wc_comment_format=WC_FORMAT_HASH_COMMENT,
            current_delete_empty_folders_setting=self.DEFAULT_DELETE_EMPTY_FOLDERS, # ★★★ 追加 ★★★
            current_initial_folder_sort_setting=self.DEFAULT_INITIAL_FOLDER_SORT # ★★★ 追加 ★★★
        )
        assert dialog_instance.current_settings["image_preview_mode"] == PREVIEW_MODE_ORIGINAL_ZOOM
        assert dialog_instance.initial_preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM # Check if initial_preview_mode is also set

        # Case 2: File exists but setting is missing (should default)
        with open(settings_file, 'w') as f:
            json.dump({"other_value": "test"}, f)
        # FIX: Add current_wc_comment_format argument
        dialog_instance_2 = SettingsDialog(
            current_thumbnail_size=self.DEFAULT_THUMBNAIL_SIZE,
            available_thumbnail_sizes=self.AVAILABLE_SIZES,
            current_preview_mode=self.DEFAULT_PREVIEW_MODE,
            current_right_click_action=self.DEFAULT_RIGHT_CLICK_ACTION,
            current_wc_comment_format=WC_FORMAT_HASH_COMMENT,
            current_delete_empty_folders_setting=self.DEFAULT_DELETE_EMPTY_FOLDERS, # ★★★ 追加 ★★★
            current_initial_folder_sort_setting=self.DEFAULT_INITIAL_FOLDER_SORT # ★★★ 追加 ★★★
        )
        assert dialog_instance_2.current_settings["image_preview_mode"] == PREVIEW_MODE_FIT
        assert dialog_instance_2.initial_preview_mode == PREVIEW_MODE_FIT


    def test_load_settings_for_dialog_display_file_not_exists(self, qt_app, tmp_path, mocker):
        non_existent_file = tmp_path / "non_existent_settings.json"
        mocker.patch('src.settings_dialog.APP_SETTINGS_FILE', str(non_existent_file))
        
        # FIX: Add current_wc_comment_format argument
        dialog_instance = SettingsDialog(
            current_thumbnail_size=self.DEFAULT_THUMBNAIL_SIZE,
            available_thumbnail_sizes=self.AVAILABLE_SIZES,
            current_preview_mode=self.DEFAULT_PREVIEW_MODE,
            current_right_click_action=self.DEFAULT_RIGHT_CLICK_ACTION,
            current_wc_comment_format=WC_FORMAT_HASH_COMMENT,
            current_delete_empty_folders_setting=self.DEFAULT_DELETE_EMPTY_FOLDERS, # ★★★ 追加 ★★★
            current_initial_folder_sort_setting=self.DEFAULT_INITIAL_FOLDER_SORT # ★★★ 追加 ★★★
        )
        assert dialog_instance.current_settings["image_preview_mode"] == PREVIEW_MODE_FIT
        assert dialog_instance.initial_preview_mode == PREVIEW_MODE_FIT
