import os
import shutil
import logging
import re # For copy filename parsing
from pathlib import Path
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt # Import Qt
from .constants import SELECTION_ORDER_ROLE # Import SELECTION_ORDER_ROLE

logger = logging.getLogger(__name__)

class FileOperationSignals(QObject):
    progress = pyqtSignal(int, int) # processed_count, total_count
    finished = pyqtSignal(dict) # result_summary
    error = pyqtSignal(str)

class FileOperationsWorker(QObject):
    def __init__(self, operation_type, source_paths, destination_folder, copy_selection_order=None):
        super().__init__()
        self.signals = FileOperationSignals()
        self.operation_type = operation_type # "move" or "copy"
        self.source_paths = source_paths
        self.destination_folder = destination_folder
        self.copy_selection_order = copy_selection_order # Only for copy, list of QStandardItem
        self._is_running = True

    def run(self):
        if self.operation_type == "move":
            self._move_files()
        elif self.operation_type == "copy":
            self._copy_files()
        else:
            self.signals.error.emit(f"Unknown operation type: {self.operation_type}")
            self.signals.finished.emit({'status': 'error', 'message': 'Unknown operation'})

    def stop(self):
        self._is_running = False
        logger.info(f"{self.operation_type} operation requested to stop.")

    def _move_files(self):
        moved_count = 0
        renamed_files_info = [] # List of tuples (original_basename, new_basename)
        errors = []
        successfully_moved_src_paths = [] # Store successfully moved source paths
        total_files = len(self.source_paths)

        if not os.path.isdir(self.destination_folder):
            errors.append(f"Destination folder does not exist: {self.destination_folder}")
            self.signals.finished.emit({'operation_type': 'move', 'moved_count': 0, 'renamed_files': [], 'errors': errors, 'successfully_moved_src_paths': []})
            return

        for i, src_path in enumerate(self.source_paths):
            if not self._is_running:
                self.signals.finished.emit({'status': 'cancelled', 'moved_count': moved_count, 'renamed_files': renamed_files_info, 'errors': errors})
                return

            if not os.path.exists(src_path):
                errors.append(f"Source file not found: {os.path.basename(src_path)}")
                self.signals.progress.emit(i + 1, total_files)
                continue

            original_basename = os.path.basename(src_path)
            base_name, ext = os.path.splitext(original_basename)
            dest_path_candidate = os.path.join(self.destination_folder, original_basename)
            
            actual_dest_path = dest_path_candidate
            counter = 1
            while os.path.exists(actual_dest_path):
                actual_dest_path = os.path.join(self.destination_folder, f"{base_name}_{counter}{ext}")
                counter += 1
            
            try:
                shutil.move(src_path, actual_dest_path)
                moved_count += 1
                successfully_moved_src_paths.append(src_path) # Add to successful list
                new_basename = os.path.basename(actual_dest_path)
                if new_basename != original_basename: # Renamed_files_info is used to show a dialog
                    renamed_files_info.append({'original': original_basename, 'new': new_basename})
                # logger.info(f"Moved: {src_path} -> {actual_dest_path}") # コメントアウト
            except Exception as e:
                error_msg = f"Error moving {original_basename}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
            
            self.signals.progress.emit(i + 1, total_files)

        self.signals.finished.emit({
            'operation_type': 'move',
            'moved_count': moved_count,
            'renamed_files': renamed_files_info,
            'errors': errors,
            'status': 'completed',
            'successfully_moved_src_paths': successfully_moved_src_paths,
            'destination_folder': self.destination_folder # Add destination_folder
        })

    def _copy_files(self):
        # self.source_paths here are the QStandardItems from copy_selection_order
        # We need to extract file paths from them.
        copied_count = 0
        errors = []
        total_files = len(self.copy_selection_order)
        
        if not os.path.isdir(self.destination_folder):
            errors.append(f"Destination folder does not exist: {self.destination_folder}")
            self.signals.finished.emit({'copied_count': 0, 'errors': errors})
            return

        # Determine the starting number for copied files
        next_copy_number = 1
        try:
            existing_files = [f for f in os.listdir(self.destination_folder) if os.path.isfile(os.path.join(self.destination_folder, f))]
            existing_numbers = []
            for f_name in existing_files:
                match = re.match(r'^(\d+)_', f_name)
                if match:
                    try:
                        num = int(match.group(1))
                        existing_numbers.append(num)
                    except ValueError:
                        continue
            if existing_numbers:
                next_copy_number = max(existing_numbers) + 1
        except Exception as e:
            logger.error(f"Error determining next copy number: {e}", exc_info=True)
            errors.append(f"Could not read destination folder contents for numbering: {e}")
            # Continue with next_copy_number = 1 if error occurs

        for i, item in enumerate(self.copy_selection_order):
            if not self._is_running:
                self.signals.finished.emit({'status': 'cancelled', 'copied_count': copied_count, 'errors': errors})
                return

            # Assuming SELECTION_ORDER_ROLE and UserRole are accessible or defined
            # For simplicity, directly use UserRole for file path if SELECTION_ORDER_ROLE is not found on item
            # This part needs to align with how MainWindow stores data in items.
            # Let's assume UserRole stores the file path.
            src_path = item.data(Qt.ItemDataRole.UserRole) # UserRole should store the original file path
            selection_num = item.data(SELECTION_ORDER_ROLE) # This is the 1-based order from UI

            if not src_path or not os.path.exists(src_path):
                errors.append(f"Source file not found or path invalid for item: {item.text() if item else 'UnknownItem'}")
                self.signals.progress.emit(i + 1, total_files)
                continue

            original_basename = os.path.basename(src_path)
            # New filename based on the determined next_copy_number
            new_filename = f"{next_copy_number:03}_{original_basename}"
            dest_path_candidate = os.path.join(self.destination_folder, new_filename)

            # Handle potential name collisions for the *newly constructed* filename (e.g., if user manually created 001_file.jpg)
            # This is different from move, where collision is on original_basename.
            actual_dest_path = dest_path_candidate
            # No need for _1, _2 suffix for copy as per requirements, numbers should be unique.
            # If 001_file.jpg exists, next should be 002_otherfile.jpg.
            # The check for existing_numbers should handle this.
            # However, if by some chance a file like "001_somefile.jpg" already exists and we are trying to create it again
            # (e.g. if the numbering logic had a flaw or manual intervention), we might need a fallback.
            # For now, we assume next_copy_number logic correctly avoids direct collision for the *numbered* part.

            try:
                shutil.copy2(src_path, actual_dest_path) # copy2 preserves metadata
                copied_count += 1
                # logger.info(f"Copied: {src_path} -> {actual_dest_path} (UI order: {selection_num})") # コメントアウト
                next_copy_number += 1 # Increment for the next file
            except Exception as e:
                error_msg = f"Error copying {original_basename}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
            
            self.signals.progress.emit(i + 1, total_files)
            
        self.signals.finished.emit({
            'operation_type': 'copy',
            'copied_count': copied_count,
            'errors': errors,
            'status': 'completed',
            'destination_folder': self.destination_folder # Add destination_folder
        })


