import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtTest import QSignalSpy

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.wc_controller import WCController

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

    def test_load_invalid_image_path(self):
        """無効な画像パスを渡した場合のテスト"""
        # 存在しないファイルパスでテスト
        result = self.controller.load_image_data('invalid_path_that_does_not_exist.jpg')
        self.assertFalse(result)
        
    def test_load_valid_image(self):
        """有効な画像パスを渡した場合のテスト"""
        # テスト用画像ファイルを準備
        test_image = os.path.join(self.test_data_dir, 'images', 'test1.jpg')
        if os.path.exists(test_image):
            result = self.controller.load_image_data(test_image)
            self.assertTrue(result)

    def test_threaded_ui_updates(self):
        """マルチスレッド環境でのUI更新テスト"""
        class Worker(QThread):
            update_signal = pyqtSignal(str)

            def run(self):
                self.update_signal.emit("test update")

        controller = WCController()
        worker = Worker()
        spy = QSignalSpy(worker.update_signal)
        worker.update_signal.connect(controller.update_status)
        worker.start()
        worker.wait()
        self.assertEqual(len(spy), 1)
        self.assertEqual(spy[0][0], "test update")

if __name__ == '__main__':
    unittest.main()
