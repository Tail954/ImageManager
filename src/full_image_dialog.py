import logging
import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout
from PyQt6.QtCore import Qt, QByteArray, pyqtSignal

from .image_preview_widget import ImagePreviewWidget
from .constants import PREVIEW_MODE_FIT

logger = logging.getLogger(__name__)

class FullImageDialog(QDialog):
    toggle_fullscreen_requested = pyqtSignal(bool)
    toggle_selection_requested = pyqtSignal(str) # New signal: image_path

    def __init__(self, image_path_list, current_index, preview_mode=PREVIEW_MODE_FIT, parent=None, is_selected_callback=None):
        super().__init__(parent)
        self.all_image_paths = image_path_list if image_path_list is not None else []
        self.current_index = current_index
        self.preview_mode = preview_mode
        self.is_selected_callback = is_selected_callback
        self.saved_geometry = None 
        self.image_path = None # Will be set in update_image/update_title

        self.setMinimumSize(400, 300)
        self.resize(800, 600)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0) 

        self.preview_widget = ImagePreviewWidget(self, preview_mode)
        main_layout.addWidget(self.preview_widget)

        self.setLayout(main_layout)
        
        # Connect signals
        self.preview_widget.previous_image_requested.connect(self.show_previous_image)
        self.preview_widget.next_image_requested.connect(self.show_next_image)
        self.preview_widget.toggle_fullscreen_requested.connect(self.toggle_fullscreen_state)
        self.preview_widget.toggle_selection_requested.connect(self._on_toggle_selection) # Connect signal

        # Initial Load
        self._update_current_image_info() # Sets title and image_path
        self.preview_widget.update_image(
            self.image_path, 
            self.current_index, 
            len(self.all_image_paths)
        )
        self.setFocus() 

    def _update_current_image_info(self):
        """Updates internal state and window title based on current index."""
        if not self.all_image_paths:
            self.image_path = None
            self.current_index = -1
            self.setWindowTitle("画像なし - ImageManager")
            return

        if not (0 <= self.current_index < len(self.all_image_paths)):
            self.current_index = 0 if self.all_image_paths else -1
        
        if self.current_index != -1:
            self.image_path = self.all_image_paths[self.current_index]
            try:
                title_filename = os.path.basename(self.image_path)
                self.setWindowTitle(f"{title_filename} - ImageManager")
            except Exception:
                self.setWindowTitle("ImageManager")
        else:
            self.image_path = None
            self.setWindowTitle("画像なし - ImageManager")

    def update_image(self, new_image_path_list, new_current_index):
        """Updates the image list and current index, then loads the image."""
        self.all_image_paths = new_image_path_list if new_image_path_list is not None else []
        self.current_index = new_current_index
        
        self._update_current_image_info()
        self.preview_widget.update_image(
            self.image_path, 
            self.current_index, 
            len(self.all_image_paths)
        )

        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def show_previous_image(self):
        if not self.all_image_paths or self.current_index <= 0:
            return
        self.current_index -= 1
        self._update_current_image_info()
        self._update_current_image_info()
        self.preview_widget.update_image(self.image_path, self.current_index, len(self.all_image_paths), self._get_current_selection_state())

    def show_next_image(self):
        if not self.all_image_paths or self.current_index >= len(self.all_image_paths) - 1:
            return
        self.current_index += 1
        self._update_current_image_info()
        self._update_current_image_info()
        self.preview_widget.update_image(self.image_path, self.current_index, len(self.all_image_paths), self._get_current_selection_state())

    def toggle_fullscreen_state(self):
        if self.windowState() == Qt.WindowState.WindowMaximized:
            if self.saved_geometry and isinstance(self.saved_geometry, QByteArray):
                self.restoreGeometry(self.saved_geometry)
            self.showNormal()
            self.saved_geometry = None
            self.preview_widget.update_fullscreen_button_text("□")
        else:
            if self.windowState() == Qt.WindowState.WindowNoState and self.saved_geometry is None:
                 self.saved_geometry = self.saveGeometry()
            self.setWindowState(Qt.WindowState.WindowMaximized)
            self.preview_widget.update_fullscreen_button_text("❐")
        
        # In case resize event isn't triggered or needed logic inside widget
        # self.preview_widget.update() # Widget handles resizeEvent

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        elif key == Qt.Key.Key_Left:
            self.show_previous_image()
            event.accept()
        elif key == Qt.Key.Key_Right or key == Qt.Key.Key_Space:
            self.show_next_image()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # Movie stopping is handled in widget's update_image(None) or implicitly when widget is destroyed
        if self.preview_widget.movie:
            self.preview_widget.movie.stop()
        super().closeEvent(event)
    
    def _on_toggle_selection(self):
        if self.image_path:
            self.toggle_selection_requested.emit(self.image_path)

    def _get_current_selection_state(self):
        if self.image_path and self.is_selected_callback:
            return self.is_selected_callback(self.image_path)
        return False

    def update_selection_state(self, image_path):
        """Called externally to update selection state of current image"""
        if self.image_path == image_path:
             self.preview_widget.set_selection_state(self._get_current_selection_state())

    def set_is_selected_callback(self, callback):
        self.is_selected_callback = callback


if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication
    
    # Simple test
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
    else:
        test_path = "test.jpg" # Dummy

    app = QApplication(sys.argv)
    # Mocking a list of images with just one image
    dialog = FullImageDialog([test_path], 0)
    dialog.show()
    sys.exit(app.exec())
