import pytest
import json # Added import
from PyQt6.QtWidgets import QApplication, QWidget, QDialog # Added QDialog
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPainter, QColor

# Assuming src is in PYTHONPATH or tests are run from project root
from src.settings_dialog import ThumbnailSizePreviewWidget, SettingsDialog, PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM

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
        mock_painter = mocker.MagicMock(spec=QPainter)
        
        # To properly mock painter.drawRect, we need to ensure QPainter(widget) works.
        # This is tricky without a full widget lifecycle.
        # For simplicity, we'll assume the painter is correctly passed and focus on logic.
        # We can't directly mock QPainter constructor easily with mocker.
        # Instead, we can patch methods on an instance if we could get it.

        # A common way to test paintEvent is to render the widget to a QPixmap and inspect it,
        # but that's more of an integration test. For unit test, mocking draw calls is preferred.
        # Let's try to patch QPainter's methods globally for the duration of this test.
        
        # mocker.patch('PyQt6.QtGui.QPainter.drawRect') # Will be handled by mock_qpainter_instance
        # mocker.patch('PyQt6.QtGui.QPainter.drawText')
        # mocker.patch('PyQt6.QtGui.QPainter.setPen')
        # mocker.patch('PyQt6.QtGui.QPainter.setBrush')
        # mocker.patch('PyQt6.QtGui.QPainter.setRenderHint')

        # Create a dummy QPaintEvent
        from PyQt6.QtGui import QPaintEvent
        from PyQt6.QtCore import QRect
        
        # Ensure widget has a size for paintEvent calculations
        widget.resize(widget.minimumSizeHint()) 
        
        # Call paintEvent directly
        # QPainter needs to be constructed within paintEvent, so we can't pass a mock directly.
        # We will rely on the global patches of QPainter methods.
        
        # This is a simplified way to invoke paintEvent for testing logic.
        # In a real scenario, the event loop would handle this.
        # We need to ensure QPainter(self) inside paintEvent uses the patched methods.
        
        # To make QPainter(self) use a mock, we can patch QPainter itself.
        # The QPainter instance is created inside paintEvent.
        # We need to ensure that when `QPainter(self)` is called, it uses our mock.
        mock_painter_instance = mocker.MagicMock(spec=QPainter)
        mocker.patch('src.settings_dialog.QPainter', return_value=mock_painter_instance)


        widget.paintEvent(QPaintEvent(QRect(0,0,widget.width(), widget.height())))

        assert mock_painter_instance.drawRect.call_count == expected_rect_count
        
        # Verify text drawn
        expected_text = f"{size} x {size} px"
        # Check if drawText was called with the expected text.
        called_with_expected_text = False
        for call_args in mock_painter_instance.drawText.call_args_list:
            # args[1] is usually the text for painter.drawText(QRect, flags, text)
            # args[2] for painter.drawText(x, y, text)
            # args[0] for painter.drawText(QPointF, text)
            # Check all string arguments in the call
            if any(isinstance(arg, str) and expected_text in arg for arg in call_args.args):
                called_with_expected_text = True
                break
        assert called_with_expected_text, f"drawText not called with '{expected_text}'"


