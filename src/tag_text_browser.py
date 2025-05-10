import logging
from PyQt6.QtWidgets import QTextBrowser
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QEvent

logger = logging.getLogger(__name__)

class TagTextBrowser(QTextBrowser):
    tagClicked = pyqtSignal(str) 
    browserClicked = pyqtSignal() # New signal to indicate this browser was clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        # Allow text selection by mouse for copying, but primary interaction is custom tag selection
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse) 
        self.selected_tags = set()
        self.tag_positions = [] # Stores tuples of (start_pos, end_pos, tag_text)
        self.drag_start_pos = None # Store the character position of drag start

        # It seems viewport event filter was problematic or not standard.
        # We will rely on the browser's own mouse events.

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scrollbar = self.verticalScrollBar()
            original_scroll_value = scrollbar.value() if scrollbar else 0
            
            cursor = self.cursorForPosition(event.pos())
            char_position = cursor.position() # Get character position, not block position
            
            self.drag_start_pos = char_position # Record drag start position
            
            tag_clicked_on = None
            for start, end, tag_text in self.tag_positions:
                if start <= char_position < end: # Use < end for character position
                    tag_clicked_on = tag_text
                    if tag_text in self.selected_tags:
                        self.selected_tags.remove(tag_text)
                    else:
                        self.selected_tags.add(tag_text)
                    break # Found the tag, no need to check others for this click
            
            self.update_highlight()
            self.browserClicked.emit()

            if tag_clicked_on:
                self.tagClicked.emit(tag_clicked_on)
                event.accept()
            
            if not event.isAccepted():
                # If our custom tag click logic didn't handle it, pass to super.
                # This allows for normal text selection if clicking outside tags.
                super().mousePressEvent(event)
            
            if scrollbar:
                scrollbar.setValue(original_scroll_value) # Restore scroll position at the end
            
            # If event was accepted by us or super, it's handled.
            # If not, it propagates further up.
            return # Explicitly return to signify we've processed this button press.

        # For other mouse buttons, defer to superclass
        super().mousePressEvent(event)


    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.drag_start_pos is not None:
            scrollbar = self.verticalScrollBar()
            original_scroll_value = scrollbar.value() if scrollbar else 0
            
            cursor = self.cursorForPosition(event.pos())
            current_char_pos = cursor.position()
            
            # Determine selection range based on drag
            selection_start_char = min(self.drag_start_pos, current_char_pos)
            selection_end_char = max(self.drag_start_pos, current_char_pos)
            
            # Temporarily clear and re-populate selected_tags based on drag range
            # This provides live feedback during drag.
            current_drag_selected_tags = set()
            for start, end, tag_text in self.tag_positions:
                # Check for overlap: if the tag's range [start, end)
                # overlaps with the selection range [selection_start_char, selection_end_char)
                if max(start, selection_start_char) < min(end, selection_end_char):
                    current_drag_selected_tags.add(tag_text)
            
            # Update selected_tags only if they changed to avoid too many highlight updates
            if self.selected_tags != current_drag_selected_tags:
                self.selected_tags = current_drag_selected_tags
                self.update_highlight()

            if scrollbar:
                scrollbar.setValue(original_scroll_value) # Restore scroll position
            
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Finalize selection on mouse release.
            # The selection made during mouseMove is already in self.selected_tags.
            self.drag_start_pos = None # Reset drag start position
            # No need to call super().mouseReleaseEvent(event) if we handled it,
            # otherwise, it might interfere with custom selection.
            # However, if we want to allow normal text selection to also work,
            # we might need to be more careful here.
            # For now, assume left-click release finalizes our tag selection.
            event.accept() 
            return
        super().mouseReleaseEvent(event)

    def clear_selection(self):
        self.selected_tags.clear()
        self.update_highlight()

    def update_highlight(self):
        # Save current cursor position to restore it later
        # This prevents the view from jumping after reformatting
        original_cursor = self.textCursor()
        
        # Create a new cursor for modifications
        modify_cursor = self.textCursor()
        
        # Clear all existing formatting (background color)
        modify_cursor.select(QTextCursor.SelectionType.Document)
        default_format = QTextCharFormat() # Default format (no background)
        modify_cursor.setCharFormat(default_format)
        modify_cursor.clearSelection()
        
        # Apply highlight to selected tags
        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor("orange")) # Standard highlight color
        
        for start, end, tag_text in self.tag_positions:
            if tag_text in self.selected_tags:
                modify_cursor.setPosition(start)
                modify_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                modify_cursor.setCharFormat(highlight_format)
                modify_cursor.clearSelection() # Important to clear selection after formatting
        
        # Restore the original cursor position
        self.setTextCursor(original_cursor)

    def parse_and_set_text(self, text):
        self.clear() # Clear previous content and selections
        self.selected_tags.clear()
        self.tag_positions = []
        
        if not text:
            self.setPlainText("")
            return
        
        # Set the plain text first, so character positions are valid
        self.setPlainText(text)
        
        # タグを検出するための状態変数 (ImageMover's parser logic)
        i = 0
        text_length = len(text)
        
        while i < text_length:
            # 空白をスキップ
            while i < text_length and text[i].isspace():
                i += 1
            
            if i >= text_length:
                break
            
            start = i # This is the character index in the original text string
            
            # カッコ内のタグ処理
            if text[i] == '(':
                bracket_count = 1
                i += 1
                while i < text_length and bracket_count > 0:
                    if text[i] == '(':
                        bracket_count += 1
                    elif text[i] == ')':
                        bracket_count -= 1
                    i += 1
                tag_text = text[start:i].strip()
                self.tag_positions.append((start, i, tag_text))
            
            # 角括弧内のタグ処理 
            elif text[i] == '<':
                i += 1
                while i < text_length and text[i] != '>':
                    i += 1
                if i < text_length:  # '>'が見つかった場合
                    i += 1  # '>'も含める
                tag_text = text[start:i].strip()
                self.tag_positions.append((start, i, tag_text))
            
            # エスケープされた括弧のタグ処理 \(...\)
            elif i < text_length - 1 and text[i] == '\\' and text[i+1] == '(':
                i += 2  # \( をスキップ
                while i < text_length:
                    if i < text_length - 1 and text[i] == '\\' and text[i+1] == ')':
                        i += 2  # \) も含める
                        break
                    i += 1
                tag_text = text[start:i].strip()
                self.tag_positions.append((start, i, tag_text))
            
            # 通常のタグ処理（カンマまで）
            else:
                escape_sequence_active = False
                temp_tag_start = i
                while i < text_length:
                    if text[i] == '\\' and i + 1 < text_length:
                        # This is an escape character, skip next char as well
                        i += 2 
                        escape_sequence_active = True # Mark that we just processed an escape
                        continue
                    
                    # Break if comma, or start of special tag (if not just after an escape)
                    if text[i] == ',' or \
                       (not escape_sequence_active and (text[i] == '<' or text[i] == '(')):
                        break
                    
                    i += 1
                    escape_sequence_active = False # Reset after moving past a non-escape char
                
                # Current segment ends at `i`
                tag_text = text[temp_tag_start:i].strip()
                if tag_text:
                    self.tag_positions.append((temp_tag_start, i, tag_text))
                
                # If we stopped because of a comma, consume it
                if i < text_length and text[i] == ',':
                    i += 1 
                # If we stopped because of '<' or '(', the next loop iteration will handle it.
        
        self.update_highlight()

    def get_selected_tags(self):
        # Return tags in the order they appear in the text
        ordered_selected_tags = []
        for start, end, tag_text in self.tag_positions:
            if tag_text in self.selected_tags:
                ordered_selected_tags.append(tag_text)
        return ordered_selected_tags

if __name__ == '__main__':
    # Example Usage for testing TagTextBrowser directly
    import sys
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QDialog, QPushButton

    app = QApplication(sys.argv)
    test_dialog = QDialog()
    test_dialog.setWindowTitle("TagTextBrowser Test")
    layout = QVBoxLayout(test_dialog)
    
    browser = TagTextBrowser()
    # Test string with various cases from ImageMover's parser
    test_prompt = ("masterpiece, (best quality:1.2), illustration, amazing composition, <lora:cool_style:0.8>, "
                   "detailed face, intricate details, \(escaped parentheses tag\), normal_tag, another_tag, "
                   "tag with spaces, (complex_nested:(tag:0.5):1.1), final_tag")
    browser.parse_and_set_text(test_prompt)
    layout.addWidget(browser)
    
    def print_selected():
        logger.info(f"Selected Tags: {browser.get_selected_tags()}")
        
    button = QPushButton("Print Selected Tags")
    button.clicked.connect(print_selected)
    layout.addWidget(button)
    
    test_dialog.resize(600, 400)
    test_dialog.show()
    sys.exit(app.exec())
