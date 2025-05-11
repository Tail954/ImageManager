import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QApplication, QTabWidget, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt
import os # Added import
from .tag_text_browser import TagTextBrowser # Import the new TagTextBrowser

logger = logging.getLogger(__name__)

class ImageMetadataDialog(QDialog):
    def _update_title(self):
        if self.item_file_path_for_debug and os.path.basename(self.item_file_path_for_debug): # Ensure basename is not empty
            self.setWindowTitle(f"画像メタデータ: {os.path.basename(self.item_file_path_for_debug)}")
        else:
            self.setWindowTitle("画像メタデータ")

    def __init__(self, metadata_dict, parent=None, item_file_path_for_debug=None):
        super().__init__(parent)
        # self.setWindowTitle("画像メタデータ") # Title will be set by _update_title
        self.item_file_path_for_debug = item_file_path_for_debug
        self.metadata_dict = metadata_dict if isinstance(metadata_dict, dict) else {}
        self._update_title() # Set initial title correctly

        # Main layout for the dialog
        main_dialog_layout = QVBoxLayout(self)

        # Tab widget
        self.tab_widget = QTabWidget()
        main_dialog_layout.addWidget(self.tab_widget)

        # --- Tab 1: テキスト選択 ---
        self.text_selection_tab = QWidget()
        text_selection_layout = QVBoxLayout(self.text_selection_tab)

        self.ts_positive_prompt_edit = QTextEdit()
        self.ts_positive_prompt_edit.setReadOnly(True)
        text_selection_layout.addWidget(QLabel("Positive Prompt:"))
        text_selection_layout.addWidget(self.ts_positive_prompt_edit)

        self.ts_negative_prompt_edit = QTextEdit()
        self.ts_negative_prompt_edit.setReadOnly(True)
        text_selection_layout.addWidget(QLabel("Negative Prompt:"))
        text_selection_layout.addWidget(self.ts_negative_prompt_edit)

        self.ts_generation_info_edit = QTextEdit()
        self.ts_generation_info_edit.setReadOnly(True)
        text_selection_layout.addWidget(QLabel("Generation Info:"))
        text_selection_layout.addWidget(self.ts_generation_info_edit)
        
        self.tab_widget.addTab(self.text_selection_tab, "テキスト選択")

        # --- Tab 2: タグ選択 ---
        self.tag_selection_tab = QWidget()
        tag_selection_layout = QVBoxLayout(self.tag_selection_tab)

        self.tag_positive_browser = TagTextBrowser()
        tag_selection_layout.addWidget(QLabel("Positive Prompt (タグ選択):"))
        tag_selection_layout.addWidget(self.tag_positive_browser)

        self.tag_negative_browser = TagTextBrowser()
        tag_selection_layout.addWidget(QLabel("Negative Prompt (タグ選択):"))
        tag_selection_layout.addWidget(self.tag_negative_browser)

        self.tag_generation_info_edit = QTextEdit() # For Generation Info display on this tab
        self.tag_generation_info_edit.setReadOnly(True)
        tag_selection_layout.addWidget(QLabel("Generation Info (参照用):"))
        tag_selection_layout.addWidget(self.tag_generation_info_edit)

        self.tab_widget.addTab(self.tag_selection_tab, "タグ選択")

        # --- Common Buttons ---
        common_button_layout = QHBoxLayout()
        self.copy_button = QPushButton("クリップボードにコピー")
        self.copy_button.clicked.connect(self.handle_copy_to_clipboard)
        common_button_layout.addWidget(self.copy_button)

        self.clear_selection_button = QPushButton("選択をクリア")
        self.clear_selection_button.clicked.connect(self.handle_clear_selection)
        common_button_layout.addWidget(self.clear_selection_button)

        common_button_layout.addStretch() # Push close button to the right

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        common_button_layout.addWidget(self.close_button)
        
        main_dialog_layout.addLayout(common_button_layout)

        self.setLayout(main_dialog_layout)
        self.resize(600, 500) # Set a reasonable default size

        self._populate_fields()
        self._connect_signals()


    def _populate_fields(self):
        positive_prompt = self.metadata_dict.get("positive_prompt", "N/A")
        negative_prompt = self.metadata_dict.get("negative_prompt", "N/A")
        generation_info = self.metadata_dict.get("generation_info", "N/A")

        # Text Selection Tab
        self.ts_positive_prompt_edit.setPlainText(positive_prompt)
        self.ts_negative_prompt_edit.setPlainText(negative_prompt)
        self.ts_generation_info_edit.setPlainText(generation_info)

        # Tag Selection Tab
        self.tag_positive_browser.parse_and_set_text(positive_prompt)
        self.tag_negative_browser.parse_and_set_text(negative_prompt)
        self.tag_generation_info_edit.setPlainText(generation_info) # Display as plain text

    def _connect_signals(self):
        # Connect signals for clearing selections when focus changes or tab changes
        self.tab_widget.currentChanged.connect(self._handle_tab_changed)

        # Text Selection Tab - clear other selections in this tab
        self.ts_positive_prompt_edit.selectionChanged.connect(
            lambda: self._clear_other_text_edits_selection(self.ts_positive_prompt_edit)
        )
        self.ts_negative_prompt_edit.selectionChanged.connect(
            lambda: self._clear_other_text_edits_selection(self.ts_negative_prompt_edit)
        )
        self.ts_generation_info_edit.selectionChanged.connect(
            lambda: self._clear_other_text_edits_selection(self.ts_generation_info_edit)
        )
        
        # Tag Selection Tab - clear other tag browser's selection
        # This might need more refined logic if clicking one browser should clear the other.
        # For now, the copy/clear buttons will operate on the "active" one (e.g. last clicked).
        # A simpler approach: when one TagTextBrowser gets a click, clear the other.
        # This requires TagTextBrowser to emit a signal or for us to filter events.
        # Let's assume for now that the user will interact with one at a time,
        # and the "Clear Selection" button will clear the appropriate one based on some logic,
        # or clear both if that's simpler.
        # ImageMover's MetadataDialog had `handle_mouse_press` to clear other browsers.
        # We can replicate this by connecting a custom signal or by overriding mousePressEvent
        # in the dialog for TagTextBrowsers if they are direct children.
        
        # Connect browserClicked signals for exclusive selection logic
        self.tag_positive_browser.browserClicked.connect(
            lambda: self._on_tag_browser_clicked(self.tag_positive_browser)
        )
        self.tag_negative_browser.browserClicked.connect(
            lambda: self._on_tag_browser_clicked(self.tag_negative_browser)
        )

    def _on_tag_browser_clicked(self, clicked_browser):
        """Handles clicks on a TagTextBrowser to ensure exclusive selection."""
        # Clear selection in the other TagTextBrowser
        if clicked_browser == self.tag_positive_browser:
            if self.tag_negative_browser.selected_tags: # Only clear if it has selection
                self.tag_negative_browser.clear_selection()
        elif clicked_browser == self.tag_negative_browser:
            if self.tag_positive_browser.selected_tags: # Only clear if it has selection
                self.tag_positive_browser.clear_selection()

        # Clear any text selection in the "テキスト選択" tab
        editors_to_clear = [self.ts_positive_prompt_edit, self.ts_negative_prompt_edit, self.ts_generation_info_edit]
        for editor in editors_to_clear:
            if editor.textCursor().hasSelection():
                cursor = editor.textCursor()
                cursor.clearSelection()
                editor.setTextCursor(cursor)

    def _clear_other_text_edits_selection(self, current_editor):
        editors = [self.ts_positive_prompt_edit, self.ts_negative_prompt_edit, self.ts_generation_info_edit]
        for editor in editors:
            if editor is not current_editor and editor.textCursor().hasSelection():
                cursor = editor.textCursor()
                cursor.clearSelection()
                editor.setTextCursor(cursor)
        # Also clear tag selections if a text edit gets selection
        self.tag_positive_browser.clear_selection()
        self.tag_negative_browser.clear_selection()


    def _handle_tab_changed(self, index):
        # When tab changes, clear all selections to avoid confusion
        self.ts_positive_prompt_edit.textCursor().clearSelection()
        self.ts_negative_prompt_edit.textCursor().clearSelection()
        self.ts_generation_info_edit.textCursor().clearSelection()
        self.tag_positive_browser.clear_selection()
        self.tag_negative_browser.clear_selection()


    def handle_copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        if not clipboard:
            logger.error("Failed to get clipboard instance.")
            return

        current_tab_index = self.tab_widget.currentIndex()
        copied_text = ""

        if current_tab_index == 0: # "テキスト選択" タブ
            if self.ts_positive_prompt_edit.textCursor().hasSelection():
                copied_text = self.ts_positive_prompt_edit.textCursor().selectedText()
            elif self.ts_negative_prompt_edit.textCursor().hasSelection():
                copied_text = self.ts_negative_prompt_edit.textCursor().selectedText()
            elif self.ts_generation_info_edit.textCursor().hasSelection():
                copied_text = self.ts_generation_info_edit.textCursor().selectedText()
        
        elif current_tab_index == 1: # "タグ選択" タブ
            # Determine which TagTextBrowser was last interacted with or has selection.
            # For simplicity, we can check both. If both have selections, decide a priority or join them.
            # ImageMover copied from the one that had selection.
            # Let's assume we copy from positive if it has selection, else from negative.
            # A more robust way would be to track last focused/clicked TagTextBrowser.
            
            positive_tags = self.tag_positive_browser.get_selected_tags()
            negative_tags = self.tag_negative_browser.get_selected_tags()

            # Simple strategy: if positive has tags, use that. Else if negative has tags, use that.
            # If both have (which shouldn't happen with good exclusive selection logic), prioritize positive.
            if positive_tags:
                copied_text = ", ".join(positive_tags)
            elif negative_tags:
                copied_text = ", ".join(negative_tags)
        
        if copied_text:
            clipboard.setText(copied_text)
            logger.info(f"Copied to clipboard: {copied_text[:100]}...") # Log snippet
        else:
            logger.info("Nothing selected to copy.")


    def handle_clear_selection(self):
        current_tab_index = self.tab_widget.currentIndex()
        if current_tab_index == 0: # "テキスト選択" タブ
            cursor = self.ts_positive_prompt_edit.textCursor()
            cursor.clearSelection()
            self.ts_positive_prompt_edit.setTextCursor(cursor)

            cursor = self.ts_negative_prompt_edit.textCursor()
            cursor.clearSelection()
            self.ts_negative_prompt_edit.setTextCursor(cursor)

            cursor = self.ts_generation_info_edit.textCursor()
            cursor.clearSelection()
            self.ts_generation_info_edit.setTextCursor(cursor)
            logger.info("Cleared text selection in 'テキスト選択' tab.")

        elif current_tab_index == 1: # "タグ選択" タブ
            self.tag_positive_browser.clear_selection()
            self.tag_negative_browser.clear_selection()
            logger.info("Cleared tag selections in 'タグ選択' tab.")


    def update_metadata(self, metadata_dict, item_file_path_for_debug=None):
        self.item_file_path_for_debug = item_file_path_for_debug # Update path
        self.metadata_dict = metadata_dict if isinstance(metadata_dict, dict) else {}
        self._update_title() # Update title with new path
        
        self._populate_fields() # Re-populate all fields with new metadata
        self.handle_clear_selection() # Clear any existing selections

        if self.isVisible():
            self.raise_()
            self.activateWindow()

if __name__ == '__main__':
    # Example Usage (ensure TagTextBrowser is in the same directory or Python path)
    # from tag_text_browser import TagTextBrowser # Assuming it's in the same dir for testing
    app = QApplication([])
    sample_metadata = {
        "positive_prompt": "masterpiece, best quality, intricate details",
        "negative_prompt": "worst quality, low quality, blurry",
        "generation_info": "Steps: 20, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 12345, Size: 512x768"
    }
    dialog = ImageMetadataDialog(sample_metadata)
    dialog.show() # Show non-modally for testing
    app.exec()