class TestSettingsDialog:
    # Dummy available sizes for testing the dialog
    AVAILABLE_SIZES = [96, 128, 200]
    DEFAULT_THUMBNAIL_SIZE = 128
    DEFAULT_PREVIEW_MODE = PREVIEW_MODE_FIT

    @pytest.fixture
    def dialog(self, qt_app, mocker):
        # Mock _load_preview_mode_setting to avoid file IO during most tests
        mocker.patch.object(SettingsDialog, '_load_preview_mode_setting', 
                            return_value={"image_preview_mode": self.DEFAULT_PREVIEW_MODE})
        
        dialog_instance = SettingsDialog(
            current_thumbnail_size=self.DEFAULT_THUMBNAIL_SIZE,
            available_thumbnail_sizes=self.AVAILABLE_SIZES,
            current_preview_mode=self.DEFAULT_PREVIEW_MODE
        )
        return dialog_instance

    def test_dialog_initialization(self, dialog):
        assert dialog.windowTitle() == "設定"
        assert dialog.initial_thumbnail_size == self.DEFAULT_THUMBNAIL_SIZE
        assert dialog.available_thumbnail_sizes == self.AVAILABLE_SIZES
        assert dialog.initial_preview_mode == self.DEFAULT_PREVIEW_MODE

        # Check slider initialization
        assert dialog.thumbnail_size_slider.minimum() == 0
        assert dialog.thumbnail_size_slider.maximum() == len(self.AVAILABLE_SIZES) - 1
        assert dialog.thumbnail_size_slider.value() == self.AVAILABLE_SIZES.index(self.DEFAULT_THUMBNAIL_SIZE)

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
        
    def test_accept_dialog(self, dialog, mocker):
        mock_super_accept = mocker.patch.object(QDialog, 'accept') # Mock QDialog.accept
        mock_save_specific = mocker.patch.object(dialog, '_save_dialog_specific_settings', return_value=True)

        dialog.accept()

        mock_save_specific.assert_called_once()
        mock_super_accept.assert_called_once() # Ensure dialog's accept is called

    def test_save_dialog_specific_settings(self, dialog):
        # Test saving PREVIEW_MODE_ORIGINAL_ZOOM
        dialog.original_zoom_mode_radio.setChecked(True)
        dialog.fit_mode_radio.setChecked(False) # Ensure other is not checked
        dialog._save_dialog_specific_settings()
        assert dialog.current_settings["image_preview_mode"] == PREVIEW_MODE_ORIGINAL_ZOOM

        # Test saving PREVIEW_MODE_FIT
        dialog.fit_mode_radio.setChecked(True)
        dialog.original_zoom_mode_radio.setChecked(False)
        dialog._save_dialog_specific_settings()
        assert dialog.current_settings["image_preview_mode"] == PREVIEW_MODE_FIT

    # Test _load_preview_mode_setting with file operations (requires more setup or finer mocking)
    def test_load_preview_mode_setting_file_exists(self, qt_app, tmp_path, mocker):
        # This test will not use the dialog fixture to avoid its _load_preview_mode_setting mock
        settings_file = tmp_path / "app_settings.json"
        
        # Case 1: File exists with the setting
        with open(settings_file, 'w') as f:
            json.dump({"image_preview_mode": PREVIEW_MODE_ORIGINAL_ZOOM, "other_value": "test"}, f)
        
        mocker.patch('src.settings_dialog.APP_SETTINGS_FILE', str(settings_file))
        dialog_instance = SettingsDialog(self.DEFAULT_THUMBNAIL_SIZE, self.AVAILABLE_SIZES, self.DEFAULT_PREVIEW_MODE)
        assert dialog_instance.current_settings["image_preview_mode"] == PREVIEW_MODE_ORIGINAL_ZOOM
        assert dialog_instance.initial_preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM # Check if initial_preview_mode is also set

        # Case 2: File exists but setting is missing (should default)
        with open(settings_file, 'w') as f:
            json.dump({"other_value": "test"}, f)
        dialog_instance_2 = SettingsDialog(self.DEFAULT_THUMBNAIL_SIZE, self.AVAILABLE_SIZES, self.DEFAULT_PREVIEW_MODE)
        assert dialog_instance_2.current_settings["image_preview_mode"] == PREVIEW_MODE_FIT
        assert dialog_instance_2.initial_preview_mode == PREVIEW_MODE_FIT


    def test_load_preview_mode_setting_file_not_exists(self, qt_app, tmp_path, mocker):
        non_existent_file = tmp_path / "non_existent_settings.json"
        mocker.patch('src.settings_dialog.APP_SETTINGS_FILE', str(non_existent_file))
        
        dialog_instance = SettingsDialog(self.DEFAULT_THUMBNAIL_SIZE, self.AVAILABLE_SIZES, self.DEFAULT_PREVIEW_MODE)
        assert dialog_instance.current_settings["image_preview_mode"] == PREVIEW_MODE_FIT
        assert dialog_instance.initial_preview_mode == PREVIEW_MODE_FIT
