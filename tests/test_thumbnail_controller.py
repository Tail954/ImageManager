"""Generation cancellation, bounded handoff, and model ownership."""

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QStandardItemModel

from src.metadata_filter_proxy_model import MetadataFilterProxyModel
from src.thumbnail_controller import ThumbnailController


class _ControlledWorker(QObject):
    thumbnailLoaded = pyqtSignal(int, str, object, dict)
    progressUpdated = pyqtSignal(int, int, int)
    finished = pyqtSignal()
    instances = []

    def __init__(self, generation, paths, target_size, parent=None):
        super().__init__(parent)
        self.generation = generation
        self.paths = tuple(paths)
        self.target_size = target_size
        self.stopped = False
        self.started = False
        type(self).instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def finish(self):
        self.finished.emit()


def _controller(qapplication, mocker):
    _ControlledWorker.instances.clear()
    mocker.patch("src.thumbnail_controller.ThumbnailLoaderThread", _ControlledWorker)
    source = QStandardItemModel()
    proxy = MetadataFilterProxyModel()
    proxy.setSourceModel(source)
    controller = ThumbnailController(source, proxy)
    return controller, source


def test_only_latest_pending_generation_starts_and_old_delivery_is_ignored(
    qapplication, mocker,
):
    controller, source = _controller(qapplication, mocker)
    ready, progress, completed, idle = [], [], [], []
    controller.thumbnailReady.connect(lambda *args: ready.append(args))
    controller.progressChanged.connect(lambda *args: progress.append(args))
    controller.completed.connect(completed.append)
    controller.idle.connect(lambda: idle.append(True))

    generation_a = controller.replace(["A.png"], 96)
    qapplication.processEvents()
    worker_a = _ControlledWorker.instances[-1]
    generation_b = controller.replace(["B.png"], 96)
    generation_c = controller.replace(["C.png"], 96)
    qapplication.processEvents()

    assert worker_a.stopped
    assert generation_b < generation_c
    assert controller.paths() == ("C.png",)
    assert controller.is_idle() is False
    assert len(_ControlledWorker.instances) == 1  # B was superseded before worker start.

    worker_a.thumbnailLoaded.emit(generation_a, "A.png", object(), {"positive_prompt": "old"})
    worker_a.progressUpdated.emit(generation_a, 1, 1)
    worker_a.finish()
    qapplication.processEvents()

    worker_c = _ControlledWorker.instances[-1]
    assert worker_c.paths == ("C.png",)
    assert len(_ControlledWorker.instances) == 2
    assert ready == [] and progress == [] and completed == []
    assert controller.is_idle() is False

    metadata = {"positive_prompt": "new"}
    worker_c.thumbnailLoaded.emit(generation_c, "C.png", None, metadata)
    worker_c.progressUpdated.emit(generation_c, 1, 1)
    worker_c.finish()
    qapplication.processEvents()

    assert [entry[0:2] for entry in ready] == [(generation_c, "C.png")]
    assert progress == [(generation_c, 1, 1)]
    assert completed == [generation_c]
    assert len(idle) == 1
    assert controller.metadata_for("C.png") == metadata
    assert controller.item_for_path("A.png") is None
    assert source.rowCount() == 1
    assert controller.is_idle()


def test_empty_generation_completes_asynchronously_once(qapplication, mocker):
    controller, _source = _controller(qapplication, mocker)
    completed, idle = [], []
    controller.completed.connect(completed.append)
    controller.idle.connect(lambda: idle.append(True))

    generation = controller.replace([], 96)

    assert completed == []
    qapplication.processEvents()
    qapplication.processEvents()
    assert completed == [generation]
    assert idle == [True]
    assert controller.is_idle()


def test_shutdown_waits_for_worker_finished_and_remove_is_idempotent(qapplication, mocker):
    controller, source = _controller(qapplication, mocker)
    idle = []
    controller.idle.connect(lambda: idle.append(True))
    generation = controller.replace(["one.png", "two.png"], 96)
    qapplication.processEvents()
    worker = _ControlledWorker.instances[-1]
    assert generation > 0

    controller.remove_paths(["one.png", "one.png"])
    assert controller.paths() == ("two.png",)
    assert source.rowCount() == 1
    controller.remove_paths(["one.png"])
    assert source.rowCount() == 1

    controller.shutdown()
    assert worker.stopped
    assert controller.is_idle() is False
    assert idle == []
    worker.finish()
    qapplication.processEvents()
    assert controller.is_idle()
    assert idle == [True]
