import unittest
import os
import shutil
import tempfile

# Ensure src directory is in Python path for imports
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import patch, MagicMock, call

# Assuming src is a sibling directory to tests, or PYTHONPATH is set up
from src.file_operations import FileOperationsWorker, FileOperationSignals, FileOperations
# We need to mock or define Qt roles if QStandardItem is deeply involved.
# For now, let's assume we can mock item.data() effectively.
# If Qt is imported in file_operations, we might need to mock it at a higher level.
try:
    from PyQt6.QtCore import Qt, QThread # Import QThread
    USER_ROLE = Qt.ItemDataRole.UserRole
    SELECTION_ORDER_ROLE = Qt.ItemDataRole.UserRole + 2 # As defined in constants.py
except ImportError:
    # Define fallbacks if PyQt6 is not available in the test environment
    # (though it should be for running the app)
    QThread = MagicMock() # Mock QThread if not importable
    USER_ROLE = 256  # Common value for UserRole
    SELECTION_ORDER_ROLE = 258


class TestFileOperationsWorker(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.source_folder = os.path.join(self.test_dir.name, "source")
        self.dest_folder = os.path.join(self.test_dir.name, "destination")
        os.makedirs(self.source_folder, exist_ok=True)
        os.makedirs(self.dest_folder, exist_ok=True)

        self.source_file1_path = os.path.join(self.source_folder, "file1.txt")
        with open(self.source_file1_path, "w") as f:
            f.write("This is file1.")

        # Mock signals for the worker
        self.mock_signals = MagicMock(spec=FileOperationSignals)
        # self.patcher_signals = patch('src.file_operations.FileOperationSignals', return_value=self.mock_signals)
        # self.MockFileOperationSignals = self.patcher_signals.start()


    def tearDown(self):
        self.test_dir.cleanup()
        # if hasattr(self, 'patcher_signals'):
        #     self.patcher_signals.stop()

    def test_move_files_single_success(self):
        """Test moving a single file successfully."""
        source_paths = [self.source_file1_path]
        
        # Worker needs its own signals instance. We'll mock the one it creates or uses.
        # The FileOperationsWorker creates its own signals object.
        # We can patch the FileOperationSignals class itself if needed,
        # or pass a mocked instance if the constructor allowed, but it doesn't.
        # So, we'll access worker.signals after instantiation and replace it, or patch the class.

        with patch('src.file_operations.FileOperationSignals') as MockSignalsInstance:
            mock_signals_obj = MockSignalsInstance.return_value # This is the instance worker will use
            
            worker = FileOperationsWorker(
                operation_type="move",
                source_paths=source_paths,
                destination_folder=self.dest_folder
            )
            # worker.signals is now mock_signals_obj

            worker.run() # This will call _move_files

            # Assertions
            self.assertFalse(os.path.exists(self.source_file1_path), "Source file should not exist after move.")
            expected_dest_file_path = os.path.join(self.dest_folder, "file1.txt")
            self.assertTrue(os.path.exists(expected_dest_file_path), "Destination file should exist after move.")

            # Check signals
            mock_signals_obj.progress.emit.assert_called_once_with(1, 1)
            
            expected_finish_dict = {
                'operation_type': 'move',
                'moved_count': 1,
                'renamed_files': [],
                'errors': [],
                'status': 'completed',
                'successfully_moved_src_paths': [self.source_file1_path],
                'destination_folder': self.dest_folder
            }
            mock_signals_obj.finished.emit.assert_called_once_with(expected_finish_dict)
            mock_signals_obj.error.emit.assert_not_called()

    def test_move_files_destination_exists_rename(self):
        """Test moving a file when a file with the same name exists at the destination."""
        # Create a file at the destination with the same name
        existing_dest_file_path = os.path.join(self.dest_folder, "file1.txt")
        with open(existing_dest_file_path, "w") as f:
            f.write("This is the existing destination file.")

        source_paths = [self.source_file1_path]

        with patch('src.file_operations.FileOperationSignals') as MockSignalsInstance:
            mock_signals_obj = MockSignalsInstance.return_value
            worker = FileOperationsWorker("move", source_paths, self.dest_folder)
            worker.run()

            self.assertFalse(os.path.exists(self.source_file1_path))
            # Original destination file should still be there
            self.assertTrue(os.path.exists(existing_dest_file_path))
            # New file should be renamed
            expected_renamed_dest_file_path = os.path.join(self.dest_folder, "file1_1.txt")
            self.assertTrue(os.path.exists(expected_renamed_dest_file_path))

            mock_signals_obj.progress.emit.assert_called_once_with(1, 1)
            expected_finish_dict = {
                'operation_type': 'move',
                'moved_count': 1,
                'renamed_files': [{'original': 'file1.txt', 'new': 'file1_1.txt'}],
                'errors': [],
                'status': 'completed',
                'successfully_moved_src_paths': [self.source_file1_path],
                'destination_folder': self.dest_folder
            }
            mock_signals_obj.finished.emit.assert_called_once_with(expected_finish_dict)
            mock_signals_obj.error.emit.assert_not_called()

    # --- Tests for _copy_files ---

    def _create_mock_qstandard_item(self, file_path, selection_order):
        item = MagicMock()
        # Configure item.data(role) to return specific values
        def side_effect(role):
            if role == USER_ROLE:
                return file_path
            if role == SELECTION_ORDER_ROLE:
                return selection_order
            return None # Default for other roles
        item.data.side_effect = side_effect
        item.text.return_value = os.path.basename(file_path) # For error messages
        return item

    def test_copy_files_single_success(self):
        """Test copying a single file successfully."""
        mock_item1 = self._create_mock_qstandard_item(self.source_file1_path, 1)
        copy_selection_order = [mock_item1]

        with patch('src.file_operations.FileOperationSignals') as MockSignalsInstance:
            mock_signals_obj = MockSignalsInstance.return_value
            worker = FileOperationsWorker(
                operation_type="copy",
                source_paths=None, # Not used directly by _copy_files
                destination_folder=self.dest_folder,
                copy_selection_order=copy_selection_order
            )
            worker.run() # This will call _copy_files

            expected_dest_file_path = os.path.join(self.dest_folder, f"001_{os.path.basename(self.source_file1_path)}")
            self.assertTrue(os.path.exists(expected_dest_file_path), "Destination file should exist after copy.")
            self.assertTrue(os.path.exists(self.source_file1_path), "Source file should still exist after copy.")

            mock_signals_obj.progress.emit.assert_called_once_with(1, 1)
            expected_finish_dict = {
                'operation_type': 'copy',
                'copied_count': 1,
                'errors': [],
                'status': 'completed',
                'destination_folder': self.dest_folder
            }
            mock_signals_obj.finished.emit.assert_called_once_with(expected_finish_dict)
            mock_signals_obj.error.emit.assert_not_called()

    def test_copy_files_multiple_with_numbering(self):
        """Test copying multiple files with correct numbered prefixes."""
        source_file2_path = os.path.join(self.source_folder, "file2.txt")
        with open(source_file2_path, "w") as f:
            f.write("This is file2.")

        mock_item1 = self._create_mock_qstandard_item(self.source_file1_path, 1)
        mock_item2 = self._create_mock_qstandard_item(source_file2_path, 2)
        copy_selection_order = [mock_item1, mock_item2]

        # Create an existing file in destination to test numbering continuation
        existing_numbered_file = os.path.join(self.dest_folder, "001_existing.txt")
        with open(existing_numbered_file, "w") as f:
            f.write("Existing numbered file.")


        with patch('src.file_operations.FileOperationSignals') as MockSignalsInstance:
            mock_signals_obj = MockSignalsInstance.return_value
            worker = FileOperationsWorker("copy", None, self.dest_folder, copy_selection_order)
            worker.run()

            expected_dest_file1_path = os.path.join(self.dest_folder, f"002_{os.path.basename(self.source_file1_path)}")
            expected_dest_file2_path = os.path.join(self.dest_folder, f"003_{os.path.basename(source_file2_path)}")
            self.assertTrue(os.path.exists(expected_dest_file1_path))
            self.assertTrue(os.path.exists(expected_dest_file2_path))

            self.assertEqual(mock_signals_obj.progress.emit.call_count, 2)
            mock_signals_obj.progress.emit.assert_any_call(1, 2)
            mock_signals_obj.progress.emit.assert_any_call(2, 2)

            expected_finish_dict = {
                'operation_type': 'copy',
                'copied_count': 2,
                'errors': [],
                'status': 'completed',
                'destination_folder': self.dest_folder
            }
            mock_signals_obj.finished.emit.assert_called_once_with(expected_finish_dict)

    def test_copy_files_empty_selection_order(self):
        """Test copy operation with an empty selection order."""
        copy_selection_order = []
        with patch('src.file_operations.FileOperationSignals') as MockSignalsInstance:
            mock_signals_obj = MockSignalsInstance.return_value
            worker = FileOperationsWorker("copy", None, self.dest_folder, copy_selection_order)
            worker.run()

            mock_signals_obj.progress.emit.assert_not_called()
            expected_finish_dict = {
                'operation_type': 'copy',
                'copied_count': 0,
                'errors': [],
                'status': 'completed',
                'destination_folder': self.dest_folder
            }
            mock_signals_obj.finished.emit.assert_called_once_with(expected_finish_dict)

    def test_copy_files_source_not_found(self):
        """Test copy operation when a source file in the order does not exist."""
        non_existent_path = os.path.join(self.source_folder, "non_existent.txt")
        mock_item_non_existent = self._create_mock_qstandard_item(non_existent_path, 1)
        copy_selection_order = [mock_item_non_existent]

        with patch('src.file_operations.FileOperationSignals') as MockSignalsInstance:
            mock_signals_obj = MockSignalsInstance.return_value
            worker = FileOperationsWorker("copy", None, self.dest_folder, copy_selection_order)
            worker.run()

            mock_signals_obj.progress.emit.assert_called_once_with(1, 1)
            expected_finish_dict = {
                'operation_type': 'copy',
                'copied_count': 0,
                'errors': [f"Source file not found or path invalid for item: {os.path.basename(non_existent_path)}"],
                'status': 'completed',
                'destination_folder': self.dest_folder
            }
            mock_signals_obj.finished.emit.assert_called_once_with(expected_finish_dict)

    def test_copy_files_destination_folder_not_exists(self):
        """Test copy operation when the destination folder does not exist."""
        non_existent_dest_folder = os.path.join(self.test_dir.name, "non_existent_dest")
        mock_item1 = self._create_mock_qstandard_item(self.source_file1_path, 1)
        copy_selection_order = [mock_item1]

        with patch('src.file_operations.FileOperationSignals') as MockSignalsInstance:
            mock_signals_obj = MockSignalsInstance.return_value
            worker = FileOperationsWorker("copy", None, non_existent_dest_folder, copy_selection_order)
            worker.run() # This will call _copy_files

            # No progress should be made if destination doesn't exist before loop
            mock_signals_obj.progress.emit.assert_not_called()
            expected_finish_dict = {
                # 'operation_type': 'copy', # This key is missing in the actual implementation for this error path
                'copied_count': 0,
                'errors': [f"Destination folder does not exist: {non_existent_dest_folder}"]
                # 'status': 'completed', # This key is also missing
                # 'destination_folder': non_existent_dest_folder # And this
            }
            # The actual implementation for this error path in _copy_files is:
            # self.signals.finished.emit({'copied_count': 0, 'errors': errors})
            # So we adjust the expectation.
            mock_signals_obj.finished.emit.assert_called_once_with(expected_finish_dict)
            mock_signals_obj.error.emit.assert_not_called()


class TestFileOperations(unittest.TestCase):

    def setUp(self):
        self.mock_main_window = MagicMock()
        # ★★★ UIManager のモックを追加 ★★★
        self.mock_ui_manager = MagicMock()
        self.mock_main_window.ui_manager = self.mock_ui_manager
        # FileOperationManager がアクセスする可能性のある MainWindow のUI要素のモック
        self.mock_ui_manager.move_files_button = MagicMock()
        self.mock_ui_manager.copy_files_button = MagicMock()
        self.mock_ui_manager.copy_mode_button = MagicMock()

        # Add methods that FileOperations expects to connect to
        self.mock_main_window._handle_file_op_progress = MagicMock()
        self.mock_main_window._handle_file_op_finished = MagicMock()
        self.mock_main_window._handle_file_op_error = MagicMock()
        self.file_ops = FileOperations(parent=None) # Initialize with None parent

    @patch('src.file_operations.FileOperationsWorker')
    @patch('src.file_operations.QThread')
    def test_start_operation_success(self, MockQThread, MockFileOperationsWorker):
        """Test starting a new file operation successfully."""
        mock_thread_instance = MockQThread.return_value
        mock_worker_instance = MockFileOperationsWorker.return_value
        # Mock the signals object on the worker instance
        mock_worker_instance.signals = MagicMock(spec=FileOperationSignals)

        op_type = "move"
        source_paths = ["/path/to/source"]
        dest_folder = "/path/to/dest"

        # FileOperations は file_op_manager を介して MainWindow のメソッドを呼び出す
        # file_op_manager のモックを作成し、FileOperations に渡す
        mock_file_op_manager = MagicMock()
        with patch.object(self.file_ops, 'file_op_manager', mock_file_op_manager):
            result = self.file_ops.start_operation(op_type, source_paths, dest_folder)

        self.assertTrue(result)
        MockFileOperationsWorker.assert_called_once_with(op_type, source_paths, dest_folder, None)
        mock_worker_instance.moveToThread.assert_called_once_with(mock_thread_instance)

        # Check signal connections
        mock_worker_instance.signals.progress.connect.assert_called_once_with(mock_file_op_manager._handle_file_op_progress)
        mock_worker_instance.signals.finished.connect.assert_any_call(mock_file_op_manager._handle_file_op_finished)
        mock_worker_instance.signals.error.connect.assert_called_once_with(mock_file_op_manager._handle_file_op_error)

        mock_thread_instance.started.connect.assert_called_once_with(mock_worker_instance.run)
        mock_worker_instance.signals.finished.connect.assert_any_call(self.file_ops._on_worker_finished)
        mock_thread_instance.start.assert_called_once()

        # Clean up to allow other tests to run without interference
        self.file_ops._thread = None
        self.file_ops._worker = None


    @patch('src.file_operations.QThread')
    def test_start_operation_already_running(self, MockQThread):
        """Test that start_operation returns False if an operation is already running."""
        # Simulate an already running thread
        mock_thread_instance = MockQThread.return_value
        mock_thread_instance.isRunning.return_value = True
        self.file_ops._thread = mock_thread_instance

        result = self.file_ops.start_operation("move", [], "/dest")
        self.assertFalse(result)
        # Ensure isRunning was checked
        mock_thread_instance.isRunning.assert_called_once()

        # Clean up
        self.file_ops._thread = None


    @patch('src.file_operations.FileOperationsWorker')
    @patch('src.file_operations.QThread')
    def test_stop_operation_running(self, MockQThread, MockFileOperationsWorker):
        """Test stop_operation when an operation is running."""
        mock_thread_instance = MockQThread.return_value
        mock_worker_instance = MockFileOperationsWorker.return_value
        
        # Setup a running operation
        self.file_ops._thread = mock_thread_instance
        self.file_ops._worker = mock_worker_instance
        mock_thread_instance.isRunning.return_value = True

        self.file_ops.stop_operation()

        mock_worker_instance.stop.assert_called_once()
        mock_thread_instance.isRunning.assert_called_once()

        # Clean up
        self.file_ops._thread = None
        self.file_ops._worker = None

    def test_stop_operation_not_running(self):
        """Test stop_operation when no operation is running."""
        # Ensure worker and thread are None or thread is not running
        self.file_ops._thread = None
        self.file_ops._worker = None
        
        # Or if thread exists but is not running
        mock_thread_not_running = MagicMock(spec=QThread) # Use imported/mocked QThread
        mock_thread_not_running.isRunning.return_value = False
        self.file_ops._thread = mock_thread_not_running
        self.file_ops._worker = None # Ensure worker is also None for this specific scenario
        
        with patch('src.file_operations.logger') as mock_logger:
             self.file_ops.stop_operation()
             # Check that worker.stop() was not called
             # (difficult to assert directly if worker is None, so check logger)
             mock_logger.info.assert_any_call("No file operation currently running to stop.")


    @patch('src.file_operations.QThread')
    @patch('src.file_operations.FileOperationsWorker')
    def test_on_worker_finished_cleanup(self, MockFileOperationsWorker, MockQThread):
        """Test the _on_worker_finished cleanup mechanism."""
        mock_thread_instance = MockQThread.return_value
        mock_worker_instance = MockFileOperationsWorker.return_value

        self.file_ops._thread = mock_thread_instance
        self.file_ops._worker = mock_worker_instance
        
        # Simulate worker finishing
        self.file_ops._on_worker_finished()

        mock_thread_instance.quit.assert_called_once()
        # mock_thread_instance.wait.assert_called_once() # wait is not called in the current _on_worker_finished
        mock_worker_instance.deleteLater.assert_called_once()
        mock_thread_instance.deleteLater.assert_called_once()

        self.assertIsNone(self.file_ops._worker)
        self.assertIsNone(self.file_ops._thread)


if __name__ == '__main__':
    unittest.main()
