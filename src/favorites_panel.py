"""Favorites navigation widget; persistence and navigation stay with the controller."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QListWidget, QListWidgetItem,
                             QMenu, QPushButton, QVBoxLayout, QWidget)


class _FavoriteList(QListWidget):
    activatedKey = pyqtSignal(str)
    reordered = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._press_pos = None
        self._dragged = False
        self._pressed_item = None

    def mousePressEvent(self, event):
        self._press_pos = event.position().toPoint() if event.button() == Qt.MouseButton.LeftButton else None
        self._dragged = False
        self._pressed_item = self.itemAt(self._press_pos) if self._press_pos is not None else None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and (event.position().toPoint() - self._press_pos).manhattanLength() >= QApplication.startDragDistance():
            self._dragged = True
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._dragged = True
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        activate = event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None and not self._dragged and item is not None and item is self._pressed_item
        super().mouseReleaseEvent(event)
        self._press_pos = None
        if activate:
            self.activatedKey.emit(item.data(Qt.ItemDataRole.UserRole))

    def dropEvent(self, event):
        if event.source() is not self:
            event.ignore()
            return
        before = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        super().dropEvent(event)
        after = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        if event.isAccepted() and before != after:
            self.reordered.emit(after)


class FavoritesPanel(QWidget):
    addRequested = pyqtSignal()
    activateRequested = pyqtSignal(str)
    removeRequested = pyqtSignal(str)
    copyPathRequested = pyqtSignal(str)
    openInExplorerRequested = pyqtSignal(str)
    orderChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_key = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.add_button = QPushButton('現在のフォルダを追加')
        self.add_button.clicked.connect(self.addRequested)
        layout.addWidget(self.add_button)
        self.list_widget = _FavoriteList(self)
        layout.addWidget(self.list_widget)
        self.list_widget.activatedKey.connect(self.activateRequested)
        self.list_widget.reordered.connect(self.orderChanged)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._context_menu)

    def set_entries(self, entries):
        self.list_widget.clear()
        for entry in entries:
            item = QListWidgetItem(entry.display_name)
            item.setData(Qt.ItemDataRole.UserRole, entry.key)
            item.setToolTip(entry.path)
            self.list_widget.addItem(item)
        self.set_current_key(self._current_key)

    def set_current_key(self, key):
        self._current_key = key
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            font = QFont(item.font())
            font.setBold(item.data(Qt.ItemDataRole.UserRole) == key)
            item.setFont(font)

    def set_can_add(self, enabled):
        self.add_button.setEnabled(enabled)

    def _context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        remove = menu.addAction('お気に入りから解除')
        copy = menu.addAction('パスをコピー')
        explorer = menu.addAction('エクスプローラーで開く')
        chosen = menu.exec(self.list_widget.viewport().mapToGlobal(pos))
        if chosen == remove:
            self.removeRequested.emit(key)
        elif chosen == copy:
            self.copyPathRequested.emit(key)
        elif chosen == explorer:
            self.openInExplorerRequested.emit(key)
