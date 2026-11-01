"""Path-based thumbnail selection and copy numbering."""

from PyQt6.QtCore import QObject, Qt, QItemSelection, QItemSelectionModel, pyqtSignal

from .constants import SELECTION_ORDER_ROLE


class SelectionController(QObject):
    selectionChanged = pyqtSignal()

    def __init__(self, thumbnails, proxy_model, view, parent=None):
        super().__init__(parent)
        self.thumbnails = thumbnails
        self.proxy_model = proxy_model
        self.view = view
        self._selected = ()
        self._copy_order = []
        self._copy_mode = False
        self._suppress = False
        view.selectionModel().selectionChanged.connect(self.sync_from_view)

    def selected_paths(self) -> tuple[str, ...]:
        return self._selected

    def copy_paths(self) -> tuple[str, ...]:
        return tuple(self._copy_order)

    def is_selected(self, path: str) -> bool:
        return path in self._selected

    def set_copy_mode(self, enabled: bool) -> None:
        if self._copy_mode != bool(enabled):
            self.clear()
            self._copy_mode = bool(enabled)

    def _view_paths(self):
        paths = []
        for index in self.view.selectionModel().selectedIndexes():
            path = self.proxy_model.data(index, Qt.ItemDataRole.UserRole)
            if path and path not in paths:
                paths.append(path)
        return tuple(paths)

    def _update_numbers(self, old_order):
        for path in set(old_order) | set(self._copy_order):
            item = self.thumbnails.item_for_path(path)
            if item is not None:
                number = self._copy_order.index(path) + 1 if path in self._copy_order else None
                if item.data(SELECTION_ORDER_ROLE) != number:
                    item.setData(number, SELECTION_ORDER_ROLE)

    def sync_from_view(self, *_args) -> None:
        if self._suppress:
            return
        selected = self._view_paths()
        old_order = self._copy_order.copy()
        if self._copy_mode:
            self._copy_order = [path for path in self._copy_order if path in selected]
            self._copy_order.extend(path for path in selected if path not in self._copy_order)
        else:
            self._copy_order.clear()
        if selected != self._selected or old_order != self._copy_order:
            self._selected = selected
            self._update_numbers(old_order)
            self.selectionChanged.emit()

    def clear(self) -> None:
        old_order = self._copy_order.copy()
        self._selected = ()
        self._copy_order.clear()
        selection_model = self.view.selectionModel()
        self._suppress = True
        try:
            selection_model.clearSelection()
        finally:
            self._suppress = False
        self._update_numbers(old_order)
        self.selectionChanged.emit()

    def select_all(self) -> None:
        self.view.selectAll()
        self.sync_from_view()

    def toggle(self, path: str) -> None:
        item = self.thumbnails.item_for_path(path)
        if item is None:
            return
        index = self.proxy_model.mapFromSource(self.thumbnails.source_model.indexFromItem(item))
        if index.isValid():
            self.view.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Toggle)
            self.sync_from_view()

    def _restore(self, paths, copy_order, mutate) -> None:
        selection_model = self.view.selectionModel()
        self._suppress = True
        updates_enabled = self.view.updatesEnabled()
        self.view.setUpdatesEnabled(False)
        try:
            mutate()
            restored = QItemSelection()
            visible = []
            for path in paths:
                item = self.thumbnails.item_for_path(path)
                if item is None:
                    continue
                index = self.proxy_model.mapFromSource(self.thumbnails.source_model.indexFromItem(item))
                if index.isValid():
                    restored.select(index, index)
                    visible.append(path)
            selection_model.select(restored, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            old_order = self._copy_order.copy()
            self._selected = tuple(visible)
            self._copy_order = [path for path in copy_order if path in visible] if self._copy_mode else []
            self._update_numbers(old_order)
        finally:
            self.view.setUpdatesEnabled(updates_enabled)
            self._suppress = False
        self.selectionChanged.emit()

    def apply_filters(self, positive, negative, generation, search_mode,
                      preserve_selection=True) -> None:
        paths = self._selected if preserve_selection else ()
        order = self._copy_order.copy() if preserve_selection else []
        self._restore(paths, order, lambda: self.proxy_model.set_filters(
            positive, negative, generation, search_mode))

    def apply_sort(self, key_type, order) -> None:
        def sort():
            self.proxy_model.set_sort_key_type(key_type)
            if key_type == 2:
                self.proxy_model.sort(-1)
            else:
                self.proxy_model.sort(0, order)
        self._restore(self._selected, self._copy_order.copy(), sort)

    def remove_paths(self, paths) -> None:
        removed = set(paths)
        self._restore([path for path in self._selected if path not in removed],
                      [path for path in self._copy_order if path not in removed], lambda: None)
