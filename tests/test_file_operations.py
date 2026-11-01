import os

import pytest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtTest import QSignalSpy

from src.file_operation_types import FileOperationRequest, FileOperationResult
from src.file_operations import FileOperations, FileOperationsWorker


def make_request(kind, sources, destination, operation_id=7):
    return FileOperationRequest(operation_id, kind, tuple(map(str, sources)), str(destination))


def run_worker(request):
    worker = FileOperationsWorker(request)
    progress = QSignalSpy(worker.progress)
    results = QSignalSpy(worker.result)
    worker.run()
    assert len(results) == 1
    return results[0][0], progress


def test_move_single_success_and_result_contract(tmp_path):
    source = tmp_path / "source" / "one.txt"
    destination = tmp_path / "destination"
    source.parent.mkdir()
    destination.mkdir()
    source.write_text("data", encoding="utf-8")

    result, progress = run_worker(make_request("move", [source], destination))

    assert isinstance(result, FileOperationResult)
    assert (result.operation_id, result.operation_type, result.status) == (7, "move", "completed")
    assert [(s.source_path, s.destination_path) for s in result.successes] == [
        (str(source), str(destination / "one.txt"))
    ]
    assert result.errors == ()
    assert list(progress[0]) == [7, 1, 1]
    assert not source.exists()
    assert (destination / "one.txt").read_text(encoding="utf-8") == "data"


def test_move_collision_uses_legacy_suffix(tmp_path):
    source = tmp_path / "source" / "image.png"
    destination = tmp_path / "destination"
    source.parent.mkdir()
    destination.mkdir()
    source.write_bytes(b"source")
    (destination / "image.png").write_bytes(b"existing")

    result, _ = run_worker(make_request("move", [source], destination))

    assert result.status == "completed"
    assert result.successes[0].destination_path == str(destination / "image_1.png")
    assert (destination / "image.png").read_bytes() == b"existing"
    assert (destination / "image_1.png").read_bytes() == b"source"


def test_copy_uses_selection_order_and_next_existing_number(tmp_path):
    destination = tmp_path / "destination"
    destination.mkdir()
    sources = [tmp_path / "b.png", tmp_path / "a.png"]
    for path in sources:
        path.write_bytes(path.name.encode())
    (destination / "007_old.png").write_bytes(b"old")

    result, progress = run_worker(make_request("copy", sources, destination, operation_id=9))

    assert result.status == "completed"
    assert [os.path.basename(s.destination_path) for s in result.successes] == [
        "008_b.png", "009_a.png"
    ]
    assert [os.path.basename(s.source_path) for s in result.successes] == ["b.png", "a.png"]
    assert list(progress[0]) == [9, 1, 2]
    assert list(progress[1]) == [9, 2, 2]
    assert all(path.exists() for path in sources)


def test_request_snapshots_mutable_source_list(tmp_path):
    source = ["one.png"]
    request = FileOperationRequest(1, "copy", source, str(tmp_path))
    source.append("two.png")
    assert request.source_paths == ("one.png",)


@pytest.mark.parametrize("source_mode", ["missing", "unreadable"])
def test_copy_records_source_failure_and_continues(tmp_path, monkeypatch, source_mode):
    destination = tmp_path / "destination"
    destination.mkdir()
    bad_source = tmp_path / "bad.png"
    good_source = tmp_path / "good.png"
    good_source.write_bytes(b"good")
    bad_path = str(bad_source)

    if source_mode == "unreadable":
        bad_source.write_bytes(b"unreadable")
        real_copy = __import__("shutil").copy2

        def fail_first(src, dst):
            if os.fspath(src) == bad_path:
                raise PermissionError("read denied")
            return real_copy(src, dst)

        monkeypatch.setattr("src.file_operations.shutil.copy2", fail_first)

    result, _ = run_worker(make_request("copy", [bad_path, good_source], destination))

    assert result.status == "completed"
    assert len(result.successes) == 1
    assert os.path.basename(result.successes[0].destination_path) == "001_good.png"
    assert len(result.errors) == 1


def test_invalid_destination_returns_error_result(tmp_path):
    source = tmp_path / "one.png"
    source.write_bytes(b"data")

    result, progress = run_worker(make_request("copy", [source], tmp_path / "missing"))

    assert result.status == "error"
    assert result.successes == ()
    assert result.errors
    assert len(progress) == 0


def test_cancel_keeps_successes_already_completed(tmp_path, monkeypatch):
    destination = tmp_path / "destination"
    destination.mkdir()
    sources = [tmp_path / "first.png", tmp_path / "second.png"]
    for path in sources:
        path.write_bytes(path.name.encode())
    worker = FileOperationsWorker(make_request("copy", sources, destination))
    real_copy = __import__("shutil").copy2
    calls = []

    def copy_then_cancel(src, dst):
        real_copy(src, dst)
        calls.append(src)
        worker.stop()

    monkeypatch.setattr("src.file_operations.shutil.copy2", copy_then_cancel)
    results = QSignalSpy(worker.result)
    worker.run()

    assert len(results) == 1
    result = results[0][0]
    assert result.status == "cancelled"
    assert len(result.successes) == 1
    assert result.successes[0].source_path == str(sources[0])
    assert (destination / "001_first.png").exists()
    assert not (destination / "002_second.png").exists()


def test_service_rejects_overlapping_request_and_releases_only_on_idle(qapplication, tmp_path):
    source = tmp_path / "source.png"
    destination = tmp_path / "destination"
    source.write_bytes(b"data")
    destination.mkdir()
    service = FileOperations()
    request = make_request("copy", [source], destination, operation_id=11)
    results = QSignalSpy(service.result)
    idle = QSignalSpy(service.idle)
    state_at_result = []
    service.result.connect(lambda _result: state_at_result.append(service.is_busy()))

    assert service.start(request)
    assert service.is_busy()
    assert not service.start(request)
    assert results.wait(5000)
    assert state_at_result == [True]
    assert service.is_busy()
    assert idle.wait(5000)
    assert not service.is_busy()
    assert len(results) == len(idle) == 1
