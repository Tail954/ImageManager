import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QApplication, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)

class ImageMetadataDialog(QDialog):
    def __init__(self, metadata_dict, parent=None, item_file_path_for_debug=None): # Added item_file_path_for_debug
        super().__init__(parent)
        self.setWindowTitle("画像メタデータ")
        self.item_file_path_for_debug = item_file_path_for_debug # Store for logging

        self.metadata_dict = metadata_dict if isinstance(metadata_dict, dict) else {}
        
        self.setMinimumSize(500, 400)

        main_layout = QVBoxLayout(self)

        # For simplicity, we'll just display the three target fields directly
        # In a future step, this could be enhanced like ImageMover's tabbed dialog

        self.positive_prompt_edit = QTextEdit(self)
        self.positive_prompt_edit.setPlainText(self.metadata_dict.get("positive_prompt", "N/A"))
        self.positive_prompt_edit.setReadOnly(True)
        
        self.negative_prompt_edit = QTextEdit(self)
        self.negative_prompt_edit.setPlainText(self.metadata_dict.get("negative_prompt", "N/A"))
        self.negative_prompt_edit.setReadOnly(True)
        
        self.generation_info_edit = QTextEdit(self)
        self.generation_info_edit.setPlainText(self.metadata_dict.get("generation_info", "N/A"))
        self.generation_info_edit.setReadOnly(True)

        main_layout.addWidget(QLabel("Positive Prompt:"))
        main_layout.addWidget(self.positive_prompt_edit)
        main_layout.addWidget(QLabel("Negative Prompt:"))
        main_layout.addWidget(self.negative_prompt_edit)
        main_layout.addWidget(QLabel("Generation Info:"))
        main_layout.addWidget(self.generation_info_edit)

        # Close button
        button_layout = QHBoxLayout()
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept) # QDialog.accept() closes the dialog
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def update_metadata(self, metadata_dict, item_file_path_for_debug=None): # Added item_file_path_for_debug
        """Updates the displayed metadata."""
        self.item_file_path_for_debug = item_file_path_for_debug # Update for logging if passed

        self.metadata_dict = metadata_dict if isinstance(metadata_dict, dict) else {}
        self.positive_prompt_edit.setPlainText(self.metadata_dict.get("positive_prompt", "N/A"))
        self.negative_prompt_edit.setPlainText(self.metadata_dict.get("negative_prompt", "N/A"))
        self.generation_info_edit.setPlainText(self.metadata_dict.get("generation_info", "N/A"))
        
        # Ensure the dialog is raised and activated if it's already open and being updated
        if self.isVisible():
            self.raise_()
            self.activateWindow()

if __name__ == '__main__':
    # Example Usage
    app = QApplication([])
    sample_metadata = {
        "positive_prompt": "masterpiece, best quality, intricate details",
        "negative_prompt": "worst quality, low quality, blurry",
        "generation_info": "Steps: 20, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 12345, Size: 512x768"
    }
    dialog = ImageMetadataDialog(sample_metadata)
    dialog.show() # Show non-modally for testing
    app.exec()
