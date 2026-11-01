"""GUI-thread owner of thumbnail model, index, metadata and load generations."""

import os

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QStandardItem

from .constants import METADATA_ROLE
from .thumbnail_loader import ThumbnailLoaderThread


class ThumbnailController(QObject):
    thumbnailReady = pyqtSignal(int, str, object, dict)
    progressChanged = pyqtSignal(int, int, int)
    completed = pyqtSignal(int)
    idle = pyqtSignal()

    def __init__(self, source_model, proxy_model, parent=None):
        super().__init__(parent)
        self.source_model = source_model
        self.proxy_model = proxy_model
        self._index = {}
        self._paths = ()
        self._metadata = {}
        self._hidden_paths = set()
        self._generation = 0
        self._worker = None
        self._pending = None
        self._shutting_down = False

    @property
    def metadata_cache(self):
        return self._metadata

    def item_for_path(self, path):
        return self._index.get(path)

    def paths(self):
        return self._paths

    def metadata_for(self, path):
        return self._metadata.get(path)

    def cache_metadata(self, path, metadata):
        self._metadata[path] = metadata
        item = self._index.get(path)
        if item is not None:
            item.setData(metadata, METADATA_ROLE)

    def replace(self, file_paths, target_size):
        if self._shutting_down:
            raise RuntimeError("ThumbnailController is shutting down")
        self._generation += 1
        generation = self._generation
        if self._worker is not None:
            self._worker.stop()
        self._pending = (generation, tuple(file_paths), target_size)
        self.source_model.clear()
        self._index.clear()
        self._paths = tuple(file_paths)
        self._metadata.clear()
        self._hidden_paths.clear()
        self.proxy_model.set_hidden_paths(self._hidden_paths)
        self.proxy_model.invalidateFilter()
        placeholder = QPixmap(target_size, target_size)
        placeholder.fill(Qt.GlobalColor.transparent)
        icon = QIcon(placeholder)
        for path in self._paths:
            item = QStandardItem(os.path.basename(path))
            item.setEditable(False)
            item.setIcon(icon)
            item.setData(path, Qt.ItemDataRole.UserRole)
            self.source_model.appendRow(item)
            self._index[path] = item
        QTimer.singleShot(0, self._start_pending)
        return generation

    def _start_pending(self):
        if self._worker is not None or self._pending is None or self._shutting_down:
            return
        generation, paths, size = self._pending
        self._pending = None
        if not paths:
            QTimer.singleShot(0, lambda g=generation: self._finish_empty(g))
            return
        worker = ThumbnailLoaderThread(generation, paths, size, self)
        self._worker = worker
        worker.thumbnailLoaded.connect(self._thumbnail_loaded)
        worker.progressUpdated.connect(self._progress_updated)
        worker.finished.connect(lambda w=worker, g=generation: self._worker_finished(w, g))
        worker.start()

    def _thumbnail_loaded(self, generation, path, image, metadata):
        if self._shutting_down or generation != self._generation:
            return
        item = self._index.get(path)
        if item is None:
            return
        if image is not None:
            item.setIcon(QIcon(QPixmap.fromImage(image)))
        self.cache_metadata(path, metadata)
        item.setToolTip(f"場所: {os.path.dirname(path)}")
        self.thumbnailReady.emit(generation, path, image, metadata)

    def _progress_updated(self, generation, processed, total):
        if not self._shutting_down and generation == self._generation:
            self.progressChanged.emit(generation, processed, total)

    def _worker_finished(self, worker, generation):
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()
        if self._pending is not None:
            QTimer.singleShot(0, self._start_pending)
        elif not self._shutting_down and generation == self._generation:
            self.completed.emit(generation)
        if self.is_idle():
            self.idle.emit()

    def _finish_empty(self, generation):
        if not self._shutting_down and generation == self._generation and self._pending is None and self._worker is None:
            self.completed.emit(generation)
            self.idle.emit()

    def remove_paths(self, paths):
        rows = []
        for path in set(paths):
            item = self._index.pop(path, None)
            self._metadata.pop(path, None)
            if item is not None:
                rows.append(item.row())
        for row in sorted(rows, reverse=True):
            self.source_model.removeRow(row)
        self._paths = tuple(path for path in self._paths if path in self._index)

    def shutdown(self):
        self._shutting_down = True
        self._pending = None
        if self._worker is not None:
            self._worker.stop()
        else:
            self.idle.emit()

    def is_idle(self):
        return self._worker is None and self._pending is None

    def waiting_for_previous_load(self):
        return self._worker is not None and self._pending is not None
