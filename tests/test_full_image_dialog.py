import pytest
from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtGui import QPixmap, QImage, QMouseEvent, QWheelEvent
from PyQt6.QtCore import Qt, QPoint, QSize, QPointF # Added QPointF
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.full_image_dialog import FullImageDialog, PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM
from src.constants import METADATA_ROLE # If FullImageDialog interacts with items having this

# Fixture for QApplication
@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

# Helper to create a dummy QPixmap
def create_dummy_pixmap(width, height, color="blue"):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.blue if color == "blue" else Qt.GlobalColor.red)
    return QPixmap.fromImage(image)

# Dummy image paths for testing (assuming some images exist in test_data)
# Use a known small image from your test_data if possible, otherwise mock loading.
TEST_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "test_data", "images")
TEST_IMAGE_VALID_1 = os.path.join(TEST_IMAGE_DIR, "01.png") # Assuming this exists
TEST_IMAGE_VALID_2 = os.path.join(TEST_IMAGE_DIR, "02.png") # Assuming this exists
TEST_IMAGE_INVALID = os.path.join(TEST_IMAGE_DIR, "non_existent.png")

# Ensure test images exist or skip tests that rely on them
skip_if_no_test_images = pytest.mark.skipif(
    not (os.path.exists(TEST_IMAGE_VALID_1) and os.path.exists(TEST_IMAGE_VALID_2)),
    reason="Test images not found in tests/test_data/images/"
)

