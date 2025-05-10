from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QPushButton, QDialogButtonBox
)
from PyQt6.QtCore import Qt

class RenamedFilesDialog(QDialog):
    def __init__(self, renamed_files_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ファイル名変更履歴")
        self.setMinimumSize(500, 300) # 適宜調整

        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        
        display_text = "以下のファイルは名前が変更されました:\n\n"
        for info in renamed_files_info:
            original_name = info.get('original', 'N/A')
            new_name = info.get('new', 'N/A')
            display_text += f"・「{original_name}」 → 「{new_name}」\n"
        
        self.text_edit.setText(display_text)
        layout.addWidget(self.text_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)

if __name__ == '__main__':
    # Test the dialog
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    # Sample data for testing
    sample_renamed_info = [
        {'original': 'image1.jpg', 'new': 'image1_1.jpg'},
        {'original': 'photo_very_long_name_to_test_wrapping_and_scrolling_behavior.png', 'new': 'photo_very_long_name_to_test_wrapping_and_scrolling_behavior_1.png'},
        {'original': 'document.txt', 'new': 'document_final.txt'},
    ]
    for i in range(20): # Add more items to test scrolling
        sample_renamed_info.append({'original': f'test_image_{i:02d}.jpg', 'new': f'test_image_{i:02d}_renamed.jpg'})

    dialog = RenamedFilesDialog(sample_renamed_info)
    dialog.exec()
    sys.exit(app.exec())
