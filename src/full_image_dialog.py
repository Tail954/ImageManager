import logging
import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication, QSpacerItem, QSizePolicy
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QSize, QByteArray

logger = logging.getLogger(__name__)

class FullImageDialog(QDialog):
    def __init__(self, image_path_list, current_index, parent=None):
        super().__init__(parent)
        self.all_image_paths = image_path_list
        self.current_index = current_index
        self.image_path = self.all_image_paths[self.current_index] if self.all_image_paths and 0 <= self.current_index < len(self.all_image_paths) else None
        
        self.pixmap = QPixmap()
        self.saved_geometry = None # For storing geometry before maximizing

        self.setWindowTitle(f"{os.path.basename(self.image_path if self.image_path else 'No Image')} - ImageManager")
        self.setMinimumSize(400, 300)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        # layout.setContentsMargins(0,0,0,0) # Keep some margins for controls

        # Controls layout (for navigation and fullscreen button)
        controls_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("← Previous")
        self.prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_button.clicked.connect(self.show_previous_image)
        controls_layout.addWidget(self.prev_button)

        self.counter_label = QLabel("")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls_layout.addWidget(self.counter_label)

        self.next_button = QPushButton("Next →")
        self.next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_button.clicked.connect(self.show_next_image)
        controls_layout.addWidget(self.next_button)
        
        controls_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)) # Spacer

        self.fullscreen_button = QPushButton("□") # Maximize symbol
        self.fullscreen_button.setFixedSize(30, 30)
        self.fullscreen_button.setToolTip("最大化/元に戻す")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen_state)
        controls_layout.addWidget(self.fullscreen_button)
        
        main_layout.addLayout(controls_layout)

        # Image label
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Make the label expand to take available space
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        main_layout.addWidget(self.image_label, 1) # Add with stretch factor

        self.setLayout(main_layout)
        
        self._load_and_display_image()
        self.resize(800, 600)

    def update_image(self, new_image_path_list, new_current_index):
        """Updates the image list and current index, then loads the image."""
        self.all_image_paths = new_image_path_list
        self.current_index = new_current_index
        if self.all_image_paths and 0 <= self.current_index < len(self.all_image_paths):
            self.image_path = self.all_image_paths[self.current_index]
            # Window title will be set in _load_current_image (via _load_and_display_image)
        else:
            self.image_path = None # Mark as invalid
        
        self._load_current_image() # This will load, display, and update nav buttons

        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    def _load_current_image(self):
        """Loads the image at the current_index from all_image_paths."""
        if self.all_image_paths and 0 <= self.current_index < len(self.all_image_paths):
            self.image_path = self.all_image_paths[self.current_index]
            self.setWindowTitle(f"{os.path.basename(self.image_path)} - ImageManager")
            self.pixmap = QPixmap() # Reset before loading
            self._load_and_display_image() 
        else:
            logger.warning("Cannot load current image, index or list is invalid.")
            self.image_label.setText("画像インデックスが無効です。")
            self.pixmap = QPixmap() # Ensure pixmap is cleared
            self._update_image_display() # Clear image display
        self._update_navigation_buttons()


    def show_previous_image(self):
        if self.all_image_paths and self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()

    def show_next_image(self):
        if self.all_image_paths and self.current_index < len(self.all_image_paths) - 1:
            self.current_index += 1
            self._load_current_image()

    def _update_navigation_buttons(self):
        if not self.all_image_paths or self.image_path is None:
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.counter_label.setText("N/A")
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
        if not self.image_path or not os.path.exists(self.image_path): # Check self.image_path here
            logger.error(f"Image path is invalid or does not exist: {self.image_path}")
            self.image_label.setText("画像が見つかりません。")
            self.pixmap = QPixmap() # Clear pixmap
            # self._update_navigation_buttons() # Update nav based on invalid image
            return

        if not self.pixmap.load(self.image_path):
            logger.error(f"Failed to load image: {self.image_path}")
            self.image_label.setText(f"画像の読み込みに失敗しました:\n{os.path.basename(self.image_path)}")
            self.pixmap = QPixmap() # Clear pixmap
            # self._update_navigation_buttons() # Update nav based on failed load
            return
        
        self._update_image_display()
        self._update_navigation_buttons() # Update navigation buttons after successful load or failure message

    def _update_image_display(self):
        if self.pixmap.isNull():
            return
            
        # Scale pixmap to fit the label while keeping aspect ratio
        # Use self.image_label.size() for scaling target
        scaled_pixmap = self.pixmap.scaled(
            self.image_label.size(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        """Handle resize events to rescale the image."""
        super().resizeEvent(event)
        # When the dialog (and thus the label, if it's the only central widget) resizes,
        # update the pixmap display.
        self._update_image_display()

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
