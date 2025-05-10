from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QListView
from PyQt6.QtGui import QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QRectF, QSize # Added QSize

class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection_border_color = QColor("orange")
        self.selection_border_width = 3 # pixels

    def paint(self, painter, option, index):
        # Draw the default item painting
        super().paint(painter, option, index)

        # Selection border is handled by QListView's stylesheet.
        # if option.state & QStyle.StateFlag.State_Selected:
        #     pass

    def sizeHint(self, option, index):
        # Get the parent view (QListView)
        view = self.parent()
        if isinstance(view, QListView): # Check if parent is a QListView
            # In IconMode with uniformItemSizes, gridSize is the authority.
            # The iconSize is the size of the icon within this grid cell.
            # sizeHint should return the total space for the item.
            grid_s = view.gridSize()
            if grid_s.isValid():
                return grid_s
        
        # Fallback to base implementation if view is not QListView or gridSize is not set
        return super().sizeHint(option, index)
