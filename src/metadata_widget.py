import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QApplication, QTabWidget
)
from PyQt6.QtCore import Qt
from .tag_text_browser import TagTextBrowser

logger = logging.getLogger(__name__)

class MetadataWidget(QWidget):
    def __init__(self, parent=None, metadata_dict=None):
        super().__init__(parent)
        self.metadata_dict = metadata_dict if isinstance(metadata_dict, dict) else {}
        self.init_ui()
        self._populate_fields()
        self._connect_signals()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Widget usually fit into container

        # Tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

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
        
        common_button_layout.addStretch() # Push buttons to the left

        main_layout.addLayout(common_button_layout)

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
        self.tag_generation_info_edit.setPlainText(generation_info)

    def _connect_signals(self):
        self.tab_widget.currentChanged.connect(self._handle_tab_changed)

        # Text Selection Tab
        self.ts_positive_prompt_edit.selectionChanged.connect(
            lambda: self._clear_other_text_edits_selection(self.ts_positive_prompt_edit)
        )
        self.ts_negative_prompt_edit.selectionChanged.connect(
            lambda: self._clear_other_text_edits_selection(self.ts_negative_prompt_edit)
        )
        self.ts_generation_info_edit.selectionChanged.connect(
            lambda: self._clear_other_text_edits_selection(self.ts_generation_info_edit)
        )
        
        # Tag Selection Tab
        self.tag_positive_browser.browserClicked.connect(
            lambda: self._on_tag_browser_clicked(self.tag_positive_browser)
        )
        self.tag_negative_browser.browserClicked.connect(
            lambda: self._on_tag_browser_clicked(self.tag_negative_browser)
        )

    def _on_tag_browser_clicked(self, clicked_browser):
        if clicked_browser == self.tag_positive_browser:
            if self.tag_negative_browser.selected_tags:
                self.tag_negative_browser.clear_selection()
        elif clicked_browser == self.tag_negative_browser:
            if self.tag_positive_browser.selected_tags:
                self.tag_positive_browser.clear_selection()

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
        self.tag_positive_browser.clear_selection()
        self.tag_negative_browser.clear_selection()

    def _handle_tab_changed(self, index):
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

        if current_tab_index == 0:
            if self.ts_positive_prompt_edit.textCursor().hasSelection():
                copied_text = self.ts_positive_prompt_edit.textCursor().selectedText()
            elif self.ts_negative_prompt_edit.textCursor().hasSelection():
                copied_text = self.ts_negative_prompt_edit.textCursor().selectedText()
            elif self.ts_generation_info_edit.textCursor().hasSelection():
                copied_text = self.ts_generation_info_edit.textCursor().selectedText()
        
        elif current_tab_index == 1:
            positive_tags = self.tag_positive_browser.get_selected_tags()
            negative_tags = self.tag_negative_browser.get_selected_tags()

            if positive_tags:
                copied_text = ", ".join(positive_tags)
            elif negative_tags:
                copied_text = ", ".join(negative_tags)
        
        if copied_text:
            clipboard.setText(copied_text)
            logger.info(f"Copied to clipboard: {copied_text[:100]}...")
        else:
            logger.info("Nothing selected to copy.")

    def handle_clear_selection(self):
        current_tab_index = self.tab_widget.currentIndex()
        if current_tab_index == 0:
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

        elif current_tab_index == 1:
            self.tag_positive_browser.clear_selection()
            self.tag_negative_browser.clear_selection()
            logger.info("Cleared tag selections in 'タグ選択' tab.")

    def update_metadata(self, metadata_dict):
        self.metadata_dict = metadata_dict if isinstance(metadata_dict, dict) else {}
        self._populate_fields()
        self.handle_clear_selection()
