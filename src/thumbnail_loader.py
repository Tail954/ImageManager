# src/thumbnail_loader.py
import logging
import os # For os.path.getmtime and os.cpu_count()
import concurrent.futures # For ThreadPoolExecutor
import threading
from PyQt6.QtCore import QThread, pyqtSignal, QRectF, Qt, QPointF # QPointF を追加
from PIL import Image
try:
    from PIL import ImageQt
except ImportError:
    ImageQt = None

from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QImage, QPolygonF # QPolygonF を追加
# Import shared metadata extraction logic
from .metadata_utils import extract_image_metadata

logger = logging.getLogger(__name__)

class ThumbnailLoaderThread(QThread):
    thumbnailLoaded = pyqtSignal(object, object, dict) # item, q_image, metadata_dict
    progressUpdated = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(self, file_paths, items_to_process, target_size):
        super().__init__()
        self.file_paths = file_paths
        self.items_to_process = items_to_process # List of QStandardItem
        self.target_size = target_size
        self._is_running = True
        self._processed_count = 0
        self._lock = threading.Lock() # Lock for atomically updating _processed_count

    def _process_single_image(self, file_path, item):
        """Processes a single image: creates thumbnail and extracts metadata."""
        if not self._is_running:
            # logger.debug(f"_process_single_image: Stop requested for {file_path}, returning default metadata.")
            # Return default/empty data if stopping
            return item, None, {
                'positive_prompt': '',
                'negative_prompt': '',
                'generation_info': '',
                'filename_for_sort': os.path.basename(file_path).lower() if file_path and isinstance(file_path, str) else '',
                'update_timestamp': 0.0
            }

        q_image = None
        # まずメタデータを抽出
        # logger.debug(f"_process_single_image: Extracting metadata for {file_path}")
        metadata_dict = extract_image_metadata(file_path)
        # logger.debug(f"_process_single_image: Metadata from extract_image_metadata for {file_path}: {metadata_dict}")

        # 抽出された辞書にソート用キーを追加
        filename_for_sort = os.path.basename(file_path).lower()
        update_timestamp = 0.0
        try:
            update_timestamp = os.path.getmtime(file_path)
        except FileNotFoundError:
            logger.warning(f"File not found for mtime in _process_single_image: {file_path}, using 0.0.")
        except Exception as e:
            logger.error(f"Error getting mtime for {file_path} in _process_single_image: {e}. Using 0.0.")
        
        metadata_dict['filename_for_sort'] = filename_for_sort
        metadata_dict['update_timestamp'] = update_timestamp
        # logger.debug(f"_process_single_image: Metadata after adding sort keys for {file_path}: {metadata_dict}")
        
        try:
            img = Image.open(file_path)
            is_animated_webp = False
            if img.format == "WEBP":
                try:
                    if img.is_animated: # Pillow 9.1.0以降
                        is_animated_webp = True
                except AttributeError: # 古いPillowではis_animatedがない場合がある
                    if hasattr(img, 'n_frames') and img.n_frames > 1:
                        is_animated_webp = True
            
            if is_animated_webp:
                logger.debug(f"アニメーションWebPを検出: {file_path}。アイコンを生成します。")
                img.seek(0) # 最初のフレームを選択

                # 最初のフレームをサムネイルサイズにリサイズ
                img.thumbnail((self.target_size, self.target_size))

                # Pillow Image を QImage に変換
                if img.mode == "RGBA":
                    base_q_image = ImageQt.ImageQt(img)
                elif img.mode == "RGB":
                    base_q_image = ImageQt.ImageQt(img.convert("RGBA"))
                else: # Other modes like P, L, 1, etc.
                    base_q_image = ImageQt.ImageQt(img.convert("RGBA"))

                # QImage から QPixmap を作成して、その上にアイコンを描画
                pixmap = QPixmap.fromImage(base_q_image)
                
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)

                # アイコンの描画 (例: 右下に小さな再生ボタン)
                icon_base_size = max(16, self.target_size // 6) # アイコンの基準サイズ
                padding = self.target_size // 20 # パディングをサムネイルサイズに比例させる
                
                icon_rect_x = pixmap.width() - icon_base_size - padding
                icon_rect_y = pixmap.height() - icon_base_size - padding
                icon_rect = QRectF(icon_rect_x, icon_rect_y, icon_base_size, icon_base_size)

                # Vマークアイコンの描画
                # 背景 (半透明の円)
                painter.setBrush(QColor(0, 0, 0, 120)) # 少し濃いめの半透明黒
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(icon_rect)

                # 「V」の文字を描画
                painter.setFont(QFont("Arial", int(icon_base_size * 0.7), QFont.Weight.Bold)) # アイコンサイズに合わせたフォントサイズ
                painter.setPen(QColor("white"))
                # テキストをicon_rectの中央に描画
                # QFontMetrics を使って正確な中央揃えも可能ですが、ここでは単純なAlignCenterを使用
                painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "V")

                painter.end()
                q_image = pixmap.toImage() # QImageに変換
            else:
                # 静止画の場合は通常のサムネイル生成
                img.thumbnail((self.target_size, self.target_size))
                if img.mode == "RGBA":
                    q_image = ImageQt.ImageQt(img)
                elif img.mode == "RGB":
                    q_image = ImageQt.ImageQt(img.convert("RGBA")) # Convert RGB to RGBA
                else: # Other modes like P, L, 1, etc.
                    q_image = ImageQt.ImageQt(img.convert("RGBA")) # Convert to RGBA as a general fallback

            return item, q_image, metadata_dict
        except Image.DecompressionBombError:
            logger.error(f"サムネイル生成エラー (DecompressionBombError): {file_path}")
            return item, None, metadata_dict
        except FileNotFoundError:
            logger.error(f"サムネイル生成/メタデータ抽出エラー (ファイルが見つかりません): {file_path}")
            # metadata_dict には既にソート用キーと抽出試行済みのメタデータが入っている
            return item, None, metadata_dict
        except Exception as e:
            logger.error(f"サムネイル生成/メタデータ抽出エラー ({file_path}): {e}", exc_info=True)
            # metadata_dict には既にソート用キーと抽出試行済みのメタデータが入っている
            return item, None, metadata_dict

    def run(self):
        if ImageQt is None:
            logger.error("ImageQt module not found in thread. Cannot generate thumbnails.")
            self.finished.emit()
            return

        total_files = len(self.file_paths)
        if total_files == 0: # No files to process
            self.finished.emit()
            return
        
        with self._lock: # Ensure _processed_count is reset safely
            self._processed_count = 0

        # Determine number of workers. os.cpu_count() can be None.
        cpu_cores = os.cpu_count()
        if cpu_cores is None or cpu_cores < 1:
            num_workers = 1 # Fallback if os.cpu_count() fails or returns invalid
        else:
            num_workers = cpu_cores
        
        # Adjust num_workers: no more than total_files, and at least 1.
        num_workers = max(1, min(num_workers, total_files))

        logger.info(f"ThumbnailLoaderThread: Using up to {num_workers} workers for {total_files} files.")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = []

            for i, file_path in enumerate(self.file_paths):
                if not self._is_running:
                    logger.info("ThumbnailLoaderThread: Stop requested, halting submission of new tasks.")
                    break 
                item = self.items_to_process[i]
                future = executor.submit(self._process_single_image, file_path, item)
                futures.append(future)

            for future in concurrent.futures.as_completed(futures):
                if not self._is_running:
                    logger.info("ThumbnailLoaderThread: Stop requested during task completion processing.")
                    # Note: Already submitted tasks to as_completed will continue to be processed here
                    # until this loop naturally finishes or this break is hit repeatedly.
                    break 
                
                try:
                    item_result, q_image_result, metadata_result = future.result()
                    # Ensure item_result is valid before emitting
                    if item_result is not None:
                         self.thumbnailLoaded.emit(item_result, q_image_result, metadata_result)
                    else:
                        logger.warning(f"Skipping thumbnailLoaded.emit due to None item from future for a task.")

                except concurrent.futures.CancelledError:
                    logger.info("A thumbnail processing task was cancelled.")
                except Exception as e: # Catch errors from future.result() or task execution
                    # This catch is for errors from future.result() itself, or if _process_single_image re-raises
                    logger.error(f"Error retrieving result from future: {e}", exc_info=True)
                    # We don't know which item this was for easily unless we used future_to_item map
                    # And even then, emitting an error for a specific item might be complex here.
                    # _process_single_image should handle its own errors and return (item, None, metadata).

                with self._lock:
                    self._processed_count += 1
                    current_processed_count = self._processed_count
                
                self.progressUpdated.emit(current_processed_count, total_files)
        
        logger.info("ThumbnailLoaderThread: Processing loop finished. Emitting finished signal.")
        self.finished.emit()

    def stop(self):
        logger.info("ThumbnailLoaderThread.stop() called. Setting _is_running to False.")
        self._is_running = False
        # The ThreadPoolExecutor used with a 'with' statement will automatically call
        # shutdown(wait=True) when the 'with' block exits.
        # The _is_running flag is checked within _process_single_image and
        # before submitting new tasks, and in the as_completed loop.
        # This provides a cooperative way to stop processing.
