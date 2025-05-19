import logging
import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication, QSpacerItem, QSizePolicy
from PyQt6.QtGui import QPixmap, QMovie # QMovie をインポート
from PyQt6.QtCore import Qt, QSize, QByteArray, QTimer

from PIL import Image # PillowをインポートしてWebPのアニメーション判定に使用
try:
    from PIL import ImageQt # PillowのImageオブジェクトをQImageに変換するために必要
except ImportError:
    ImageQt = None

from .constants import PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM # Import from constants

logger = logging.getLogger(__name__)

class FullImageDialog(QDialog):
    def __init__(self, image_path_list, current_index, preview_mode=PREVIEW_MODE_FIT, parent=None):
        super().__init__(parent)
        self.all_image_paths = image_path_list if image_path_list is not None else []
        self.current_index = current_index
        self.preview_mode = preview_mode
        self.scale_factor = 1.0 # For original_zoom mode
        self.pixmap = QPixmap()
        self.movie = None # QMovieインスタンスを保持
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
        self.fullscreen_button.setFocusPolicy(Qt.FocusPolicy.NoFocus) # ★ フォーカスポリシー変更
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
        self.setFocus() # ★ 初期表示時にフォーカスを設定

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
        self.setFocus() # ★ 画像更新時にフォーカスを設定

    def _load_current_image(self):
        """Loads the image at the current_index from all_image_paths."""
        if self.movie and self.movie.state() == QMovie.MovieState.Running:
            try:
                self.movie.frameChanged.disconnect(self._update_movie_frame)
            except TypeError:
                logger.debug("Attempted to disconnect frameChanged, but was not connected or already disconnected.")
            self.movie.stop()
        self.image_label.setMovie(None) # 以前のmovieをクリア
        self.movie = None
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
        self.setFocus() # ★ 画像読み込み後にフォーカスを設定


    def show_previous_image(self):
        if not self.all_image_paths or self.current_index <= 0: # Also check if already at first image
            return
        self.current_index -= 1
        self._load_current_image()
        # self.setFocus() は _load_current_image 内で呼ばれる

    def show_next_image(self):
        if not self.all_image_paths or self.current_index >= len(self.all_image_paths) - 1: # Also check if already at last
            return
        self.current_index += 1
        self._load_current_image()
        # self.setFocus() は _load_current_image 内で呼ばれる

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
        # 既存のムービーがあれば停止・クリア
        if self.movie and self.movie.state() == QMovie.MovieState.Running:
            try:
                self.movie.frameChanged.disconnect(self._update_movie_frame)
            except TypeError:
                pass # Not connected
            self.movie.stop()
        self.image_label.setMovie(None)
        self.movie = None
        self.pixmap = QPixmap() # pixmapもリセット

        if not self.image_path:
            logger.error("Image path is None, cannot load.")
            self._update_image_display() # Ensure display is cleared
            self._update_navigation_buttons()
            return
        if not os.path.exists(self.image_path):
            logger.error(f"Image path does not exist: {self.image_path}")
            self.image_label.setText(f"指定された画像ファイルが見つかりません:\n{os.path.basename(self.image_path)}")
            self._update_image_display()
            self._update_navigation_buttons() 
            return

        try:
            # PillowでWebPがアニメーションか判定
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
                    logger.error(f"QMovieの読み込みに失敗: {self.image_path}. Movie error: {self.movie.lastErrorString()}")
                    self.image_label.setText(f"動画の読み込みに失敗:\n{os.path.basename(self.image_path)}")
                    self.movie = None # 無効なmovieはクリア
                else:
                    # self.image_label.setMovie(self.movie) # QMovieを直接セットするのをやめる
                    try: # 念のため既存の接続を解除
                        self.movie.frameChanged.disconnect(self._update_movie_frame)
                    except TypeError:
                        pass
                    self.movie.frameChanged.connect(self._update_movie_frame)
                    # _update_image_display で再生とスケーリング
            else: # 静止画として読み込み
                try:
                    pil_img = Image.open(self.image_path)
                    if ImageQt is None:
                        logger.error("Pillow (PIL) の ImageQt モジュールが見つかりません。QPixmap.load() を試みます。")
                        if not self.pixmap.load(self.image_path):
                             logger.error(f"Failed to load image with QPixmap.load(): {self.image_path}")
                             self.image_label.setText(f"画像の読み込みに失敗しました (QPixmap):\n{os.path.basename(self.image_path)}")
                        # QPixmap.load() が成功した場合、self.pixmap は有効になる
                    else:
                        # ImageQt を使用した変換 (thumbnail_loader.py と同様のロジック)
                        if pil_img.mode == "RGBA":
                            q_image = ImageQt.ImageQt(pil_img)
                        elif pil_img.mode == "RGB":
                            q_image = ImageQt.ImageQt(pil_img.convert("RGBA"))
                        else: # Other modes like P, L, 1, etc.
                            q_image = ImageQt.ImageQt(pil_img.convert("RGBA"))
                        
                        self.pixmap = QPixmap.fromImage(q_image)
                        if self.pixmap.isNull():
                            logger.error(f"Failed to convert PIL Image to QPixmap: {self.image_path}")
                            self.image_label.setText(f"画像の変換に失敗しました:\n{os.path.basename(self.image_path)}")
                    pil_img.close()
                except Exception as pil_e:
                    logger.error(f"Pillowでの画像読み込みまたは変換中にエラー ({self.image_path}): {pil_e}", exc_info=True)
                    self.image_label.setText(f"画像の読み込み中にエラー (Pillow):\n{os.path.basename(self.image_path)}")
                    self.pixmap = QPixmap() # エラー時はpixmapを空にする
        except Exception as e:
            logger.error(f"画像/動画の読み込み準備中にエラー ({self.image_path}): {e}", exc_info=True)
            self.image_label.setText(f"ファイルの読み込みに失敗:\n{os.path.basename(self.image_path)}")
            if self.movie: # エラー発生時にもしmovieが作られていたら
                self.movie.stop()
                self.image_label.setMovie(None)
                self.movie = None

        self._update_image_display()
        self._update_navigation_buttons() 
        # self.setFocus() は呼び出し元の _load_current_image で呼ばれる

    def _update_image_display(self):
        # 優先度1: 有効なQMovieがあればそれを表示
        if self.movie and self.movie.isValid():
            self.image_label.setText("") # エラーテキストをクリア (初回表示時など)
            # QMovieのフレーム更新は frameChanged シグナル経由で行う
            self._update_movie_frame() # 初期フレームを表示
            if self.movie.state() != QMovie.MovieState.Running:
                 self.movie.start()
            return
        
        # 優先度2: 有効なQPixmapがあればそれを表示
        if not self.pixmap.isNull():
            self.image_label.setText("") # エラーテキストをクリア
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
                scaled_pixmap = self.pixmap.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
            return

        # ここに来る場合は、有効なMovieもPixmapもない = 表示失敗
        self.image_label.setPixmap(QPixmap()) # 念のため既存のPixmapをクリア

        # _load_and_display_image で具体的なエラーメッセージが self.image_label.text() に
        # 設定されているはずなので、それをそのまま表示する。
        # もし _load_and_display_image でテキストが設定されなかった場合 (ロジックの漏れなど) のために、
        # フォールバックメッセージを用意する。
        if not self.image_label.text(): # _load_and_display_image でメッセージが設定されなかった場合
            if self.image_path and not os.path.exists(self.image_path):
                self.image_label.setText(f"指定された画像ファイルが見つかりません:\n{os.path.basename(self.image_path)}")
            elif self.image_path and os.path.exists(self.image_path): # ファイルは存在するが読み込めなかった
                self.image_label.setText(f"画像の読み込みに失敗しました:\n{os.path.basename(self.image_path)}")
            elif self.image_path is None and self.all_image_paths:
                 self.image_label.setText("表示する画像が選択されていません。")
            elif not self.all_image_paths:
                 self.image_label.setText("表示できる画像がありません。")
            else:
                self.image_label.setText("画像の表示に失敗しました。")
        # else: _load_and_display_image で設定されたメッセージが既に表示されているので何もしない

    def resizeEvent(self, event):
        """Handle resize events to rescale the image."""
        super().resizeEvent(event)
        if (self.movie and self.movie.isValid()) or self.preview_mode == PREVIEW_MODE_FIT:
            self._update_image_display()
        # For ORIGINAL_ZOOM mode, dialog resize doesn't change image scale, only viewport.

    def wheelEvent(self, event):
        if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            # 動画再生中はズーム操作を無効化
            if self.movie and self.movie.isValid():
                event.ignore()
                return

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
            # 動画再生中はパン操作を無効化
            if self.movie and self.movie.isValid():
                super().mousePressEvent(event) # 親クラスの処理に任せる
                return

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
            # 動画再生中はパン操作を無効化 (drag_start_posがセットされないので通常ここには来ないはずだが念のため)
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
            # 動画再生中はパン操作を無効化
            if self.movie and self.movie.isValid():
                super().mouseReleaseEvent(event)
                return

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
            event.accept() # ★ イベントを消費
        elif key == Qt.Key.Key_Left:
            self.show_previous_image()
            event.accept() # ★ イベントを消費
        elif key == Qt.Key.Key_Right or key == Qt.Key.Key_Space: # Space for next image
            self.show_next_image()
            event.accept() # ★ イベントを消費
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.movie and self.movie.state() == QMovie.MovieState.Running:
            try:
                self.movie.frameChanged.disconnect(self._update_movie_frame)
            except TypeError:
                pass
            self.movie.stop()
            logger.debug("FullImageDialog closing, stopped QMovie.")
        super().closeEvent(event)

    def _update_movie_frame(self): # frame_number 引数は QMovie.frameChanged から渡されるが、ここでは使わない
        """QMovieの現在のフレームをスケーリングしてQLabelに表示する。"""
        if self.movie and self.movie.isValid() and self.image_label:
            current_frame_pixmap = self.movie.currentPixmap()
            if not current_frame_pixmap.isNull():
                if self.preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM:
                    # 原寸表示モードの場合
                    # 動画のズームは無効化されているため、scale_factor は実質1.0として扱う
                    original_size = current_frame_pixmap.size()
                    self.image_label.setFixedSize(original_size) # QLabelを動画の原寸に設定
                    self.image_label.setPixmap(current_frame_pixmap) # Pixmapも原寸で表示
                else: # PREVIEW_MODE_FIT
                    # フィット表示モードの場合
                    target_label_size = self.image_label.size() # QLabelの現在のサイズに合わせる
                    scaled_pixmap = current_frame_pixmap.scaled(
                        target_label_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.image_label.setPixmap(scaled_pixmap)


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