class FileOperations(QObject):
    def __init__(self, parent=None, file_op_manager=None): # file_op_manager を追加
        super().__init__(parent)
        self._thread = None # Use a private attribute
        self._worker = None # Use a private attribute
        self.file_op_manager = file_op_manager # file_op_manager を保持

    def start_operation(self, operation_type, source_paths, destination_folder, copy_selection_order=None):
        if self._thread is not None and self._thread.isRunning():
            logger.warning("Another file operation is already in progress.")
            return False

        # Ensure previous thread and worker are cleaned up if they exist but are not running
        if self._thread is not None:
            self._thread.quit() # Attempt to quit
            self._thread.wait(100) # Wait a bit for it to finish
            # self._thread.deleteLater() # Schedule for deletion, will be None after this
            self._thread = None 
        if self._worker is not None:
            # self._worker.deleteLater()
            self._worker = None

        self._thread = QThread(self) # Set parent to FileOperations instance
        self._worker = FileOperationsWorker(operation_type, source_paths, destination_folder, copy_selection_order)
        self._worker.moveToThread(self._thread)

        # Connect signals from worker to slots in FileOperationManager
        if self.file_op_manager: # file_op_manager が渡されていれば接続
            if hasattr(self.file_op_manager, '_handle_file_op_progress'):
                self._worker.signals.progress.connect(self.file_op_manager._handle_file_op_progress)
            if hasattr(self.file_op_manager, '_handle_file_op_finished'):
                self._worker.signals.finished.connect(self.file_op_manager._handle_file_op_finished) # Connect to manager's finished
            if hasattr(self.file_op_manager, '_handle_file_op_error'):
                self._worker.signals.error.connect(self.file_op_manager._handle_file_op_error)
        else:
            # MainWindowへの直接接続のフォールバック（テストなどでfile_op_managerがNoneの場合）
            # ただし、今回のリファクタリングでは常にfile_op_manager経由にするのが望ましい
            main_window = self.parent()
            if main_window:
                logger.warning("FileOperations: file_op_manager not provided, attempting to connect to parent (MainWindow).")
                if hasattr(main_window, '_handle_file_op_progress'): # Assuming MainWindow still has these for fallback
                    self._worker.signals.progress.connect(main_window._handle_file_op_progress)
                if hasattr(main_window, '_handle_file_op_finished'):
                    self._worker.signals.finished.connect(main_window._handle_file_op_finished)
                if hasattr(main_window, '_handle_file_op_error'):
                    self._worker.signals.error.connect(main_window._handle_file_op_error)
            else:
                logger.error("FileOperations: Neither file_op_manager nor parent (MainWindow) is available for signal connection.")

        self._thread.started.connect(self._worker.run)
        
        # Ensure proper cleanup
        self._worker.signals.finished.connect(self._on_worker_finished) # Custom slot for cleanup
        
        self._thread.start()
        logger.info(f"Started {operation_type} operation in a new thread.")
        return True

    def _on_worker_finished(self):
        logger.debug("Worker has finished. Cleaning up thread and worker.")
        if self._thread is not None:
            self._thread.quit()
            # self._thread.wait() # Wait for thread to finish quitting
        
        # It's generally safer to let Qt's event loop handle deletion with deleteLater
        # rather than deleting them immediately after quit/wait, especially if signals
        # are still pending or if the finished signal itself is emitted from the thread.
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None


    def stop_operation(self):
        if self._worker and self._thread and self._thread.isRunning():
            self._worker.stop() # Signal the worker to stop its loop
            logger.info("Requesting file operation to stop...")
            # Don't quit or wait here directly, let the worker finish its current iteration and emit finished.
        else:
            logger.info("No file operation currently running to stop.")

    # Placeholder for signal connections if FileOperations itself handles them before passing to MainWindow
    # def handle_progress(self, processed, total):
    #     logger.debug(f"FileOp Progress: {processed}/{total}")
    # def handle_finished(self, result):
    #     logger.debug(f"FileOp Finished: {result}")
    # def handle_error(self, err_msg):
    #     logger.error(f"FileOp Error: {err_msg}")