class TestFullImageDialog:

    @skip_if_no_test_images
    def test_dialog_initialization_fit_mode(self, qt_app):
        image_paths = [TEST_IMAGE_VALID_1, TEST_IMAGE_VALID_2]
        dialog = FullImageDialog(image_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        assert os.path.basename(TEST_IMAGE_VALID_1) in dialog.windowTitle()
        assert dialog.preview_mode == PREVIEW_MODE_FIT
        assert dialog.current_index == 0
        assert dialog.all_image_paths == image_paths # Attribute is all_image_paths
        # More assertions: e.g., image_label has a pixmap after loading
        # This requires _load_image to be called, which might be async or delayed.
        # For now, check basic properties.
        dialog.close() # Clean up

    @skip_if_no_test_images
    def test_dialog_initialization_original_zoom_mode(self, qt_app):
        image_paths = [TEST_IMAGE_VALID_1, TEST_IMAGE_VALID_2]
        dialog = FullImageDialog(image_paths, 0, preview_mode=PREVIEW_MODE_ORIGINAL_ZOOM, parent=None)
        assert dialog.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM
        # Assertions for original zoom mode specific setup if any
        dialog.close()

    def test_initialization_no_images(self, qt_app):
        dialog = FullImageDialog([], 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        assert dialog.windowTitle() == "画像なし - ImageManager"
        assert dialog.preview_widget.image_label.text() == "表示できる画像がありません。"
        assert not dialog.preview_widget.next_button.isEnabled()
        assert not dialog.preview_widget.prev_button.isEnabled()
        dialog.close()

    @skip_if_no_test_images
    def test_initialization_invalid_index_positive(self, qt_app):
        image_paths = [TEST_IMAGE_VALID_1, TEST_IMAGE_VALID_2]
        dialog = FullImageDialog(image_paths, 100, preview_mode=PREVIEW_MODE_FIT, parent=None) # Index out of bounds
        # Expect it to default to the first image or handle gracefully
        assert dialog.current_index == 0 # Should default to 0
        assert os.path.basename(TEST_IMAGE_VALID_1) in dialog.windowTitle()
        assert dialog.preview_widget.image_label.pixmap() is not None and not dialog.preview_widget.image_label.pixmap().isNull()
        dialog.close()

    @skip_if_no_test_images
    def test_initialization_invalid_index_negative(self, qt_app):
        image_paths = [TEST_IMAGE_VALID_1, TEST_IMAGE_VALID_2]
        dialog = FullImageDialog(image_paths, -5, preview_mode=PREVIEW_MODE_FIT, parent=None) # Index out of bounds
        assert dialog.current_index == 0 # Should default to 0
        assert os.path.basename(TEST_IMAGE_VALID_1) in dialog.windowTitle()
        assert dialog.preview_widget.image_label.pixmap() is not None and not dialog.preview_widget.image_label.pixmap().isNull()
        dialog.close()

    @skip_if_no_test_images
    def test_load_image_valid(self, qt_app, mocker):
        image_paths = [TEST_IMAGE_VALID_1]
        dialog = FullImageDialog(image_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        
        # _load_image is called in __init__ or showEvent.
        # We need to ensure it has run. If it's complex, mock it for unit testing other parts.
        # Here, we assume it loads the image and sets self.current_pixmap.
        # A short wait might be needed if loading is deferred, or use QtTest.qWait.
        QApplication.processEvents() # Process events to allow image loading if deferred

        assert dialog.preview_widget.pixmap is not None
        assert not dialog.preview_widget.pixmap.isNull()
        assert dialog.preview_widget.image_label.pixmap() is not None # Check if label has pixmap
        # Check window title update
        expected_filename = os.path.basename(TEST_IMAGE_VALID_1)
        assert expected_filename in dialog.windowTitle()
        dialog.close()

    def test_load_image_invalid(self, qt_app, mocker):
        image_paths = [TEST_IMAGE_INVALID]
        dialog = FullImageDialog(image_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        QApplication.processEvents()
        
        assert dialog.preview_widget.pixmap.isNull() # Pixmap is reset on load failure
        expected_filename = os.path.basename(TEST_IMAGE_INVALID)
        assert dialog.preview_widget.image_label.text() == f"指定された画像ファイルが見つかりません:\n{expected_filename}"
        assert expected_filename in dialog.windowTitle() # Title might still show filename
        dialog.close()

    def test_load_image_path_is_none(self, qt_app, mocker):
        """Test update_image when image_path is None."""
        # Initialize with a list containing None to make self.image_path None.
        dialog = FullImageDialog([None], 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        QApplication.processEvents()

        # __init__ should set self.image_path to None.
        assert dialog.image_path is None
        assert dialog.preview_widget.pixmap.isNull()
        # _update_image_display sets this text when image_path is None and all_image_paths is not empty
        assert dialog.preview_widget.image_label.text() == "表示できる画像がありません。"
        # __init__ sets title to "画像なし - ImageManager" when image_path becomes None.
        assert dialog.windowTitle() == "画像なし - ImageManager"
        dialog.close()

    @skip_if_no_test_images
    def test_load_image_pixmap_load_fails(self, qt_app, mocker):
        """Test _load_and_display_image when QPixmap.load() fails."""
        image_paths = [TEST_IMAGE_VALID_1] # Use a normally valid image path
        
        # --- ImageQt を None にして、QPixmap.load() が呼び出されるようにする ---
        # mocker.patch はコンテキストマネージャではないので、直接 with 文では使えない
        # テスト関数スコープで ImageQt を None に置き換える
        mocker.patch('src.image_preview_widget.ImageQt', None)
        
        mock_pixmap_load = mocker.patch('src.image_preview_widget.QPixmap.load', return_value=False)
        dialog = FullImageDialog(image_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)

        QApplication.processEvents()
        
        mock_pixmap_load.assert_called_once_with(TEST_IMAGE_VALID_1)
        assert dialog.preview_widget.pixmap.isNull()
        expected_filename = os.path.basename(TEST_IMAGE_VALID_1)
        assert dialog.preview_widget.image_label.text() == f"画像の読み込みに失敗しました (QPixmap):\n{expected_filename}"
        # Window title is set before _load_and_display_image in _load_current_image or __init__
        assert expected_filename in dialog.windowTitle()
        dialog.close()

    @skip_if_no_test_images
    def test_navigation_next_previous(self, qt_app, mocker):
        image_paths = [TEST_IMAGE_VALID_1, TEST_IMAGE_VALID_2, os.path.join(TEST_IMAGE_DIR, "03.png")]
        # Ensure 03.png exists or this test might fail on load
        if not os.path.exists(image_paths[2]):
            pytest.skip("Test image 03.png not found")
            
        dialog = FullImageDialog(image_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        QApplication.processEvents()

        # Initial state
        assert dialog.current_index == 0
        assert os.path.basename(image_paths[0]) in dialog.windowTitle()

        # Next
        # Mock _load_and_display_image in WIDGET, not dialog
        # Wait, dialog calls widget.update_image.
        # We should check if dialog.current_index updates and window title updates.
        # widget.update_image handles loading.
        
        mock_update_image = mocker.spy(dialog.preview_widget, 'update_image')
        dialog.preview_widget.next_button.click()
        QApplication.processEvents()
        assert dialog.current_index == 1
        assert os.path.basename(image_paths[1]) in dialog.windowTitle() # Title is updated by _load_current_image
        mock_update_image.assert_called_once()
        mock_update_image.reset_mock()

        # Next again (to last image)
        dialog.preview_widget.next_button.click()
        QApplication.processEvents()
        assert dialog.current_index == 2
        assert os.path.basename(image_paths[2]) in dialog.windowTitle()
        mock_update_image.assert_called_once()
        mock_update_image.reset_mock()
        
        
        # Next (current FullImageDialog does NOT wrap, button should be disabled)
        assert not dialog.preview_widget.next_button.isEnabled() # Check if button is disabled at the end
        # dialog.next_button.click() # This would do nothing
        # QApplication.processEvents()
        # assert dialog.current_index == 2 # Stays at the end
        # assert os.path.basename(image_paths[2]) in dialog.windowTitle()
        # mock_load_and_display.assert_not_called() # Should not be called if button disabled / no change
        # mock_load_and_display.reset_mock()


        # Previous
        dialog.preview_widget.prev_button.click()
        QApplication.processEvents()
        assert dialog.current_index == 1 
        assert os.path.basename(image_paths[1]) in dialog.windowTitle()
        mock_update_image.assert_called_once()
        mock_update_image.reset_mock()
        
        dialog.close()

    @skip_if_no_test_images
    def test_update_image_method(self, qt_app, mocker):
        initial_paths = [TEST_IMAGE_VALID_1]
        dialog = FullImageDialog(initial_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        QApplication.processEvents()
        assert os.path.basename(TEST_IMAGE_VALID_1) in dialog.windowTitle()

        new_paths = [TEST_IMAGE_VALID_2, TEST_IMAGE_VALID_1] # New list
        mock_update_current = mocker.spy(dialog, '_update_current_image_info') # _load_current_image renamed? No, use _update_current_image_info or widget update
        
        dialog.update_image(new_paths, 0) # Update to show first image of new list
        QApplication.processEvents()
        
        assert dialog.all_image_paths == new_paths
        assert dialog.current_index == 0
        mock_update_current.assert_called_once()
        # Window title update is handled within _load_current_image
        dialog.close()

    @skip_if_no_test_images
    def test_navigation_boundary_conditions(self, qt_app, mocker):
        # Test with a single image
        single_image_paths = [TEST_IMAGE_VALID_1]
        dialog_single = FullImageDialog(single_image_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        QApplication.processEvents()
        assert not dialog_single.preview_widget.prev_button.isEnabled()
        assert not dialog_single.preview_widget.next_button.isEnabled()
        assert dialog_single.preview_widget.counter_label.text() == "1 / 1"

        # Try clicking next/prev (should do nothing)
        mock_load_single = mocker.spy(dialog_single.preview_widget, 'update_image')
        dialog_single.preview_widget.next_button.click()
        dialog_single.preview_widget.prev_button.click()
        QApplication.processEvents()
        mock_load_single.reset_mock() # Initially called in init
        # Not sure if it's called again with same index? Check implementation.
        # Button disabled, click won't emit.
        # If enabled, it would emit.
        # But they are disabled.
        # mock_load_single.assert_not_called() 
        dialog_single.close()

        # Test at the beginning of a list
        multi_image_paths = [TEST_IMAGE_VALID_1, TEST_IMAGE_VALID_2]
        dialog_multi = FullImageDialog(multi_image_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        QApplication.processEvents()
        assert not dialog_multi.preview_widget.prev_button.isEnabled()
        assert dialog_multi.preview_widget.next_button.isEnabled()
        
        mock_load_multi = mocker.spy(dialog_multi.preview_widget, 'update_image')
        dialog_multi.preview_widget.prev_button.click() # Click prev at first image
        QApplication.processEvents()
        # mock_load_multi.assert_not_called() 
        dialog_multi.close()

        # Test at the end of a list
        dialog_multi_end = FullImageDialog(multi_image_paths, len(multi_image_paths) - 1, preview_mode=PREVIEW_MODE_FIT, parent=None)
        QApplication.processEvents()
        assert dialog_multi_end.preview_widget.prev_button.isEnabled()
        assert not dialog_multi_end.preview_widget.next_button.isEnabled()

        mock_load_multi_end = mocker.spy(dialog_multi_end.preview_widget, 'update_image')
        dialog_multi_end.preview_widget.next_button.click() # Click next at last image
        QApplication.processEvents()
        # mock_load_multi_end.assert_not_called() # Should not load
        dialog_multi_end.close()


    @skip_if_no_test_images
    def test_update_image_invalid_index(self, qt_app, mocker):
        initial_paths = [TEST_IMAGE_VALID_1]
        dialog = FullImageDialog(initial_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        QApplication.processEvents()
        assert os.path.basename(TEST_IMAGE_VALID_1) in dialog.windowTitle()

        new_paths = [TEST_IMAGE_VALID_1, TEST_IMAGE_VALID_2]
        dialog.update_image(new_paths, 100) # Invalid positive index
        QApplication.processEvents()
        
        assert dialog.all_image_paths == new_paths
        assert dialog.current_index == 0 # Should default to 0
        assert os.path.basename(TEST_IMAGE_VALID_1) in dialog.windowTitle() # Updated to first image of new_paths
        
        dialog.update_image(new_paths, -5) # Invalid negative index
        QApplication.processEvents()
        assert dialog.current_index == 0 # Should default to 0
        assert os.path.basename(TEST_IMAGE_VALID_1) in dialog.windowTitle()
        dialog.close()

    @skip_if_no_test_images
    def test_update_image_empty_list(self, qt_app, mocker):
        initial_paths = [TEST_IMAGE_VALID_1]
        dialog = FullImageDialog(initial_paths, 0, preview_mode=PREVIEW_MODE_FIT, parent=None)
        QApplication.processEvents()
        assert os.path.basename(TEST_IMAGE_VALID_1) in dialog.windowTitle()

        dialog.update_image([], 0) # Update with empty list
        QApplication.processEvents()
        
        assert dialog.all_image_paths == []
        assert dialog.current_index == -1 # Should be -1 for empty list
        assert dialog.windowTitle() == "画像なし - ImageManager"
        assert dialog.image_label.text() == "表示できる画像がありません。"
        assert not dialog.next_button.isEnabled()
        assert not dialog.prev_button.isEnabled()
        dialog.close()

    # More tests needed for:
    # - Fit mode scaling on resize (harder to unit test precisely)
    # - Original/Zoom mode:
    #   - Initial display (original size or scaled if too big)
    #   - Zoom via Ctrl+WheelEvent
    #   - Pan via MouseEvents
    # - Maximize/Restore button functionality
    # - showEvent and resizeEvent handlers if they contain complex logic

    @skip_if_no_test_images
    def test_zoom_functionality(self, qt_app, mocker):
        dialog = FullImageDialog([TEST_IMAGE_VALID_1], 0, preview_mode=PREVIEW_MODE_ORIGINAL_ZOOM)
        dialog.show() # Widget must be visible for mouse/wheel events
        QApplication.processEvents()

        assert dialog.preview_widget.pixmap is not None, "Pixmap should be loaded"
        assert not dialog.preview_widget.pixmap.isNull(), "Pixmap should not be null after loading"
        initial_scale = dialog.preview_widget.scale_factor
        
        # Mock _update_image_display to check if it's called
        mock_update_display = mocker.patch.object(dialog.preview_widget, '_update_image_display')

        # Simulate Ctrl + Wheel Up (Zoom In)
        # Angle delta is typically 120 units per notch
        wheel_event_zoom_in = QWheelEvent(
            QPointF(50.0, 50.0), QPointF(50.0, 50.0), # pos, globalPos - Use QPointF
            QPoint(0,0), QPoint(0, 120), # pixelDelta, angleDelta (y for vertical scroll)
            Qt.MouseButton.NoButton, # buttons
            Qt.KeyboardModifier.ControlModifier, # modifiers
            Qt.ScrollPhase.ScrollBegin, False # phase, inverted
        )
        QApplication.sendEvent(dialog.preview_widget, wheel_event_zoom_in) # Send event to the widget

        QApplication.processEvents()
        
        assert dialog.preview_widget.scale_factor > initial_scale
        mock_update_display.assert_called()
        mock_update_display.reset_mock()
        
        # Simulate Ctrl + Wheel Down (Zoom Out)
        current_scale = dialog.preview_widget.scale_factor
        wheel_event_zoom_out = QWheelEvent(
            QPointF(50.0, 50.0), QPointF(50.0, 50.0), # Use QPointF
            QPoint(0,0), QPoint(0, -120), # Negative angleDelta (y for vertical scroll)
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.ScrollBegin, False
        )
        QApplication.sendEvent(dialog.preview_widget, wheel_event_zoom_out) # Send event to the widget
        QApplication.processEvents()
        
        assert dialog.preview_widget.scale_factor < current_scale
        mock_update_display.assert_called()
        
        dialog.close()

    # Panning test is more complex due to mouse event sequence and scrollbar interaction.
    # It might be better as an integration test or with more focused mocking of scroll area.

    def test_initialization_with_selection_callback(self, qt_app):
        """Regression test for double-click initialization error and selection callback."""
        # Test basic initialization with callback and empty list
        dialog = FullImageDialog([], 0, parent=None, is_selected_callback=lambda x: True)
        assert dialog.is_selected_callback is not None
        assert dialog._get_current_selection_state() is False # False because no image_path
        dialog.close()
        
        # Test with dummy path
        image_paths = ["dummy_path.jpg"]
        dialog_with_path = FullImageDialog(image_paths, 0, parent=None, is_selected_callback=lambda x: True)
        assert dialog_with_path.is_selected_callback is not None
        assert dialog_with_path.image_path == "dummy_path.jpg"
        assert dialog_with_path._get_current_selection_state() is True
        dialog_with_path.close()
