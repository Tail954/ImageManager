"""Read-only discovery of empty subfolders."""
import logging
import os

logger = logging.getLogger(__name__)


def is_dir_empty_recursive(path: str) -> bool:
    try:
        with os.scandir(path) as scan:
            entries = list(scan)
        for entry in entries:
            if entry.is_file():
                return False
            if entry.is_dir() and not is_dir_empty_recursive(entry.path):
                return False
        return True
    except OSError as exc:
        logger.warning("Could not scan directory '%s': %s", path, exc)
        return False


def find_empty_subfolders(parent_dir: str) -> list[str]:
    with os.scandir(parent_dir) as scan:
        return [entry.path for entry in scan
                if entry.is_dir() and is_dir_empty_recursive(entry.path)]
