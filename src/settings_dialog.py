import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QRadioButton, QDialogButtonBox, QApplication,
    QSlider, QLabel, QHBoxLayout, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPainter, QColor, QPen
import json
import os

logger = logging.getLogger(__name__)
APP_SETTINGS_FILE = "app_settings.json"

PREVIEW_MODE_FIT = "fit"
PREVIEW_MODE_ORIGINAL_ZOOM = "original_zoom"

class ThumbnailSizePreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._size = 96  # Default size
        self.max_preview_width = 3 * 96 + 2 * 5 # Max width for 3x96px + spacing
        self.preview_height = 200 # Max height for largest preview (e.g. 200px) + text
        self.setMinimumSize(self.max_preview_width + 40, self.preview_height + 40) # Add some padding
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)


    def set_size(self, size):
        self._size = size
        self.update() # Trigger repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect_size = self._size
        num_rects = 1
        spacing = 5

        if rect_size == 96:
            num_rects = 3
        elif rect_size == 128:
            num_rects = 2
        
        total_rects_width = (num_rects * rect_size) + ((num_rects - 1) * spacing)
        
        start_x = (self.width() - total_rects_width) / 2
        # Center vertically, accounting for text area below
        y = (self.height() - rect_size - 30) / 2 # Increased bottom margin for text

        painter.setPen(QPen(QColor("gray"), 1))
        painter.setBrush(QColor("lightgray"))

        current_x = start_x
        for _ in range(num_rects):
            painter.drawRect(int(current_x), int(y), rect_size, rect_size)
            current_x += rect_size + spacing

        painter.setPen(QColor("black"))
        text = f"{self._size} x {self._size} px"
        # Adjust text position to be below the rectangles
        text_y_offset = y + rect_size + 5 # 5px below the bottom of the rects
        
        # Create a rect for text drawing, ensuring it's wide enough and positioned correctly
        text_rect = self.rect().adjusted(0, int(text_y_offset), 0, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text)


    def sizeHint(self):
        # Calculate width based on largest possible preview (3 * 96px + spacing)
        # Height based on largest preview size + text area
        return QSize(self.max_preview_width + 40, self.preview_height + 40) # Add some padding

    def minimumSizeHint(self):
        return self.sizeHint()


