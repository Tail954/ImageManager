import logging
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QScrollArea, QSpacerItem
from PyQt6.QtGui import QPixmap, QMovie
from PyQt6.QtCore import Qt, QSize, QByteArray, pyqtSignal

from PIL import Image
try:
    from PIL import ImageQt
except ImportError:
    ImageQt = None

from .constants import PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM

logger = logging.getLogger(__name__)

class ImagePreviewWidget(QWidget):
    # Signals to communicate with parent container (Dialog)
    previous_image_requested = pyqtSignal()
    next_image_requested = pyqtSignal()
    toggle_fullscreen_requested = pyqtSignal()
    toggle_selection_requested = pyqtSignal() # New signal

    def __init__(self, parent=None, preview_mode=PREVIEW_MODE_FIT):
        super().__init__(parent)
        self.preview_mode = preview_mode
        self.scale_factor = 1.0 # For original_zoom mode
        self.pixmap = QPixmap()
        self.movie = None # QMovieインスタンスを保持
        self.image_path = None
        
        self.init_ui()

    def init_ui(self):
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Widget usually fit into container

        # Controls layout (navigation)
        self.controls_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("← Previous")
        self.prev_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_button.clicked.connect(self.previous_image_requested.emit)
        self.controls_layout.addWidget(self.prev_button)

        self.counter_label = QLabel("")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.controls_layout.addWidget(self.counter_label)

        self.next_button = QPushButton("Next →")
        self.next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_button.clicked.connect(self.next_image_requested.emit)
        self.controls_layout.addWidget(self.next_button)

        # Selection Toggle Button
        self.selection_button = QPushButton("Select")
        self.selection_button.setCheckable(True)
        self.selection_button.setFixedSize(50, 50) # 丸いボタンにするために固定サイズを設定
        self.selection_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.selection_button.clicked.connect(self.toggle_selection_requested.emit)
        self.controls_layout.addWidget(self.selection_button)
        
        self.controls_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.fullscreen_button = QPushButton("□")
        self.fullscreen_button.setFixedSize(30, 30)
        self.fullscreen_button.setToolTip("最大化/元に戻す")
        self.fullscreen_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen_requested.emit)
        self.controls_layout.addWidget(self.fullscreen_button)
        
        main_layout.addLayout(self.controls_layout)

        # Image display area
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM:
            self.scroll_area = QScrollArea(self)
            self.scroll_area.setWidgetResizable(False) # Important for original size + zoom
            self.scroll_area.setWidget(self.image_label)
            self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
            main_layout.addWidget(self.scroll_area, 1)
        else: # PREVIEW_MODE_FIT
            self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            main_layout.addWidget(self.image_label, 1)

    def update_image(self, image_path, current_index, total_count, is_selected=False):
        """Loads and sorts the image. is_selected: initial selection state."""
        if self.movie and self.movie.state() == QMovie.MovieState.Running:
            try:
                self.movie.frameChanged.disconnect(self._update_movie_frame)
            except TypeError:
                pass
            self.movie.stop()
        self.image_label.setMovie(None)
        self.movie = None

        self.image_path = image_path
        self._update_navigation_buttons(current_index, total_count)
        self.set_selection_state(is_selected) # Update button state

        if not self.image_path:
            self.image_label.setText("表示できる画像がありません。")
            self.pixmap = QPixmap()
            self._update_image_display()
            return

        if not os.path.exists(self.image_path):
            self.image_label.setText(f"指定された画像ファイルが見つかりません:\n{os.path.basename(self.image_path)}")
            self.pixmap = QPixmap()
            self._update_image_display()
            return

        self._load_image_data()
        self._update_image_display()

    def _load_image_data(self):
        try:
            pil_img_check = Image.open(self.image_path)
            is_animated_webp = False
            if pil_img_check.format == "WEBP":
                try:
                    if pil_img_check.is_animated: is_animated_webp = True
                except AttributeError:
                    if hasattr(pil_img_check, 'n_frames') and pil_img_check.n_frames > 1: is_animated_webp = True
            pil_img_check.close()

            if is_animated_webp:
                logger.info(f"アニメーションWebPを読み込みます: {self.image_path}")
                self.movie = QMovie(self.image_path)
                self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
                if not self.movie.isValid():
                    logger.error(f"QMovieの読み込みに失敗: {self.image_path}")
                    self.image_label.setText(f"動画の読み込みに失敗:\n{os.path.basename(self.image_path)}")
                    self.movie = None
                else:
                    self.movie.frameChanged.connect(self._update_movie_frame)
            else:
                try:
                    pil_img = Image.open(self.image_path)
                    if ImageQt is None:
                        if not self.pixmap.load(self.image_path):
                             self.image_label.setText(f"画像の読み込みに失敗しました (QPixmap):\n{os.path.basename(self.image_path)}")
                    else:
                        if pil_img.mode == "RGBA":
                            q_image = ImageQt.ImageQt(pil_img)
                        elif pil_img.mode == "RGB":
                            q_image = ImageQt.ImageQt(pil_img.convert("RGBA"))
                        else:
                            q_image = ImageQt.ImageQt(pil_img.convert("RGBA"))
                        
                        self.pixmap = QPixmap.fromImage(q_image)
                        if self.pixmap.isNull():
                            self.image_label.setText(f"画像の変換に失敗しました:\n{os.path.basename(self.image_path)}")
                    pil_img.close()
                except Exception as pil_e:
                    logger.error(f"Pillow error: {pil_e}", exc_info=True)
                    self.image_label.setText(f"画像の読み込み中にエラー (Pillow):\n{os.path.basename(self.image_path)}")
                    self.pixmap = QPixmap()
        except Exception as e:
            logger.error(f"Load error: {e}", exc_info=True)
            self.image_label.setText(f"ファイルの読み込みに失敗:\n{os.path.basename(self.image_path)}")
            if self.movie:
                self.movie.stop()
                self.movie = None

    def _update_image_display(self):
        if self.movie and self.movie.isValid():
            self.image_label.setText("")
            self._update_movie_frame()
            if self.movie.state() != QMovie.MovieState.Running:
                 self.movie.start()
            return
        
        if not self.pixmap.isNull():
            self.image_label.setText("")
            if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM:
                scaled_pixmap = self.pixmap.scaled(
                    int(self.pixmap.width() * self.scale_factor),
                    int(self.pixmap.height() * self.scale_factor),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
                self.image_label.adjustSize() 
            else: # PREVIEW_MODE_FIT
                target_size = self.image_label.size()
                # Ensure target size is valid to avoid warnings
                if target_size.width() <= 0 or target_size.height() <= 0:
                    return
                scaled_pixmap = self.pixmap.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
            return

        if not self.image_label.text():
             self.image_label.setText("表示なし")

    def _update_movie_frame(self):
        if self.movie and self.movie.isValid() and self.image_label:
            current_frame_pixmap = self.movie.currentPixmap()
            if not current_frame_pixmap.isNull():
                if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM:
                    original_size = current_frame_pixmap.size()
                    self.image_label.setFixedSize(original_size)
                    self.image_label.setPixmap(current_frame_pixmap)
                else: # PREVIEW_MODE_FIT
                    target_label_size = self.image_label.size()
                    if target_label_size.width() <= 0 or target_label_size.height() <= 0:
                        return
                    scaled_pixmap = current_frame_pixmap.scaled(
                        target_label_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.image_label.setPixmap(scaled_pixmap)

    def _update_navigation_buttons(self, current_index, total_count):
        if total_count <= 0 or current_index == -1:
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.counter_label.setText("0 / 0")
            return

        self.prev_button.setEnabled(current_index > 0)
        self.next_button.setEnabled(current_index < total_count - 1)
        self.counter_label.setText(f"{current_index + 1} / {total_count}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if (self.movie and self.movie.isValid()) or self.preview_mode == PREVIEW_MODE_FIT:
            self._update_image_display()

    def wheelEvent(self, event):
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if self.movie and self.movie.isValid():
                event.ignore()
                return

            if delta > 0:
                self.scale_factor *= 1.1
            else:
                self.scale_factor /= 1.1
            self.scale_factor = max(0.1, min(self.scale_factor, 10.0)) 
            self._update_image_display()
            event.accept()
        elif self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM:
            super().wheelEvent(event)
        else:
            super().wheelEvent(event)

    _drag_start_pos = None
    _scroll_bar_values_on_drag_start_h = 0
    _scroll_bar_values_on_drag_start_v = 0

    def mousePressEvent(self, event):
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM and event.button() == Qt.MouseButton.LeftButton:
            if self.movie and self.movie.isValid():
                super().mousePressEvent(event)
                return

            if self.scroll_area.horizontalScrollBar().isVisible() or self.scroll_area.verticalScrollBar().isVisible():
                self._drag_start_pos = event.pos()
                self._scroll_bar_values_on_drag_start_h = self.scroll_area.horizontalScrollBar().value()
                self._scroll_bar_values_on_drag_start_v = self.scroll_area.verticalScrollBar().value()
                self.image_label.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM and self._drag_start_pos is not None:
            if self.movie and self.movie.isValid():
                super().mouseMoveEvent(event)
                return

            delta = event.pos() - self._drag_start_pos
            self.scroll_area.horizontalScrollBar().setValue(self._scroll_bar_values_on_drag_start_h - delta.x())
            self.scroll_area.verticalScrollBar().setValue(self._scroll_bar_values_on_drag_start_v - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM and event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            if self.movie and self.movie.isValid():
                super().mouseReleaseEvent(event)
                return

            self._drag_start_pos = None
            self.image_label.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def update_fullscreen_button_text(self, text):
        self.fullscreen_button.setText(text)

    def set_selection_state(self, is_selected):
        """Updates the selection button state and appearance."""
        self.selection_button.setChecked(is_selected)
        if is_selected:
            self.selection_button.setText("✔")
            self.selection_button.setStyleSheet("QPushButton { background-color: orange; color: black; font-weight: bold; border-radius: 25px; font-size: 20px; }")
        else:
            self.selection_button.setText("Select")
            self.selection_button.setStyleSheet("QPushButton { border-radius: 25px; border: 1px solid #ccc; background-color: #f0f0f0; }")
