import logging
import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QSplitter
from PyQt6.QtCore import Qt, QByteArray, pyqtSignal

from .image_preview_widget import ImagePreviewWidget
from .metadata_widget import MetadataWidget
from .constants import PREVIEW_MODE_FIT, METADATA_ROLE
from .metadata_utils import extract_image_metadata

logger = logging.getLogger(__name__)

class ImageWithMetadataDialog(QDialog):
    previous_image_requested = pyqtSignal()
    next_image_requested = pyqtSignal()
    toggle_fullscreen_requested = pyqtSignal(bool)
    toggle_selection_requested = pyqtSignal(str) # New signal

    def __init__(self, image_path_list, current_index, main_window, preview_mode=PREVIEW_MODE_FIT, parent=None):
        super().__init__(parent)
        self.all_image_paths = image_path_list if image_path_list is not None else []
        self.current_index = current_index
        self.main_window = main_window # To access metadata cache
        self.preview_mode = preview_mode
        self.saved_geometry = None 
        self.image_path = None 

        self.setWindowTitle("画像とメタデータ - ImageManager")
        self.resize(1200, 800) # Larger size for split view

        main_layout = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Image Preview
        self.preview_widget = ImagePreviewWidget(self, preview_mode)
        self.splitter.addWidget(self.preview_widget)

        # Right: Metadata
        self.metadata_widget = MetadataWidget(self)
        self.splitter.addWidget(self.metadata_widget)

        self.splitter.setSizes([800, 400]) # Initial ratio
        self.splitter.setStretchFactor(0, 1) # Image takes more space
        self.splitter.setStretchFactor(1, 0)

        main_layout.addWidget(self.splitter)
        self.setLayout(main_layout)

        # Connect signals
        self.preview_widget.previous_image_requested.connect(self.show_previous_image)
        self.preview_widget.next_image_requested.connect(self.show_next_image)
        self.preview_widget.toggle_fullscreen_requested.connect(self.toggle_fullscreen_state)
        self.preview_widget.toggle_selection_requested.connect(self._on_toggle_selection) # Connect signal

        # Initial Load
        self._load_current_state()

    def _load_current_state(self):
        self._update_current_image_info()
        self.preview_widget.update_image(
            self.image_path, 
            self.current_index, 
            len(self.all_image_paths),
            self._get_current_selection_state()
        )
        self._update_metadata_display()
        self.setFocus()

    def _update_current_image_info(self):
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
                base_name = os.path.basename(self.image_path)
                self.setWindowTitle(f"{base_name} - ImageManager")
            except Exception:
                self.setWindowTitle("ImageManager")
        else:
            self.image_path = None
            self.setWindowTitle("画像なし - ImageManager")

    def _update_metadata_display(self):
        if not self.image_path:
            self.metadata_widget.update_metadata({})
            return

        # Try to get metadata from cache
        metadata = self.main_window.metadata_cache.get(self.image_path)
        
        if not isinstance(metadata, dict):
            # Not in cache, try to extract
            try:
                metadata = extract_image_metadata(self.image_path)
                # Update cache
                self.main_window.metadata_cache[self.image_path] = metadata
            except Exception as e:
                logger.error(f"Failed to extract metadata for {self.image_path}: {e}")
                metadata = {}
        
        self.metadata_widget.update_metadata(metadata)

    def update_image(self, new_image_path_list, new_current_index):
        self.all_image_paths = new_image_path_list if new_image_path_list is not None else []
        self.current_index = new_current_index
        self._load_current_state()
        
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    def show_previous_image(self):
        if not self.all_image_paths or self.current_index <= 0:
            return
        self.current_index -= 1
        self._load_current_state()

    def show_next_image(self):
        if not self.all_image_paths or self.current_index >= len(self.all_image_paths) - 1:
            return
        self.current_index += 1
        self._load_current_state()

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
        if self.preview_widget.movie:
            self.preview_widget.movie.stop()
        super().closeEvent(event)

    def _on_toggle_selection(self):
        if self.image_path:
            self.toggle_selection_requested.emit(self.image_path)
            # Optimistically update or wait for callback logic if needed. 
            # Ideally MainWindow updates selection model -> triggers update here if connected,
            # OR we just rely on the button click having emitted the signal.
            # MainWindow should handle the logic. 
            # We can re-sync state immediately if we have access to MainWindow logic.
            self.update_selection_state(self.image_path)

    def _get_current_selection_state(self):
        if self.image_path and hasattr(self.main_window, 'is_image_selected'):
            return self.main_window.is_image_selected(self.image_path)
        return False

    def update_selection_state(self, image_path):
        """Called externally to update selection state"""
        if self.image_path == image_path:
             self.preview_widget.set_selection_state(self._get_current_selection_state())

