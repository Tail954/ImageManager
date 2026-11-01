"""Shared, isolated Qt test setup."""

import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(scope="session", autouse=True)
def qapplication():
    """Keep one QApplication alive for the full pytest session."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolate_app_settings(tmp_path, monkeypatch):
    """Prevent tests from reading or writing the user's project settings."""
    monkeypatch.chdir(tmp_path)
    # MainWindow constructs its store before loading settings. Redirect that
    # constructor too: changing CWD alone does not isolate its default path.
    import src.main_window as main_window_module
    from src.settings_store import SettingsStore

    monkeypatch.setattr(
        main_window_module,
        "SettingsStore",
        lambda: SettingsStore(tmp_path / "app_settings.json"),
    )
    # No test should send a real file to the operating system's trash.
    import send2trash

    monkeypatch.setattr(send2trash, "send2trash", lambda _path: None)
