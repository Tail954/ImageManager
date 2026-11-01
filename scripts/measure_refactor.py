"""Isolated reference measurement; run once per source tree with the same Python.

This small synthetic sample is a smoke benchmark, not a production performance claim.
No application settings or images outside the temporary directory are modified.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import hashlib
import logging
import os
from pathlib import Path
import sys
import shutil
import tempfile
import time


def peak_memory_mb():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return round(counters.PeakWorkingSetSize / 1024 ** 2, 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--images", type=Path, help="Copy supplied images to the isolated test directory")
    args = parser.parse_args()
    source = args.source.resolve()
    screenshot = args.screenshot.resolve() if args.screenshot else None
    supplied = args.images.resolve() if args.images else None
    originals = sorted(path for path in supplied.iterdir()
                       if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")) if supplied else []
    fingerprints = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals}
    if supplied and not originals:
        raise ValueError("No supported images in the supplied directory")
    sys.path.insert(0, str(source))
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    logging.disable(logging.CRITICAL)
    from PIL import Image, PngImagePlugin
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont, QFontDatabase
    from src.main_window import MainWindow

    original_cwd = Path.cwd()
    # Keep temp files within the writable workspace even in restricted environments.
    with tempfile.TemporaryDirectory(prefix="measurement-", dir=original_cwd) as temporary:
        os.chdir(temporary)
        try:
            folder = Path(temporary) / "images"
            folder.mkdir()
            for path in originals:
                shutil.copy2(path, folder / path.name)
            for number in range(0 if supplied else 48):
                info = PngImagePlugin.PngInfo()
                info.add_text("parameters", f"{'forest' if number % 2 else 'city'}, sunset\nNegative prompt: blur\nSteps: 20, Sampler: Euler, CFG scale: 7, Seed: {number}")
                with Image.new("RGB", (512, 512), (number * 5 % 255, 100, 180)) as image:
                    image.save(folder / f"sample-{number:03}.png", pnginfo=info)
            app = QApplication([])
            # The offscreen Windows platform may not discover installed fonts.
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/meiryo.ttc"
            if font_path.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    app.setFont(QFont(families[0], 9))
            window = MainWindow()
            decoded = []
            if hasattr(window, "thumbnail_controller"):
                window.thumbnail_controller.thumbnailReady.connect(
                    lambda generation, path, image, metadata: decoded.append(image is not None and not image.isNull()))
            else:
                original_update = window.update_thumbnail_item
                def record_thumbnail(item, image, metadata):
                    decoded.append(image is not None and not image.isNull())
                    original_update(item, image, metadata)
                window.update_thumbnail_item = record_thumbnail
            window.delete_empty_folders_enabled = False
            window.show()
            app.processEvents()
            start = time.perf_counter()
            window.load_thumbnails_from_folder(str(folder))
            deadline = start + 30
            while window.is_loading_thumbnails and time.perf_counter() < deadline:
                app.processEvents()
                time.sleep(0.001)
            if window.is_loading_thumbnails:
                raise RuntimeError("Thumbnail load timed out")
            load_seconds = time.perf_counter() - start
            app.processEvents()
            source_rows = window.ui_manager.source_thumbnail_model.rowCount()
            expected_count = len(originals) if supplied else 48
            if source_rows != expected_count:
                raise AssertionError(f"Expected {expected_count} thumbnails, received {source_rows}")
            if len(decoded) != expected_count or not all(decoded):
                raise AssertionError(f"Only {sum(decoded)}/{expected_count} thumbnails decoded")
            filter_start = time.perf_counter()
            for _ in range(10):
                window.ui_manager.positive_prompt_filter_edit.setText("forest")
                window.apply_filters(preserve_selection=True)
                window.ui_manager.positive_prompt_filter_edit.setText("")
                window.apply_filters(preserve_selection=True)
            filter_ms = (time.perf_counter() - filter_start) * 1000 / 20
            peak_mb = peak_memory_mb()
            preview_count = 0
            metadata_fingerprint = None
            if supplied:
                from src.full_image_dialog import FullImageDialog
                from src.constants import PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM, METADATA_ROLE
                metadata = {}
                source_model = window.ui_manager.source_thumbnail_model
                for row in range(source_rows):
                    item = source_model.item(row)
                    record = item.data(METADATA_ROLE)
                    if not isinstance(record, dict):
                        raise AssertionError("Missing metadata result")
                    metadata[item.text()] = record
                metadata_fingerprint = hashlib.sha256(
                    json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
                paths = [str(folder / path.name) for path in originals]
                for mode in (PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM):
                    dialog = FullImageDialog(paths, 0, preview_mode=mode)
                    try:
                        for index in range(len(paths)):
                            if index:
                                dialog.show_next_image()
                            app.processEvents()
                            preview = dialog.preview_widget
                            if preview.pixmap.isNull() and (preview.movie is None or not preview.movie.isValid()):
                                raise AssertionError(f"Preview failed for {Path(paths[index]).name} ({mode})")
                            preview_count += 1
                    finally:
                        dialog.close()
            if screenshot:
                if hasattr(window, "_favorite_add"):
                    window._favorite_add()
                app.processEvents()
                if not window.grab().save(str(screenshot)):
                    raise RuntimeError("Could not save screenshot")
            result = {"source": str(source), "images": expected_count, "source_rows": source_rows,
                      "load_seconds": round(load_seconds, 4),
                      "filter_mean_ms": round(filter_ms, 3), "peak_working_set_mb": peak_mb,
                      "preview_checks": preview_count, "decoded_thumbnails": sum(decoded),
                      "metadata_sha256": metadata_fingerprint}
            window.close()
            deadline = time.perf_counter() + 10
            while window.isVisible() and time.perf_counter() < deadline:
                app.processEvents()
                time.sleep(0.001)
            if window.isVisible():
                raise RuntimeError("Window did not close")
            app.processEvents()
            print(json.dumps(result))
        finally:
            os.chdir(original_cwd)
            if any(hashlib.sha256(path.read_bytes()).hexdigest() != expected for path, expected in fingerprints.items()):
                raise AssertionError("Supplied image contents changed")


if __name__ == "__main__":
    main()
