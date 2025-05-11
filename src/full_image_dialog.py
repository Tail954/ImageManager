import logging
import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication, QSpacerItem, QSizePolicy
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QSize, QByteArray

logger = logging.getLogger(__name__)

# Define constants for preview modes at the module level if they are also used by MainWindow
PREVIEW_MODE_FIT = "fit"
PREVIEW_MODE_ORIGINAL_ZOOM = "original_zoom"

class FullImageDialog(QDialog):
    def __init__(self, image_path_list, current_index, preview_mode=PREVIEW_MODE_FIT, parent=None):
        super().__init__(parent)
        self.all_image_paths = image_path_list if image_path_list is not None else []
        self.current_index = current_index
        self.preview_mode = preview_mode
        self.scale_factor = 1.0 # For original_zoom mode
        self.pixmap = QPixmap()
        self.saved_geometry = None # For storing geometry before maximizing

        # Determine initial image_path and window title carefully
        if not self.all_image_paths:
            self.image_path = None
            self.current_index = -1 # Indicate invalid index
            logger.warning("FullImageDialog initialized with no image paths.")
            self.setWindowTitle("画像なし - ImageManager")
        elif not (0 <= self.current_index < len(self.all_image_paths)):
            logger.warning(f"FullImageDialog initialized with invalid current_index {self.current_index} for {len(self.all_image_paths)} images. Defaulting to first image or none.")
            self.current_index = 0 if self.all_image_paths else -1
            if self.current_index != -1:
                candidate_path = self.all_image_paths[self.current_index]
                if candidate_path is None or not isinstance(candidate_path, str):
                    logger.warning(f"Image path at index {self.current_index} is invalid (None or not a string): {candidate_path}. Treating as no image.")
                    self.image_path = None
                    self.setWindowTitle("画像なし - ImageManager")
                else:
                    self.image_path = candidate_path
                    try:
                        title_filename = os.path.basename(self.image_path)
                        self.setWindowTitle(f"{title_filename} - ImageManager")
                    except Exception as e:
                        logger.error(f"Error getting basename for title from '{self.image_path}': {e}")
                        self.setWindowTitle("エラー - ImageManager")
            else:
                self.image_path = None
                self.setWindowTitle("画像なし - ImageManager")
        else: # 0 <= self.current_index < len(self.all_image_paths)
            candidate_path = self.all_image_paths[self.current_index]
            if candidate_path is None or not isinstance(candidate_path, str):
                logger.warning(f"Image path at index {self.current_index} is invalid (None or not a string): {candidate_path}. Treating as no image.")
                self.image_path = None
                self.setWindowTitle("画像なし - ImageManager")
            else:
                self.image_path = candidate_path
                try:
                    title_filename = os.path.basename(self.image_path)
                    self.setWindowTitle(f"{title_filename} - ImageManager")
                except Exception as e:
                    logger.error(f"Error getting basename for title from '{self.image_path}': {e}")
                    self.setWindowTitle("エラー - ImageManager")

        self.setMinimumSize(400, 300)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        # layout.setContentsMargins(0,0,0,0) # Keep some margins for controls if needed, or set on specific layouts

        # Controls layout (for navigation and fullscreen button)
        self.controls_layout = QHBoxLayout() # Made it a member for potential future modifications
        
        self.prev_button = QPushButton("← Previous")
        self.prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_button.clicked.connect(self.show_previous_image)
        self.controls_layout.addWidget(self.prev_button)

        self.counter_label = QLabel("")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.controls_layout.addWidget(self.counter_label)

        self.next_button = QPushButton("Next →")
        self.next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_button.clicked.connect(self.show_next_image)
        self.controls_layout.addWidget(self.next_button)
        
        self.controls_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.fullscreen_button = QPushButton("□")
        self.fullscreen_button.setFixedSize(30, 30)
        self.fullscreen_button.setToolTip("最大化/元に戻す")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen_state)
        self.controls_layout.addWidget(self.fullscreen_button)
        
        main_layout.addLayout(self.controls_layout)

        # Image display area (QLabel or QScrollArea containing QLabel)
        self.image_label = QLabel(self) # This will be the widget inside scroll_area for original_zoom mode
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM:
            from PyQt6.QtWidgets import QScrollArea # Local import for clarity
            self.scroll_area = QScrollArea(self)
            self.scroll_area.setWidgetResizable(False) # Important for original size + zoom
            self.scroll_area.setWidget(self.image_label)
            self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
            main_layout.addWidget(self.scroll_area, 1)
        else: # PREVIEW_MODE_FIT (default)
            self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            main_layout.addWidget(self.image_label, 1)

        self.setLayout(main_layout)
        
        self._load_and_display_image() # This will also call _update_navigation_buttons
        self.resize(800, 600)

    def update_image(self, new_image_path_list, new_current_index):
        """Updates the image list and current index, then loads the image."""
        self.all_image_paths = new_image_path_list if new_image_path_list is not None else []
        self.current_index = new_current_index

        if not self.all_image_paths:
            self.image_path = None
            self.current_index = -1
            logger.warning("update_image called with no image paths.")
            self.setWindowTitle("画像なし - ImageManager")
        elif not (0 <= self.current_index < len(self.all_image_paths)):
            logger.warning(f"update_image called with invalid current_index {self.current_index} for {len(self.all_image_paths)} images. Defaulting to first image or none.")
            self.current_index = 0 if self.all_image_paths else -1
            if self.current_index != -1:
                self.image_path = self.all_image_paths[self.current_index]
                # Window title will be set in _load_current_image
            else:
                self.image_path = None
                self.setWindowTitle("画像なし - ImageManager")
        else:
            self.image_path = self.all_image_paths[self.current_index]
            # Window title will be set in _load_current_image
        
        self._load_current_image() # This will load, display, and update nav buttons

        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    def _load_current_image(self):
        """Loads the image at the current_index from all_image_paths."""
        if not self.all_image_paths or self.current_index == -1:
            logger.warning("Cannot load current image, list is empty or index is invalid.")
            self.image_label.setText("表示できる画像がありません。") # This text might be overridden by _update_image_display
            self.setWindowTitle("画像なし - ImageManager")
            self.pixmap = QPixmap()
            self._update_image_display() # This will ensure label is consistent
        elif 0 <= self.current_index < len(self.all_image_paths):
            candidate_path = self.all_image_paths[self.current_index]
            self.image_path = candidate_path # Set self.image_path first

            if self.image_path is None or not isinstance(self.image_path, str):
                logger.warning(f"Image path at index {self.current_index} for _load_current_image is invalid: {self.image_path}. Treating as no image.")
                self.setWindowTitle("画像なし - ImageManager")
                # self.image_path is already None or invalid, _load_and_display_image will handle it
            else:
                try:
                    title_filename = os.path.basename(self.image_path)
                    self.setWindowTitle(f"{title_filename} - ImageManager")
                except Exception as e:
                    logger.error(f"Error getting basename for title in _load_current_image from '{self.image_path}': {e}")
                    self.setWindowTitle("エラー - ImageManager")
            
            self.pixmap = QPixmap() # Reset before loading
            self._load_and_display_image()
        else: # Should not be reached if logic above is correct, but as a fallback
            logger.error(f"Unexpected state in _load_current_image: index {self.current_index}, list size {len(self.all_image_paths)}")
            self.image_label.setText("画像読み込みエラー (内部状態異常)。") # This text might be overridden by _update_image_display
            self.setWindowTitle("エラー - ImageManager")
            self.pixmap = QPixmap()
            self._update_image_display()
        self._update_navigation_buttons()


    def show_previous_image(self):
        if not self.all_image_paths or self.current_index <= 0: # Also check if already at first image
            return
        self.current_index -= 1
        self._load_current_image()

    def show_next_image(self):
        if not self.all_image_paths or self.current_index >= len(self.all_image_paths) - 1: # Also check if already at last
            return
        self.current_index += 1
        self._load_current_image()

    def _update_navigation_buttons(self):
        if not self.all_image_paths or self.current_index == -1:
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.counter_label.setText("0 / 0") # Or "N/A" or ""
            return

        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.all_image_paths) - 1)
        self.counter_label.setText(f"{self.current_index + 1} / {len(self.all_image_paths)}")

    def toggle_fullscreen_state(self):
        if self.windowState() == Qt.WindowState.WindowMaximized:
            # Currently maximized, so restore to normal
            if self.saved_geometry and isinstance(self.saved_geometry, QByteArray):
                self.restoreGeometry(self.saved_geometry)
                # restoreGeometry might not call showNormal implicitly, so call it.
            self.showNormal() # Ensure it's shown in normal state
            self.fullscreen_button.setText("□")
            self.saved_geometry = None
            logger.debug("Image dialog restored to normal size.")
        else:
            # Currently normal or minimized, so maximize
            # Save geometry only if we are in a normal state and haven't saved it yet
            if self.windowState() == Qt.WindowState.WindowNoState and self.saved_geometry is None:
                 self.saved_geometry = self.saveGeometry()
            
            # Using setWindowState followed by show might be more robust than showMaximized directly
            self.setWindowState(Qt.WindowState.WindowMaximized)
            # self.show() # Ensure it's visible after state change - try without first, like ImageMover
            
            self.fullscreen_button.setText("❐")
            logger.debug("Image dialog maximized.")
        
        # It's generally good practice to update the display after a state change
        # that could affect layout or size, though resizeEvent should also handle it.
        self._update_image_display()
        # self._update_navigation_buttons() # Called by _load_current_image or update_image


    def _load_and_display_image(self):
        if not self.image_path:
            logger.error("Image path is None, cannot load.")
            self.image_label.setText("画像パスが指定されていません。")
            self.pixmap = QPixmap()
            self._update_image_display() # Ensure display is cleared
            self._update_navigation_buttons()
            return
        if not os.path.exists(self.image_path):
            logger.error(f"Image path does not exist: {self.image_path}")
            self.image_label.setText(f"指定された画像ファイルが見つかりません:\n{os.path.basename(self.image_path)}")
            self.pixmap = QPixmap() 
            self._update_image_display()
            self._update_navigation_buttons() 
            return

        self.pixmap = QPixmap() # Ensure pixmap is new for each load attempt
        if not self.pixmap.load(self.image_path):
            logger.error(f"Failed to load image: {self.image_path}")
            self.image_label.setText(f"画像の読み込みに失敗しました:\n{os.path.basename(self.image_path)}")
            # self.pixmap remains null from the QPixmap() call above
            self._update_image_display() # Ensure display reflects failure (cleared)
            self._update_navigation_buttons() 
            return
        
        self._update_image_display()
        self._update_navigation_buttons() 

    def _update_image_display(self):
        if self.pixmap.isNull() or self.image_path is None: # Added check for self.image_path
            self.image_label.clear() 
            if self.image_path is None and self.all_image_paths: # List might exist but current index was bad
                 self.image_label.setText("表示する画像が選択されていません。")
            elif not self.all_image_paths:
                 self.image_label.setText("表示できる画像がありません。")
            # If pixmap isNull but image_path was valid, load error text is already set by _load_and_display_image
            return

        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM:
            scaled_pixmap = self.pixmap.scaled(
                int(self.pixmap.width() * self.scale_factor),
                int(self.pixmap.height() * self.scale_factor),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.adjustSize() # Adjust label size to pixmap
        else: # PREVIEW_MODE_FIT
            # Scale pixmap to fit the label (or scroll area viewport if applicable)
            # For fit mode, image_label is directly in main_layout, so self.image_label.size() is fine.
            target_size = self.image_label.size()
            # If image_label is inside scroll_area (even if not original_zoom mode, though current logic doesn't do that),
            # it might be better to scale to scroll_area.viewport().size().
            # However, current structure for FIT mode, image_label is a direct child of main_layout.
            scaled_pixmap = self.pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        """Handle resize events to rescale the image."""
        super().resizeEvent(event)
        if self.preview_mode == PREVIEW_MODE_FIT:
            self._update_image_display()
        # For ORIGINAL_ZOOM mode, dialog resize doesn't change image scale, only viewport.

    def wheelEvent(self, event):
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.scale_factor *= 1.1
            else:
                self.scale_factor /= 1.1
            # Clamp scale factor to reasonable limits if desired
            self.scale_factor = max(0.1, min(self.scale_factor, 10.0)) 
            logger.debug(f"Zoom: Scale factor set to {self.scale_factor:.2f}")
            self._update_image_display()
            event.accept()
        elif self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM:
            # Allow normal wheel scroll for the QScrollArea
            # The event is on the QDialog, so we need to pass it to the scroll_area if it's the intended target
            # However, QScrollArea usually handles wheel events on its viewport automatically.
            # If super().wheelEvent doesn't work as expected, direct manipulation of scrollbar might be needed.
            super().wheelEvent(event) 
        else:
            super().wheelEvent(event)


    _drag_start_pos = None
    _scroll_bar_values_on_drag_start_h = 0
    _scroll_bar_values_on_drag_start_v = 0

    def mousePressEvent(self, event):
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM and event.button() == Qt.MouseButton.LeftButton:
            if self.scroll_area.horizontalScrollBar().isVisible() or self.scroll_area.verticalScrollBar().isVisible():
                self._drag_start_pos = event.pos()
                self._scroll_bar_values_on_drag_start_h = self.scroll_area.horizontalScrollBar().value()
                self._scroll_bar_values_on_drag_start_v = self.scroll_area.verticalScrollBar().value()
                self.image_label.setCursor(Qt.CursorShape.ClosedHandCursor) # Use ClosedHandCursor
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM and self._drag_start_pos is not None:
            delta = event.pos() - self._drag_start_pos
            self.scroll_area.horizontalScrollBar().setValue(self._scroll_bar_values_on_drag_start_h - delta.x())
            self.scroll_area.verticalScrollBar().setValue(self._scroll_bar_values_on_drag_start_v - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM and event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            self._drag_start_pos = None
            self.image_label.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # Optional: Close on Escape key & Navigation
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Left:
            self.show_previous_image()
        elif key == Qt.Key.Key_Right or key == Qt.Key.Key_Space: # Space for next image
            self.show_next_image()
        else:
            super().keyPressEvent(event)

if __name__ == '__main__':
    import sys
    # This basic test requires an image path.
    # Replace 'path_to_your_test_image.jpg' with an actual image path.
    # For example, if you have a 'test.jpg' in the same directory:
    # test_image_path = "test.jpg" 
    
    # As a placeholder, let's check if any argument is passed
    if len(sys.argv) > 1:
        test_image_path = sys.argv[1]
        if not os.path.exists(test_image_path):
            print(f"Test image not found: {test_image_path}")
            sys.exit(1)
    else:
        print("Please provide an image path as a command line argument for testing.")
        # Create a dummy pixmap for testing if no image is provided
        dummy_pixmap = QPixmap(QSize(100,100))
        dummy_pixmap.fill(Qt.GlobalColor.cyan)
        dummy_pixmap.save("dummy_test_image.png")
        test_image_path = "dummy_test_image.png"
        # sys.exit(1)


    app = QApplication(sys.argv)
    dialog = FullImageDialog(test_image_path)
    dialog.show()
    exit_code = app.exec()
    if test_image_path == "dummy_test_image.png" and os.path.exists("dummy_test_image.png"):
        os.remove("dummy_test_image.png")
    sys.exit(exit_code)
