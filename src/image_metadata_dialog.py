import logging
import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout
from .metadata_widget import MetadataWidget

logger = logging.getLogger(__name__)

class ImageMetadataDialog(QDialog):
    def _update_title(self):
        base_name = os.path.basename(self.item_file_path_for_debug) if self.item_file_path_for_debug else ""
        if base_name:
            self.setWindowTitle(f"画像メタデータ: {base_name}")
        else:
            self.setWindowTitle("画像メタデータ")

    def __init__(self, metadata_dict, parent=None, item_file_path_for_debug=None):
        super().__init__(parent)
        self.item_file_path_for_debug = item_file_path_for_debug
        self._update_title()

        self.resize(600, 500)

        main_layout = QVBoxLayout(self)

        self.metadata_widget = MetadataWidget(self, metadata_dict)
        main_layout.addWidget(self.metadata_widget)

        # Close button (MetadataWidget has Copy/Clear, but Close is usually on Dialog)
        # Note: The original ImageMetadataDialog had Close inside the layout.
        # MetadataWidget does NOT have a close button, so we add it here.
        # However, MetadataWidget was designed to be embedded.
        # Let's check MetadataWidget implementation again.
        # Ah, in my previous tool call I included "Close" button? No, I added "addStretch" but not Close button in MetadataWidget.
        # So I should add Close button here.
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

    def update_metadata(self, metadata_dict, item_file_path_for_debug=None):
        self.item_file_path_for_debug = item_file_path_for_debug
        self._update_title()
        self.metadata_widget.update_metadata(metadata_dict)

        if self.isVisible():
            self.raise_()
            self.activateWindow()

if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication
    app = QApplication([])
    sample = {"positive_prompt": "test"}
    dialog = ImageMetadataDialog(sample)
    dialog.show()
    app.exec()
