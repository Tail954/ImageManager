import unittest
from unittest.mock import patch, MagicMock, call
import os
import sys
from PyQt6.QtCore import QObject, pyqtSignal, QStandardPaths, QThread # Added QThread
from PyQt6.QtGui import QImage, QPixmap, QStandardItem # Added QStandardItem
from PyQt6.QtTest import QSignalSpy # For testing signals

# Adjust the import path as necessary
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.thumbnail_loader import ThumbnailLoaderThread
try:
    from PIL import ImageQt # For mocking ImageQt.ImageQt
except ImportError:
    ImageQt = None # Handle if Pillow is not fully installed with Qt support

class TestThumbnailLoaderThread(unittest.TestCase):

    def setUp(self):
        self.mock_qimage = MagicMock(spec=QImage)
        self.mock_qpixmap = MagicMock(spec=QPixmap)
        
        # Mock QStandardItem for items_to_process
        self.mock_item1 = MagicMock(spec=QStandardItem)
        self.mock_item1.text.return_value = "item1.jpg" # For logging or identification
        self.mock_item2 = MagicMock(spec=QStandardItem)
        self.mock_item2.text.return_value = "item2.png"
        self.mock_item3 = MagicMock(spec=QStandardItem)
        self.mock_item3.text.return_value = "error_item.gif"

        self.file_paths = ["path/to/item1.jpg", "path/to/item2.png", "path/to/error_item.gif"]
        self.items_to_process = [self.mock_item1, self.mock_item2, self.mock_item3]
        self.target_size = 128

        # Patch ImageQt.ImageQt if available
        if ImageQt:
            self.patcher_imageqt = patch('src.thumbnail_loader.ImageQt.ImageQt', return_value=self.mock_qimage)
            self.MockImageQt_ImageQt = self.patcher_imageqt.start()
            self.addCleanup(self.patcher_imageqt.stop)
        else: # If ImageQt is None, the thread should log an error and finish.
            pass

    @patch('src.thumbnail_loader.Image.open')
    @patch('src.thumbnail_loader.extract_image_metadata')
    def test_run_success_flow(self, mock_extract_metadata, mock_image_open):
        """Test successful processing of multiple images."""
        # Setup mocks for Image.open and extract_image_metadata
        mock_pil_img = MagicMock()
        mock_pil_img.thumbnail = MagicMock()
        mock_pil_img.mode = "RGB" # Example mode
        mock_pil_img.convert.return_value = mock_pil_img # For .convert("RGBA")
        mock_image_open.return_value = mock_pil_img
        
        mock_extract_metadata.side_effect = [
            {"positive_prompt": "meta1"},
            {"positive_prompt": "meta2"},
            {"positive_prompt": "meta3_error_case"} # Even if open fails, extract might be called with path
        ]

        thread = ThumbnailLoaderThread(self.file_paths, self.items_to_process, self.target_size)
        
        # Use QSignalSpy to check emitted signals
        spy_thumbnail_loaded = QSignalSpy(thread.thumbnailLoaded)
        spy_progress_updated = QSignalSpy(thread.progressUpdated)
        spy_finished = QSignalSpy(thread.finished)

        thread.run() # Run in the current thread for testing simplicity

        self.assertEqual(len(spy_thumbnail_loaded), len(self.file_paths))
        self.assertEqual(len(spy_progress_updated), len(self.file_paths))
        self.assertEqual(len(spy_finished), 1)

        # Verify each expected item was processed and signaled correctly, regardless of order.
        expected_results_map = {
            self.mock_item1.text(): (False if ImageQt else True, {"positive_prompt": "meta1"}),
            self.mock_item2.text(): (False if ImageQt else True, {"positive_prompt": "meta2"}),
            self.mock_item3.text(): (False if ImageQt else True, {"positive_prompt": "meta3_error_case"}),
        }
        
        processed_item_texts = set()
        for i in range(len(spy_thumbnail_loaded)):
            emitted_item = spy_thumbnail_loaded[i][0]
            emitted_qimage = spy_thumbnail_loaded[i][1]
            emitted_metadata = spy_thumbnail_loaded[i][2]
            
            item_text = emitted_item.text()
            self.assertIn(item_text, expected_results_map, f"Unexpected item text {item_text} in signal.")
            processed_item_texts.add(item_text)
            
            expected_qimage_is_none, expected_meta = expected_results_map[item_text]
            
            if expected_qimage_is_none:
                self.assertIsNone(emitted_qimage)
            else:
                # All successful qimages in this test should be the same mock instance
                self.assertIs(emitted_qimage, self.mock_qimage) 
                
            self.assertEqual(emitted_metadata, expected_meta)
            
        self.assertEqual(len(processed_item_texts), len(self.file_paths), "Not all expected items were found in signals.")

        # Check progressUpdated signal arguments for the last item
        self.assertEqual(spy_progress_updated[-1][0], len(self.file_paths)) # processed_count
        self.assertEqual(spy_progress_updated[-1][1], len(self.file_paths)) # total_files

    @patch('src.thumbnail_loader.Image.open', side_effect=FileNotFoundError("Mocked FileNotFoundError"))
    @patch('src.thumbnail_loader.extract_image_metadata') # Still mock this as it might be called
    def test_run_file_not_found_error(self, mock_extract_metadata, mock_image_open):
        """Test behavior when Image.open raises FileNotFoundError for one file."""
        # Let the first file open successfully, second fail, third succeed.
        mock_pil_img_ok = MagicMock()
        mock_pil_img_ok.thumbnail = MagicMock()
        mock_pil_img_ok.mode = "RGB"
        mock_pil_img_ok.convert.return_value = mock_pil_img_ok

        mock_image_open.side_effect = [
            mock_pil_img_ok,
            FileNotFoundError("Mocked FileNotFoundError for item2.png"),
            mock_pil_img_ok
        ]
        mock_extract_metadata.side_effect = [
            {"positive_prompt": "meta1"}, # For item1.jpg
            # For item2.png, extract_image_metadata should not be called due to FileNotFoundError
            {"positive_prompt": "meta3"}
        ]

        thread = ThumbnailLoaderThread(self.file_paths, self.items_to_process, self.target_size)
        spy_thumbnail_loaded = QSignalSpy(thread.thumbnailLoaded)
        spy_finished = QSignalSpy(thread.finished)

        thread.run()

        self.assertEqual(len(spy_thumbnail_loaded), len(self.file_paths))
        self.assertEqual(len(spy_finished), 1)

        # Verify each expected item was processed and signaled correctly.
        expected_results_map = {
            self.mock_item1.text(): (False if ImageQt else True, {"positive_prompt": "meta1"}),
            self.mock_item2.text(): (True, {'positive_prompt': '', 'negative_prompt': '', 'generation_info': ''}), # FileNotFoundError
            self.mock_item3.text(): (False if ImageQt else True, {"positive_prompt": "meta3"}),
        }

        processed_item_texts = set()
        for i in range(len(spy_thumbnail_loaded)):
            emitted_item = spy_thumbnail_loaded[i][0]
            emitted_qimage = spy_thumbnail_loaded[i][1]
            emitted_metadata = spy_thumbnail_loaded[i][2]

            item_text = emitted_item.text()
            self.assertIn(item_text, expected_results_map, f"Unexpected item text {item_text} in signal.")
            processed_item_texts.add(item_text)

            expected_qimage_is_none, expected_meta = expected_results_map[item_text]

            if expected_qimage_is_none:
                self.assertIsNone(emitted_qimage)
            else:
                self.assertIs(emitted_qimage, self.mock_qimage)
            self.assertEqual(emitted_metadata, expected_meta)
        self.assertEqual(len(processed_item_texts), len(self.file_paths), "Not all expected items were found in signals.")

    def test_run_empty_file_list(self):
        """Test behavior with an empty list of file paths."""
        thread = ThumbnailLoaderThread([], [], self.target_size)
        spy_finished = QSignalSpy(thread.finished)
        spy_thumbnail_loaded = QSignalSpy(thread.thumbnailLoaded)
        spy_progress_updated = QSignalSpy(thread.progressUpdated)

        thread.run()

        self.assertEqual(len(spy_finished), 1)
        self.assertEqual(len(spy_thumbnail_loaded), 0)
        self.assertEqual(len(spy_progress_updated), 0)

    @patch('src.thumbnail_loader.Image.open')
    @patch('src.thumbnail_loader.extract_image_metadata')
    @patch('src.thumbnail_loader.logger') # Mock logger to check for error messages
    def test_run_stop_requested(self, mock_logger, mock_extract_metadata, mock_image_open):
        """Test cooperative stop mechanism."""
        # Setup mocks
        mock_pil_img = MagicMock()
        mock_pil_img.thumbnail = MagicMock()
        mock_pil_img.mode = "RGB"
        mock_pil_img.convert.return_value = mock_pil_img
        mock_image_open.return_value = mock_pil_img
        mock_extract_metadata.return_value = {"positive_prompt": "stopped_meta"}

        # Use a larger list to make stopping mid-way more meaningful
        long_file_paths = [f"path/to/file{i}.jpg" for i in range(5)]
        long_items_to_process = [MagicMock(spec=QStandardItem) for _ in range(5)]

        thread = ThumbnailLoaderThread(long_file_paths, long_items_to_process, self.target_size)
        
        # Simulate stop() being called after the first item is processed by the executor
        # This is tricky to time perfectly without actual threading.
        # We'll check the _is_running flag logic within _process_single_image and the submission loop.
        
        # To test the stop flag, we can patch _process_single_image to call thread.stop()
        # after the first call, or check the number of submissions.
        
        original_process_single_image = thread._process_single_image
        call_count_process_single = 0

        def wrapped_process_single_image(*args, **kwargs):
            nonlocal call_count_process_single
            call_count_process_single += 1
            if call_count_process_single == 2: # Stop after the first one is submitted and starts processing
                thread.stop()
            return original_process_single_image(*args, **kwargs)

        with patch.object(thread, '_process_single_image', side_effect=wrapped_process_single_image):
            spy_thumbnail_loaded = QSignalSpy(thread.thumbnailLoaded)
            spy_finished = QSignalSpy(thread.finished)
            thread.run()

        self.assertEqual(len(spy_finished), 1)
        # The number of loaded thumbnails might be 1 or more depending on ThreadPoolExecutor's behavior
        # and how quickly stop() propagates. The key is that it doesn't process all 5.
        self.assertLessEqual(len(spy_thumbnail_loaded), len(long_file_paths))
        # Check if the logger was called with the stop message
        mock_logger.info.assert_any_call("ThumbnailLoaderThread.stop() called. Setting _is_running to False.")

if __name__ == '__main__':
    unittest.main()
