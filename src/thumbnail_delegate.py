from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
from PyQt6.QtGui import QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QRectF

class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection_border_color = QColor("orange")
        self.selection_border_width = 3 # pixels

    def paint(self, painter, option, index):
        # Draw the default item painting
        super().paint(painter, option, index)

        # If the item is selected, draw a border around it
        if option.state & QStyle.StateFlag.State_Selected:
            # Delegate will no longer draw the selection border.
            # This will be handled by QListView's stylesheet.
            # Print statements for debugging were here, now removed.
            pass

    # We might need to override sizeHint if the border significantly changes item size perception,
    # but with QListView.setUniformItemSizes(True) and setGridSize,
    # the layout is already fixed, so sizeHint might not be strictly necessary for layout.
    # However, if the border makes items appear to need more space, this could be adjusted.
