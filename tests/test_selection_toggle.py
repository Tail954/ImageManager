import sys
import os
import unittest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtCore import Qt

# Add project root to sys.path to find src module
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.image_preview_widget import ImagePreviewWidget
from src.full_image_dialog import FullImageDialog

app = QApplication(sys.argv)

class TestSelectionToggle(unittest.TestCase):
    def test_preview_widget_toggle(self):
        widget = ImagePreviewWidget()
        
        # Test button exists
        self.assertTrue(hasattr(widget, 'selection_button'))
        self.assertIsInstance(widget.selection_button, QPushButton)
        
        # Test initial state
        widget.update_image("test.jpg", 0, 1, is_selected=False)
        self.assertFalse(widget.selection_button.isChecked())
        self.assertEqual(widget.selection_button.text(), "Select")
        
        widget.update_image("test.jpg", 0, 1, is_selected=True)
        self.assertTrue(widget.selection_button.isChecked())
        self.assertEqual(widget.selection_button.text(), "Selected")
        
        # Test signal emission
        tensor_mock = MagicMock()
        widget.toggle_selection_requested.connect(tensor_mock)
        widget.selection_button.click()
        tensor_mock.assert_called_once()

    def test_full_image_dialog_integration(self):
        # Mock callback
        mock_callback = MagicMock(return_value=True)
        dialog = FullImageDialog(["test.jpg"], 0, is_selected_callback=mock_callback)
        
        # Verify initial state based on callback
        self.assertTrue(dialog.preview_widget.selection_button.isChecked())
        mock_callback.assert_called_with("test.jpg")
        
        # Verify signal propagation via method
        signal_mock = MagicMock()
        dialog.toggle_selection_requested.connect(signal_mock)
        
        # Simulate widget signal
        dialog.preview_widget.toggle_selection_requested.emit()
        signal_mock.assert_called_with("test.jpg")

if __name__ == '__main__':
    unittest.main()
