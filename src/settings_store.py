"""Validated, atomic storage for the application's settings."""

from copy import deepcopy
import json
import logging
import os
import tempfile
from collections.abc import Mapping

from .constants import (
    APP_SETTINGS_FILE, DELETE_EMPTY_FOLDERS_ENABLED, DOUBLE_CLICK_ACTION,
    DOUBLE_CLICK_ACTION_VIEWER, DOUBLE_CLICK_ACTION_VIEWER_METADATA,
    FAVORITE_FOLDERS, INITIAL_SORT_ORDER_ON_FOLDER_SELECT,
    LAST_COPY_DESTINATION_FOLDER, LAST_MOVE_DESTINATION_FOLDER,
    MAIN_WINDOW_GEOMETRY, METADATA_DIALOG_GEOMETRY, PREVIEW_MODE_FIT,
    PREVIEW_MODE_ORIGINAL_ZOOM, RIGHT_CLICK_ACTION_MENU,
    RIGHT_CLICK_ACTION_METADATA, SORT_BY_LAST_SELECTED,
    SORT_BY_LOAD_ORDER_ALWAYS, TAG_PALETTE_GEOMETRY,
    TAG_PALETTE_SPLITTER_STATE, TAGS_FOLDER_PATH,
    THUMBNAIL_RIGHT_CLICK_ACTION, WC_COMMENT_OUTPUT_FORMAT,
    WC_FORMAT_BRACKET_COMMENT, WC_FORMAT_HASH_COMMENT,
)

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "thumbnail_size": 128,
    "image_preview_mode": PREVIEW_MODE_FIT,
    THUMBNAIL_RIGHT_CLICK_ACTION: RIGHT_CLICK_ACTION_METADATA,
    WC_COMMENT_OUTPUT_FORMAT: WC_FORMAT_HASH_COMMENT,
    "last_folder_path": None,
    "recursive_search": True,
    DELETE_EMPTY_FOLDERS_ENABLED: True,
    INITIAL_SORT_ORDER_ON_FOLDER_SELECT: SORT_BY_LOAD_ORDER_ALWAYS,
    "sort_button_id": 4,
    LAST_MOVE_DESTINATION_FOLDER: None,
    LAST_COPY_DESTINATION_FOLDER: None,
    DOUBLE_CLICK_ACTION: DOUBLE_CLICK_ACTION_VIEWER,
    TAGS_FOLDER_PATH: "",
    FAVORITE_FOLDERS: [],
}
_ENUMS = {
    "image_preview_mode": {PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM},
    THUMBNAIL_RIGHT_CLICK_ACTION: {RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU},
    WC_COMMENT_OUTPUT_FORMAT: {WC_FORMAT_HASH_COMMENT, WC_FORMAT_BRACKET_COMMENT},
    INITIAL_SORT_ORDER_ON_FOLDER_SELECT: {SORT_BY_LOAD_ORDER_ALWAYS, SORT_BY_LAST_SELECTED},
    DOUBLE_CLICK_ACTION: {DOUBLE_CLICK_ACTION_VIEWER, DOUBLE_CLICK_ACTION_VIEWER_METADATA},
}
_OPTIONAL_PATHS = {"last_folder_path", LAST_MOVE_DESTINATION_FOLDER, LAST_COPY_DESTINATION_FOLDER}
_GEOMETRIES = {MAIN_WINDOW_GEOMETRY, METADATA_DIALOG_GEOMETRY,
               TAG_PALETTE_GEOMETRY, TAG_PALETTE_SPLITTER_STATE}
_BOOLEANS = {"recursive_search", DELETE_EMPTY_FOLDERS_ENABLED}


def _valid(key, value):
    if key in _ENUMS:
        return type(value) is str and value in _ENUMS[key]
    if key in _BOOLEANS:
        return type(value) is bool
    if key == "thumbnail_size":
        return type(value) is int and value in (96, 128, 200)
    if key == "sort_button_id":
        return type(value) is int and value in range(5)
    if key in _OPTIONAL_PATHS:
        return value is None or (type(value) is str and bool(value))
    if key in _GEOMETRIES or key == TAGS_FOLDER_PATH:
        return type(value) is str
    if key == FAVORITE_FOLDERS:
        # FavoriteFolders discards invalid individual entries on restoration.
        return type(value) is list
    return True


class SettingsStore:
    def __init__(self, path=APP_SETTINGS_FILE):
        self.path = os.fspath(path)
        self._settings = deepcopy(_DEFAULTS)

    def load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                raw = json.load(stream)
        except FileNotFoundError:
            logger.info("Settings file missing: %s", self.path)
            raw = {}
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.error("Could not read settings %s: %s", self.path, exc)
            raw = {}
        if not isinstance(raw, dict):
            logger.error("Settings root must be an object: %s", self.path)
            raw = {}
        settings = deepcopy(_DEFAULTS)
        for key, value in raw.items():
            if _valid(key, value):
                settings[key] = deepcopy(value)
            else:
                logger.warning("Invalid setting %s in %s; using default", key, self.path)
        self._settings = settings
        return self.snapshot()

    def get(self, key, default=None):
        return deepcopy(self._settings.get(key, default))

    def snapshot(self) -> dict:
        return deepcopy(self._settings)

    def update(self, changes: Mapping) -> None:
        if not isinstance(changes, Mapping):
            raise TypeError("changes must be a mapping")
        for key, value in changes.items():
            if not _valid(key, value):
                raise ValueError(f"Invalid setting: {key}")
        self._settings.update(deepcopy(dict(changes)))

    def save(self, changes: Mapping | None = None) -> bool:
        try:
            candidate = self.snapshot()
            if changes is not None:
                if not isinstance(changes, Mapping):
                    raise TypeError("changes must be a mapping")
                for key, value in changes.items():
                    if not _valid(key, value):
                        raise ValueError(f"Invalid setting: {key}")
                candidate.update(deepcopy(dict(changes)))
            directory = os.path.dirname(os.path.abspath(self.path))
            temporary = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory,
                                                 prefix=".app_settings-", suffix=".tmp",
                                                 delete=False) as stream:
                    temporary = stream.name
                    json.dump(candidate, stream, ensure_ascii=False, indent=4)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary is not None and os.path.exists(temporary):
                    os.unlink(temporary)
        except (OSError, TypeError, ValueError) as exc:
            logger.error("Could not save settings %s: %s", self.path, exc)
            return False
        self._settings = candidate
        return True
