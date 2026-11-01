"""Ordered Windows folder bookmarks, independent of Qt and filesystem access."""

from dataclasses import dataclass
import ntpath
import re
from collections import Counter
from collections.abc import Callable


@dataclass(frozen=True)
class FavoriteEntry:
    key: str
    path: str
    name: str
    display_name: str


@dataclass(frozen=True)
class FavoriteResult:
    status: str
    message: str = ""


def normalize_folder_path(path: str) -> tuple[str, str]:
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError("フォルダの絶対パスを指定してください。")
    value = path.replace("/", "\\")
    if value.startswith("\\\\?\\"):
        value = value[4:]
        if value.lower().startswith("unc\\"):
            value = "\\\\" + value[4:]
    elif value.startswith("\\\\.\\"):
        raise ValueError("デバイスパスは登録できません。")
    if value.lower().startswith(("globalroot\\", "\\\\?\\", "\\\\.\\")):
        raise ValueError("デバイスパスは登録できません。")
    if re.match(r"^[a-zA-Z]:\\", value):
        normalized = ntpath.normpath(value)
        if len(normalized) == 2:
            normalized += "\\"
    elif value.startswith("\\\\"):
        drive, tail = ntpath.splitdrive(value)
        if not drive.startswith("\\\\") or len(drive.split("\\")) < 4 or not all(drive.split("\\")[2:4]):
            raise ValueError("共有フォルダの絶対パスを指定してください。")
        normalized = ntpath.normpath(value)
        if not tail or tail == "\\":
            normalized = drive.rstrip("\\") + "\\"
    else:
        raise ValueError("フォルダの絶対パスを指定してください。")
    if normalized.startswith("\\\\") and not ntpath.splitdrive(normalized)[0]:
        raise ValueError("共有フォルダの絶対パスを指定してください。")
    return normalized, ntpath.normcase(normalized)


class FavoriteFolders:
    def __init__(self, raw_paths, persist: Callable[[list[str]], bool]):
        self._persist = persist
        self._paths = []
        keys = set()
        if isinstance(raw_paths, list):
            for path in raw_paths:
                try:
                    normalized, key = normalize_folder_path(path)
                except ValueError:
                    continue
                if key not in keys:
                    self._paths.append(normalized)
                    keys.add(key)

    def entries(self) -> tuple[FavoriteEntry, ...]:
        parts = []
        for path in self._paths:
            drive, tail = ntpath.splitdrive(path)
            is_root = not tail or tail == "\\"
            name = path if is_root else ntpath.basename(path)
            parent = path if is_root else ntpath.dirname(path)
            parts.append((path, ntpath.normcase(path), name, parent))
        counts = Counter(name.casefold() for _, _, name, _ in parts)
        return tuple(FavoriteEntry(key, path, name,
                                   f"{name} — {parent}" if counts[name.casefold()] > 1 else name)
                     for path, key, name, parent in parts)

    def get(self, key: str) -> FavoriteEntry | None:
        return next((entry for entry in self.entries() if entry.key == key), None)

    def _commit(self, candidate: list[str], status: str) -> FavoriteResult:
        try:
            if not self._persist(candidate.copy()):
                return FavoriteResult("save_failed", "お気に入りを保存できませんでした。")
        except Exception:
            return FavoriteResult("save_failed", "お気に入りを保存できませんでした。")
        self._paths = candidate
        return FavoriteResult(status)

    def add(self, path: str) -> FavoriteResult:
        try:
            normalized, key = normalize_folder_path(path)
        except ValueError as exc:
            return FavoriteResult("invalid", str(exc))
        if self.get(key):
            return FavoriteResult("duplicate", "このフォルダは登録済みです。")
        return self._commit([*self._paths, normalized], "added")

    def remove(self, key: str) -> FavoriteResult:
        if not self.get(key):
            return FavoriteResult("not_found", "お気に入りが見つかりません。")
        return self._commit([path for path in self._paths if ntpath.normcase(path) != key], "removed")

    def reorder(self, keys: list[str]) -> FavoriteResult:
        existing = [ntpath.normcase(path) for path in self._paths]
        if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys) or len(keys) != len(existing) or set(keys) != set(existing):
            return FavoriteResult("invalid", "お気に入りの並び順が無効です。")
        if len(keys) != len(set(keys)):
            return FavoriteResult("invalid", "お気に入りの並び順が無効です。")
        if keys == existing:
            return FavoriteResult("unchanged")
        lookup = dict(zip(existing, self._paths))
        return self._commit([lookup[key] for key in keys], "reordered")
