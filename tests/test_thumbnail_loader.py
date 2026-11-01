"""Thumbnail worker contract: immutable paths and value-only results."""

import threading
from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor

from PIL import Image
from PyQt6.QtTest import QSignalSpy

from src.thumbnail_loader import ThumbnailLoaderThread


def _image(path, color=(20, 30, 40)):
    Image.new("RGB", (24, 18), color).save(path)


def test_worker_emits_generation_path_image_and_metadata(tmp_path, qapplication):
    image_path = tmp_path / "sample.png"
    _image(image_path)
    worker = ThumbnailLoaderThread(7, [str(image_path)], 96)
    loaded = QSignalSpy(worker.thumbnailLoaded)
    progress = QSignalSpy(worker.progressUpdated)

    worker.start()
    assert worker.wait(3000)
    qapplication.processEvents()

    assert len(loaded) == 1
    assert loaded[0][0] == 7
    assert loaded[0][1] == str(image_path)
    assert loaded[0][2] is not None
    assert loaded[0][3]["filename_for_sort"] == "sample.png"
    assert len(progress) == 1
    assert progress[0] == [7, 1, 1]


def test_worker_reports_broken_image_as_value_error(tmp_path, qapplication):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    worker = ThumbnailLoaderThread(3, [str(broken)], 96)
    loaded = QSignalSpy(worker.thumbnailLoaded)
    errors = QSignalSpy(worker.imageError)

    worker.start()
    assert worker.wait(3000)
    qapplication.processEvents()

    assert len(loaded) == 1
    assert loaded[0][0:2] == [3, str(broken)]
    assert loaded[0][2] is None
    assert len(errors) == 1
    assert errors[0][0:2] == [3, str(broken)]
    assert errors[0][2]


def test_worker_snapshots_paths_at_construction(tmp_path, qapplication):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _image(first)
    _image(second)
    paths = [str(first)]
    worker = ThumbnailLoaderThread(9, paths, 96)
    paths.append(str(second))
    loaded = QSignalSpy(worker.thumbnailLoaded)

    worker.start()
    assert worker.wait(3000)
    qapplication.processEvents()

    assert worker.file_paths == (str(first),)
    assert len(loaded) == 1
    assert loaded[0][1] == str(first)


def test_stop_cancels_queued_decodes_and_does_not_emit_stale_results(
    tmp_path, qapplication, mocker,
):
    entered = threading.Event()
    release = threading.Event()
    paths = [str(tmp_path / f"image-{index}.png") for index in range(30)]
    worker = ThumbnailLoaderThread(11, paths, 96)
    calls = []
    submitted = []

    class TrackingExecutor:
        def __init__(self, *args, **kwargs):
            self.executor = RealThreadPoolExecutor(*args, **kwargs)

        def submit(self, function, *args, **kwargs):
            submitted.append(args[0])
            return self.executor.submit(function, *args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.executor.shutdown(wait=True, cancel_futures=True)

    mocker.patch("src.thumbnail_loader.ThreadPoolExecutor", TrackingExecutor)

    def controlled_decode(path):
        calls.append(path)
        entered.set()
        release.wait(2)
        return path, None, {}, None

    mocker.patch.object(worker, "_decode", side_effect=controlled_decode)
    loaded = QSignalSpy(worker.thumbnailLoaded)
    worker.start()
    assert entered.wait(2)
    worker.stop()
    release.set()
    assert worker.wait(3000)
    qapplication.processEvents()

    assert len(submitted) <= 16  # eight workers and at most two batches outstanding.
    assert len(calls) <= len(submitted)
    assert len(loaded) == 0
