from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QListView
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QPainter # Added QFont, QPainter
from PyQt6.QtCore import Qt, QRectF, QSize # Added QSize
import logging # Add logging import

logger = logging.getLogger(__name__) # Get logger for this module

from .constants import SELECTION_ORDER_ROLE # Import from constants

class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection_border_color = QColor("orange")
        self.selection_border_width = 3 # pixels
        self.order_number_font = QFont("Arial", 10, QFont.Weight.Bold)
        self.order_number_color = QColor("white")
        self.order_number_background_color = QColor(0, 0, 0, 180) # Semi-transparent black

    def paint(self, painter, option, index):
        # Draw the default item painting (icon and text)
        super().paint(painter, option, index)

        # Draw selection order number if in copy mode and number exists
        view = self.parent() # This should be the QListView
        main_window_instance = None
        is_copy_mode_active = False

        if isinstance(view, QListView):
            top_level_window = view.window()
            if hasattr(top_level_window, 'is_copy_mode'):
                main_window_instance = top_level_window
        
        if main_window_instance:
            is_copy_mode_active = main_window_instance.is_copy_mode
        
        # logger.debug(f"Delegate Paint: Item {index.row()}, is_copy_mode_active: {is_copy_mode_active}, option.rect: {option.rect}")

        if is_copy_mode_active:
            order_number = index.data(SELECTION_ORDER_ROLE)
            # logger.debug(f"Delegate Paint: Item {index.row()}, In Copy Mode, Order Number: {order_number}")
            if order_number is not None:
                # logger.debug(f"Delegate Paint: Drawing order {order_number} for item {index.row()} at rect {option.rect}")
                painter.save()
                painter.setFont(self.order_number_font)
                
                text = f"{order_number:03}" # Format as 3 digits
                
                # Calculate text size for background
                fm = painter.fontMetrics()
                text_rect = fm.boundingRect(text)
                
                # Position at top-right corner of the item's rect (option.rect)
                # Add some padding
                padding = 2
                bg_width = text_rect.width() + 2 * padding
                bg_height = text_rect.height() + 2 * padding
                
                # Position background rectangle
                bg_rect_x = option.rect.right() - bg_width - padding
                bg_rect_y = option.rect.top() + padding
                
                background_rect = QRectF(bg_rect_x, bg_rect_y, bg_width, bg_height)
                
                painter.setBrush(QBrush(self.order_number_background_color))
                painter.setPen(Qt.PenStyle.NoPen) # No border for the background itself
                painter.drawRoundedRect(background_rect, 5.0, 5.0) # Rounded corners

                painter.setPen(QPen(self.order_number_color))
                # Adjust text position to be centered within the background
                text_x = bg_rect_x + padding
                text_y = bg_rect_y + padding + fm.ascent() # fm.ascent() for better vertical alignment
                
                painter.drawText(int(text_x), int(text_y), text)
                painter.restore()

        # The actual selection border is handled by QListView's stylesheet.
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