class SettingsDialog(QDialog):
    def __init__(self, current_thumbnail_size, available_thumbnail_sizes, current_preview_mode, parent=None):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setMinimumWidth(400) # Increased width for new controls

        self.initial_thumbnail_size = current_thumbnail_size
        self.available_thumbnail_sizes = available_thumbnail_sizes
        self.current_selected_thumbnail_size = current_thumbnail_size # Tracks slider changes

        # Load only preview mode from settings file for this dialog's direct responsibility
        # Thumbnail size is passed in and its persistence is handled by MainWindow
        self.current_settings = self._load_preview_mode_setting()
        self.initial_preview_mode = self.current_settings.get("image_preview_mode", PREVIEW_MODE_FIT)


        main_layout = QVBoxLayout(self)

        # --- Thumbnail Size Group ---
        thumbnail_size_group = QGroupBox("サムネイルサイズ設定")
        thumbnail_size_layout = QVBoxLayout()

        slider_layout = QHBoxLayout()
        self.thumbnail_size_label = QLabel() # Will be updated by _update_thumbnail_size_preview
        slider_layout.addWidget(self.thumbnail_size_label)

        self.thumbnail_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.thumbnail_size_slider.setMinimum(0)
        self.thumbnail_size_slider.setMaximum(len(self.available_thumbnail_sizes) - 1)
        try:
            initial_slider_value = self.available_thumbnail_sizes.index(self.initial_thumbnail_size)
        except ValueError:
            initial_slider_value = 0 # Default to first available size if current is not in list
            self.initial_thumbnail_size = self.available_thumbnail_sizes[0]
            self.current_selected_thumbnail_size = self.initial_thumbnail_size
            logger.warning(f"Initial thumbnail size {current_thumbnail_size} not in available list. Defaulting to {self.initial_thumbnail_size}")

        self.thumbnail_size_slider.setValue(initial_slider_value)
        self.thumbnail_size_slider.setTickInterval(1)
        self.thumbnail_size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider_layout.addWidget(self.thumbnail_size_slider)
        thumbnail_size_layout.addLayout(slider_layout)

        self.thumbnail_preview_widget = ThumbnailSizePreviewWidget(self)
        thumbnail_size_layout.addWidget(self.thumbnail_preview_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        
        thumbnail_size_group.setLayout(thumbnail_size_layout)
        main_layout.addWidget(thumbnail_size_group)

        self.thumbnail_size_slider.valueChanged.connect(self._update_thumbnail_size_preview)
        self._update_thumbnail_size_preview(self.thumbnail_size_slider.value()) # Initial setup

        # --- Image Preview Mode Group ---
        preview_mode_group = QGroupBox("画像表示ダイアログの表示モード")
        preview_mode_layout = QVBoxLayout()

        self.fit_mode_radio = QRadioButton("ダイアログサイズに合わせて表示（フィット表示）")
        self.original_zoom_mode_radio = QRadioButton("原寸で表示（Ctrl+ホイールでズーム、ドラッグでスクロール）")

        preview_mode_layout.addWidget(self.fit_mode_radio)
        preview_mode_layout.addWidget(self.original_zoom_mode_radio)
        preview_mode_group.setLayout(preview_mode_layout)
        main_layout.addWidget(preview_mode_group)

        if self.initial_preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM:
            self.original_zoom_mode_radio.setChecked(True)
        else:
            self.fit_mode_radio.setChecked(True)

        # --- Dialog Buttons (OK, Cancel) ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        self.setLayout(main_layout)

    def _update_thumbnail_size_preview(self, value):
        try:
            size = self.available_thumbnail_sizes[value]
            self.current_selected_thumbnail_size = size # Update tracked size
            self.thumbnail_size_label.setText(f"選択中: {size}px")
            self.thumbnail_preview_widget.set_size(size)
        except IndexError:
            logger.error(f"Slider value {value} is out of range for available_thumbnail_sizes.")


    def _load_preview_mode_setting(self):
        """Loads only the image_preview_mode setting."""
        try:
            if os.path.exists(APP_SETTINGS_FILE):
                with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    return {"image_preview_mode": settings.get("image_preview_mode", PREVIEW_MODE_FIT)}
            else:
                logger.info(f"設定ファイル ({APP_SETTINGS_FILE}) が見つかりません。プレビューモードのデフォルト設定を使用します。")
        except Exception as e:
            logger.error(f"設定ファイル ({APP_SETTINGS_FILE}) の読み込み中にエラー: {e}", exc_info=True)
        return {"image_preview_mode": PREVIEW_MODE_FIT} # Default on error or if file not found

    def _save_dialog_specific_settings(self):
        """Saves settings that this dialog is directly responsible for changing *internally*."""
        # This method is called when OK is pressed.
        # MainWindow will handle the actual persistence of thumbnail_size to app_settings.json
        # after user confirmation. This dialog only needs to update its internal state
        # for image_preview_mode if it changed.
        
        # Update internal current_settings for preview mode
        if self.fit_mode_radio.isChecked():
            self.current_settings["image_preview_mode"] = PREVIEW_MODE_FIT
        elif self.original_zoom_mode_radio.isChecked():
            self.current_settings["image_preview_mode"] = PREVIEW_MODE_ORIGINAL_ZOOM
        
        # Note: Thumbnail size is NOT saved to app_settings.json by this dialog.
        # It's returned by get_selected_thumbnail_size() for MainWindow to handle.
        return True # Indicate internal update was successful

    def accept(self):
        # Update internal state for preview mode
        self._save_dialog_specific_settings()
        # MainWindow will call get_selected_thumbnail_size() and get_selected_preview_mode()
        # and then decide whether to show a confirmation for thumbnail size change,
        # and then persist all settings.
        super().accept()

    def get_selected_preview_mode(self):
        if self.fit_mode_radio.isChecked():
            return PREVIEW_MODE_FIT
        elif self.original_zoom_mode_radio.isChecked():
            return PREVIEW_MODE_ORIGINAL_ZOOM
        return self.initial_preview_mode # Fallback to initial if somehow none is checked

    def get_selected_thumbnail_size(self):
        # Returns the size currently selected by the slider in this dialog session
        return self.current_selected_thumbnail_size

if __name__ == '__main__':
    import sys
    # Dummy data for testing
    available_sizes_test = [96, 128, 200, 256]
    current_size_test = 128
    current_preview_mode_test = PREVIEW_MODE_FIT

    # Create a dummy app_settings.json for testing if it doesn't exist
    if not os.path.exists(APP_SETTINGS_FILE):
        with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"image_preview_mode": PREVIEW_MODE_ORIGINAL_ZOOM, "thumbnail_size": 128, "other_setting": "test"}, f, indent=4)
    else: # Ensure it has expected keys for test
        with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            temp_settings = json.load(f)
        temp_settings.setdefault("image_preview_mode", PREVIEW_MODE_FIT)
        temp_settings.setdefault("thumbnail_size", 128)
        with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(temp_settings, f, indent=4)


    app = QApplication(sys.argv)
    dialog = SettingsDialog(
        current_thumbnail_size=current_size_test,
        available_thumbnail_sizes=available_sizes_test,
        current_preview_mode=current_preview_mode_test
    )
    if dialog.exec():
        print("Settings accepted by dialog.")
        selected_size = dialog.get_selected_thumbnail_size()
        selected_mode = dialog.get_selected_preview_mode()
        print(f"Selected thumbnail size from dialog: {selected_size}")
        print(f"Selected preview mode from dialog: {selected_mode}")

        # Simulate MainWindow saving the settings
        # In real app, MainWindow would show confirmation for thumbnail size change
        # and then save all settings.
        print("Simulating MainWindow saving all settings...")
        main_window_settings_to_save = {}
        if os.path.exists(APP_SETTINGS_FILE):
             with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                main_window_settings_to_save = json.load(f)
        
        main_window_settings_to_save["thumbnail_size"] = selected_size
        main_window_settings_to_save["image_preview_mode"] = selected_mode
        
        with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(main_window_settings_to_save, f, indent=4)
        print(f"MainWindow saved: {main_window_settings_to_save}")

    else:
        print("Settings cancelled by dialog.")
    
    sys.exit()
