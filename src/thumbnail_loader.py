"""Background image decoding; Qt model objects stay on the GUI thread."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import logging
import os
import threading

from PIL import Image, ImageQt
from PyQt6.QtCore import QThread, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter

from .metadata_utils import extract_image_metadata

logger = logging.getLogger(__name__)


class ThumbnailLoaderThread(QThread):
    thumbnailLoaded = pyqtSignal(int, str, object, dict)
    progressUpdated = pyqtSignal(int, int, int)
    imageError = pyqtSignal(int, str, str)

    def __init__(self, generation, file_paths, target_size, parent=None):
        super().__init__(parent)
        self.generation = generation
        self.file_paths = tuple(file_paths)
        self.target_size = target_size
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def _decode(self, path):
        metadata = extract_image_metadata(path)
        metadata["filename_for_sort"] = os.path.basename(path).lower()
        try:
            metadata["update_timestamp"] = os.path.getmtime(path)
        except OSError:
            metadata["update_timestamp"] = 0.0
        try:
            with Image.open(path) as source:
                animated = source.format == "WEBP" and getattr(source, "is_animated", False)
                if animated:
                    source.seek(0)
                source.thumbnail((self.target_size, self.target_size))
                with source.convert("RGBA") as image:
                    qimage = ImageQt.ImageQt(image).copy()
            if animated:
                painter = QPainter(qimage)
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    size = max(16, self.target_size // 6)
                    rect = QRectF(qimage.width() - size - self.target_size // 20,
                                  qimage.height() - size - self.target_size // 20,
                                  size, size)
                    painter.setBrush(QColor(0, 0, 0, 120))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(rect)
                    painter.setFont(QFont("Arial", max(8, int(size * 0.7)), QFont.Weight.Bold))
                    painter.setPen(QColor("white"))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "V")
                finally:
                    painter.end()
            return path, qimage, metadata, None
        except Exception as exc:
            logger.warning("Could not decode thumbnail %s: %s", path, exc)
            return path, None, metadata, str(exc)

    def run(self):
        total = len(self.file_paths)
        workers = max(1, min(8, os.cpu_count() or 1, total))
        limit = workers * 2
        pending = {}
        source = iter(self.file_paths)
        processed = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            while True:
                while not self._stop_event.is_set() and len(pending) < limit:
                    try:
                        path = next(source)
                    except StopIteration:
                        break
                    pending[pool.submit(self._decode, path)] = path
                if not pending:
                    break
                if self._stop_event.is_set():
                    for future in pending:
                        future.cancel()
                done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                for future in done:
                    path = pending.pop(future)
                    if future.cancelled():
                        continue
                    try:
                        _, image, metadata, error = future.result()
                    except Exception as exc:
                        logger.exception("Thumbnail worker failed: %s", path)
                        image, metadata, error = None, {}, str(exc)
                    if not self._stop_event.is_set():
                        self.thumbnailLoaded.emit(self.generation, path, image, metadata)
                        if error:
                            self.imageError.emit(self.generation, path, error)
                        processed += 1
                        self.progressUpdated.emit(self.generation, processed, total)
