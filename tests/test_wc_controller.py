import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtTest import QSignalSpy

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.wc_controller import WCController
from src.wc_creator_dialog import WCCreatorDialog
from src.constants import WC_FORMAT_HASH_COMMENT, WC_FORMAT_BRACKET_COMMENT

class TestWCController(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.app.quit()

    def setUp(self):
        self.controller = WCController()
        self.test_data_dir = os.path.join(os.path.dirname(__file__), 'test_data')
        self.test_images = [
            os.path.join(self.test_data_dir, 'images', 'test1.jpg'),
            os.path.join(self.test_data_dir, 'images', 'test2.jpg')
        ]
        self.test_metadata = [
            {'positive_prompt': 'test1 prompt'},
            {'positive_prompt': 'test2 prompt'}
        ]

    def test_load_invalid_image_path(self):
        """無効な画像パスを渡した場合のテスト"""
        # Patch QImage where it's used in wc_controller
        with patch('src.wc_controller.QImage') as MockQImageClass:
            mock_qimage_instance = MockQImageClass.return_value
            mock_qimage_instance.load.return_value = False # Simulate load failure
            mock_qimage_instance.isNull.return_value = True
            result = self.controller.load_image_data('invalid_path')
            self.assertFalse(result)
            mock_qimage_instance.load.assert_called_with('invalid_path')

    def test_empty_metadata_handling(self):
        """空のメタデータを渡した場合のテスト"""
        dialog = WCCreatorDialog([self.test_images[0]], [{}], WC_FORMAT_HASH_COMMENT)
        self.assertEqual(dialog.metadata_list, [{}])
        self.assertEqual(len(dialog.prompt_line_edits), 0) # Check if no prompt lines are created

    def test_large_image_loading(self):
        """大量の画像読み込みテスト"""
        test_images = [f"test_{i}.jpg" for i in range(100)]
        test_metadata = [{'positive_prompt': f"prompt {i}"} for i in range(100)]
        dialog = WCCreatorDialog(test_images, test_metadata, WC_FORMAT_HASH_COMMENT)
        self.assertEqual(len(dialog.selected_file_paths), 100)
        self.assertEqual(len(dialog.metadata_list), 100)

    def test_image_format_handling(self):
        """異なる画像フォーマットのテスト"""
        test_images = [
            os.path.join(self.test_data_dir, 'images', 'test.png'),
            os.path.join(self.test_data_dir, 'images', 'test.gif'),
            os.path.join(self.test_data_dir, 'images', 'test.bmp')
        ]
        for img in test_images:
            with patch('src.wc_controller.QImage') as MockQImageClass: # Patch QImage in wc_controller
                mock_qimage_instance = MockQImageClass.return_value
                mock_qimage_instance.load.return_value = True # Simulate successful load
                mock_qimage_instance.isNull.return_value = False
                result = self.controller.load_image_data(img) # Use img instead of img_path
                self.assertTrue(result)
                mock_qimage_instance.load.assert_called_with(img) # Use img instead of img_path

    def test_threaded_ui_updates(self):
        """マルチスレッド環境でのUI更新テスト"""
        class Worker(QThread):
            update_signal = pyqtSignal(str)

            def run(self):
                self.update_signal.emit("test update")

        # dialog = WCCreatorDialog([self.test_images[0]], [self.test_metadata[0]], WC_FORMAT_HASH_COMMENT) # Not needed for controller test
        worker = Worker()
        spy = QSignalSpy(worker.update_signal)
        worker.update_signal.connect(self.controller.update_status) # Connect to controller's slot
        worker.start()
        worker.wait()
        self.assertEqual(len(spy), 1)
        self.assertEqual(spy[0][0], "test update")

if __name__ == '__main__':
    unittest.main()
