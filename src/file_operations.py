"""File operation service with immutable requests and explicit thread lifetime."""
import logging
import os
import re
import shutil
import threading

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from .file_operation_types import FileOperationRequest, FileOperationResult, FileSuccess

logger = logging.getLogger(__name__)


class FileOperationsWorker(QObject):
    progress = pyqtSignal(int, int, int)
    result = pyqtSignal(object)

    def __init__(self, request):
        super().__init__()
        self.request = request
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    @pyqtSlot()
    def run(self):
        request = self.request
        successes, errors = [], []
        status = 'completed'
        try:
            if request.operation_type not in ('move', 'copy'):
                raise ValueError(f'Unknown operation type: {request.operation_type}')
            if not os.path.isdir(request.destination_folder):
                raise OSError(f'Destination folder does not exist: {request.destination_folder}')
            next_number = 1
            if request.operation_type == 'copy':
                try:
                    numbers = [int(match.group(1)) for name in os.listdir(request.destination_folder)
                               if os.path.isfile(os.path.join(request.destination_folder, name))
                               and (match := re.match(r'^(\d+)_', name))]
                    next_number = max(numbers, default=0) + 1
                except OSError as exc:
                    raise OSError(f'Could not read destination folder contents for numbering: {exc}') from exc
            for index, source in enumerate(request.source_paths):
                if self._stop.is_set():
                    status = 'cancelled'
                    break
                name = os.path.basename(source)
                try:
                    if not os.path.exists(source):
                        raise FileNotFoundError(f'Source file not found: {name}')
                    if request.operation_type == 'copy':
                        dest = os.path.join(request.destination_folder, f'{next_number:03}_{name}')
                        while os.path.exists(dest):
                            next_number += 1
                            dest = os.path.join(request.destination_folder, f'{next_number:03}_{name}')
                        shutil.copy2(source, dest)
                        next_number += 1
                    else:
                        stem, ext = os.path.splitext(name)
                        dest = os.path.join(request.destination_folder, name)
                        counter = 1
                        while os.path.exists(dest):
                            dest = os.path.join(request.destination_folder, f'{stem}_{counter}{ext}')
                            counter += 1
                        shutil.move(source, dest)
                    successes.append(FileSuccess(source, dest))
                except Exception as exc:
                    logger.warning('File operation failed for %s: %s', source, exc)
                    errors.append(str(exc))
                self.progress.emit(request.operation_id, index + 1, len(request.source_paths))
            else:
                if self._stop.is_set() and len(successes) + len(errors) < len(request.source_paths):
                    status = 'cancelled'
        except Exception as exc:
            logger.exception('File operation failed')
            errors.append(str(exc))
            status = 'error'
        self.result.emit(FileOperationResult(request.operation_id, request.operation_type, status,
                                             request.destination_folder, tuple(successes), tuple(errors)))


class FileOperations(QObject):
    progress = pyqtSignal(int, int, int)
    result = pyqtSignal(object)
    idle = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None

    def start(self, request: FileOperationRequest) -> bool:
        if self.is_busy():
            return False
        request = FileOperationRequest(request.operation_id, request.operation_type,
                                       tuple(request.source_paths), request.destination_folder)
        thread = QThread(self)
        worker = FileOperationsWorker(request)
        self._thread, self._worker = thread, worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.result.connect(self._on_result)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_idle)
        thread.start()
        return True

    @pyqtSlot(object)
    def _on_result(self, result):
        self.result.emit(result)
        self._thread.quit()

    @pyqtSlot()
    def _on_idle(self):
        thread = self._thread
        self._worker = self._thread = None
        thread.deleteLater()
        self.idle.emit()

    def stop_operation(self):
        if self._worker is not None:
            self._worker.stop()

    def is_busy(self):
        return self._thread is not None
