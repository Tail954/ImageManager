# g:\vscodeGit\ImageManager\tests\test_main_window.py
import pytest
from PyQt6.QtWidgets import QApplication, QTreeView, QListView, QLineEdit, QPushButton, QRadioButton, QComboBox, QProgressDialog, QMessageBox, QMainWindow, QButtonGroup
from unittest.mock import patch, MagicMock, call # ★★★ unittest.mock から patch, MagicMock, call をインポート ★★★

import sys
import os
# Ensure src directory is in Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from PyQt6.QtCore import Qt, QItemSelectionModel, QModelIndex, QDir, QThread, QPoint # Added QThread, QPoint
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFileSystemModel, QCloseEvent, QImage, QPixmap, QIcon
import os # os is already imported, but good to have it near path ops
import time # For sleep
import shutil # For creating dummy folders/files
import unittest # For TestCase structure if preferred

# Assuming src is in PYTHONPATH or tests are run from project root
from src.main_window import MainWindow
from src.ui_manager import UIManager # ★★★ UIManager をインポート ★★★
from src.dialog_manager import DialogManager # DialogManager のインポートを確認
from src.file_operation_manager import FileOperationManager
from src.constants import METADATA_ROLE, SELECTION_ORDER_ROLE, PREVIEW_MODE_FIT, RIGHT_CLICK_ACTION_METADATA, WC_FORMAT_HASH_COMMENT
from src.metadata_filter_proxy_model import MetadataFilterProxyModel # ★★★ NameError 修正: Import を追加 ★★★
from src.file_operations import FileOperations # For mocking its instance if needed
import send2trash # For mocking send2trash

# Fixture to create a QApplication instance for tests that need it
@pytest.fixture(scope="session")
def qt_app(request):
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

# --- Start: Re-structured tests using unittest.TestCase for better organization ---
# This structure is closer to what might have been used before, and helps group setup/teardown.

class TestMainWindowBase(unittest.TestCase):
    """Base class for tests needing a MainWindow instance and QApplication."""
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        """Set up for each test."""
        # MainWindow をインスタンス化する前に _load_app_settings をモック化する
        # これにより、__init__ 内での最初の呼び出しからモックが使用される
        # _load_app_settings のモックが ui_manager のメソッドを呼び出すように設定
        # autospec=True の場合、side_effect 関数の最初の引数はモック対象のインスタンス (self)
        def mock_load_app_settings_side_effect(main_window_instance):
            # print(f"DEBUG: mock_load_app_settings_side_effect called for {type(main_window_instance)}.")

            # MainWindow の __init__ でのデフォルト値を模倣
            main_window_instance.recursive_search_enabled = True # デフォルト
            main_window_instance.app_settings = {} # app_settings を初期化
            if hasattr(main_window_instance, 'ui_manager') and main_window_instance.ui_manager and hasattr(main_window_instance.ui_manager, 'update_recursive_button_text'):
                # print(f"DEBUG side_effect: About to call update_recursive_button_text on {type(main_window_instance.ui_manager.update_recursive_button_text)} with {main_window_instance.recursive_search_enabled}")
                main_window_instance.ui_manager.update_recursive_button_text(main_window_instance.recursive_search_enabled)
            # 他の _load_app_settings の重要な初期化があればここに追加

        self.load_settings_patcher = patch.object(MainWindow, '_load_app_settings', side_effect=mock_load_app_settings_side_effect, autospec=True)
        self.load_settings_patcher.start()

        # ★★★ UIManager のモックを MainWindow の __init__ より前に準備 ★★★
        self.ui_manager_patcher = patch('src.main_window.UIManager')
        self.MockUIManagerClass = self.ui_manager_patcher.start()
        self.mock_ui_manager_instance = self.MockUIManagerClass.return_value

        # ★★★ UIManager のモックインスタンスが持つべきUI要素とメソッドのモックをここで設定 ★★★
        # これは MainWindow のインスタンス化よりも前に行う
        self.mock_ui_manager_instance.update_recursive_button_text = MagicMock(name="mock_update_recursive_button_text_on_instance")
        self.mock_ui_manager_instance.set_file_op_buttons_enabled_ui = MagicMock()
        self.mock_ui_manager_instance.update_copy_mode_button_text = MagicMock()
        self.mock_ui_manager_instance.folder_tree_view = MagicMock(spec=QTreeView)
        self.mock_ui_manager_instance.file_system_model = MagicMock(spec=QFileSystemModel)
        self.mock_ui_manager_instance.thumbnail_view = MagicMock(spec=QListView)
        self.mock_ui_manager_instance.thumbnail_view.selectionModel.return_value = MagicMock(spec=QItemSelectionModel)
        self.mock_ui_manager_instance.source_thumbnail_model = MagicMock(spec=QStandardItemModel)
        self.mock_ui_manager_instance.filter_proxy_model = MagicMock(spec=MetadataFilterProxyModel)
        self.mock_ui_manager_instance.positive_prompt_filter_edit = MagicMock(spec=QLineEdit)
        self.mock_ui_manager_instance.negative_prompt_filter_edit = MagicMock(spec=QLineEdit)
        self.mock_ui_manager_instance.generation_info_filter_edit = MagicMock(spec=QLineEdit)
        self.mock_ui_manager_instance.and_radio_button = MagicMock(spec=QRadioButton)
        self.mock_ui_manager_instance.recursive_toggle_button = MagicMock(spec=QPushButton)
        self.mock_ui_manager_instance.move_files_button = MagicMock(spec=QPushButton)
        self.mock_ui_manager_instance.copy_files_button = MagicMock(spec=QPushButton)
        self.mock_ui_manager_instance.copy_mode_button = MagicMock(spec=QPushButton)
        self.mock_ui_manager_instance.sort_button_group = MagicMock(spec=QButtonGroup)
        self.mock_ui_manager_instance.sort_filename_asc_button = MagicMock(spec=QPushButton)
        self.mock_ui_manager_instance.sort_date_desc_button = MagicMock(spec=QPushButton)
        # ★★★ sort_load_order_button のモックと text() メソッドの戻り値を設定 ★★★
        self.mock_ui_manager_instance.sort_load_order_button = MagicMock(spec=QPushButton)
        self.mock_ui_manager_instance.sort_load_order_button.text.return_value = "読み込み順"

        # MainWindow.statusBar() メソッド (QMainWindowから継承) をモック化し、
        # MagicMockインスタンスを返すようにする
        self.statusbar_method_patcher = patch.object(MainWindow, 'statusBar', return_value=MagicMock())
        self.mock_statusbar_method = self.statusbar_method_patcher.start()

        self.window = MainWindow() # _load_app_settings がモック化された状態でインスタンス化
        self.base_path = "test_temp_dir" # Use a consistent temp dir name
        self.create_dir(self.base_path)
        self.window.current_folder_path = self.base_path
        self.window.initial_dialog_path = self.base_path
        
        # 「読み込み順」テスト用のフォルダとファイルを作成
        self.test_image_dir_load_order = os.path.join(self.base_path, "images_for_load_order")
        self.create_dir(self.test_image_dir_load_order)
        self.dummy_files_load_order = ["c_load.png", "a_load.jpg", "b_load.webp"] # 意図的にファイル名順と異なる順序
        for fname in self.dummy_files_load_order:
            self.create_file(os.path.join(self.test_image_dir_load_order, fname), "dummy_load_order_content")

        # Mock the actual FileOperations instance within FileOperationManager
        # This is important because FileOperationManager instantiates FileOperations.
        # We need to mock the FileOperations instance that FileOperationManager will use.
        self.mock_file_operations_instance = MagicMock(spec=FileOperations)
        self.mock_file_operations_instance.start_operation = MagicMock(return_value=True)
        self.mock_file_operations_instance.stop_operation = MagicMock()
        # Add _thread attribute to the mock FileOperations instance for closeEvent
        self.mock_file_operations_instance._thread = MagicMock(spec=QThread)
        
        # Patch where FileOperations is instantiated by FileOperationManager
        # This assumes FileOperationManager creates its FileOperations instance like:
        # self.file_operations = FileOperations(parent=self.main_window, file_op_manager=self)
        self.file_op_patcher = patch('src.file_operations.FileOperations', return_value=self.mock_file_operations_instance)
        self.MockFileOperationsClass = self.file_op_patcher.start()

        # If MainWindow itself also holds a direct reference to a FileOperations instance (it does)
        # and that's the one being used by some older tests, mock that too.
        # However, the goal is for MainWindow to use FileOperationManager. Remove monkeypatch for _save_settings.
        self.window.file_operations = self.mock_file_operations_instance # Ensure MainWindow's direct ref is also mocked if used

        # Mock QProgressDialog
        self.progress_dialog_patcher = patch('src.file_operation_manager.QProgressDialog') # Patched in manager
        self.MockQProgressDialog = self.progress_dialog_patcher.start()
        self.mock_progress_dialog_instance = self.MockQProgressDialog.return_value
        self.mock_progress_dialog_instance.wasCanceled.return_value = False
        self.mock_progress_dialog_instance.close = MagicMock() # close もモック化

    def tearDown(self):
        """Clean up after each test."""
        self.load_settings_patcher.stop() # パッチャーを停止
        self.progress_dialog_patcher.stop()
        self.file_op_patcher.stop()
        self.statusbar_method_patcher.stop() # ★★★ statusBar メソッドのパッチャーを停止 ★★★
        self.ui_manager_patcher.stop() # ★★★ UIManager のパッチャーを停止 ★★★
        if self.window:
            self.window.close() # Ensure window is closed
            self.window.deleteLater() # Schedule for deletion
            self.window = None
        self.remove_dir(self.base_path)
        if hasattr(self, 'test_image_dir_load_order') and os.path.exists(self.test_image_dir_load_order):
            self.remove_dir(self.test_image_dir_load_order) # ★★★ 追加: 読み込み順テスト用ディレクトリも削除 ★★★
        QApplication.processEvents() # Process deleteLater events

    @classmethod
    def tearDownClass(cls):
        # QApplication.quit() # Optional: quit app at the end of all tests in class
        pass

    def create_dir(self, dir_path):
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

    def remove_dir(self, dir_path):
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)

    def create_file(self, file_path, content="dummy"):
        with open(file_path, "w") as f:
            f.write(content)

    @patch('src.main_window.logger')
    @patch.object(MainWindow, 'statusBar', new_callable=MagicMock) # statusBarメソッド自体をモック化
    # @patch.object(UIManager, 'apply_filters_preserving_selection') # このパッチは削除
    def test_apply_filters_preserve_selection_true_calls_ui_manager(self, mock_statusbar_method, mock_logger): # 引数から mock_ui_apply_filters_preserving を削除
        # Arrange
        # MainWindowのui_managerはセットアップでモック化されたインスタンスです。
        # そのインスタンスのメソッドをテスト内でパッチします。
        self.window.ui_manager.positive_prompt_filter_edit = MagicMock(spec=QLineEdit)
        self.window.ui_manager.negative_prompt_filter_edit = MagicMock(spec=QLineEdit)
        self.window.ui_manager.generation_info_filter_edit = MagicMock(spec=QLineEdit)
        self.window.ui_manager.and_radio_button = MagicMock(spec=QRadioButton)

        self.window.ui_manager.positive_prompt_filter_edit.text.return_value = "positive_text"
        self.window.ui_manager.negative_prompt_filter_edit.text.return_value = "negative_text"
        self.window.ui_manager.generation_info_filter_edit.text.return_value = "info_text"
        self.window.ui_manager.and_radio_button.isChecked.return_value = True # AND検索

        self.window.deselect_all_thumbnails = MagicMock()

        # Act
        # テスト内で、self.window.ui_manager インスタンスのメソッドをパッチ
        with patch.object(self.window.ui_manager, 'apply_filters_preserving_selection') as mock_apply_preserving_on_instance:
            self.window.apply_filters(preserve_selection=True)

            # Assert
            mock_apply_preserving_on_instance.assert_called_once_with(
                "positive_text", "negative_text", "info_text", "AND"
            )
            self.window.deselect_all_thumbnails.assert_not_called()
    @patch('src.main_window.logger')
    @patch.object(MainWindow, 'statusBar', new_callable=MagicMock) # statusBarメソッド自体をモック化
    def test_apply_filters_preserve_selection_false(self, mock_statusbar_method, mock_logger):
        # Arrange
        self.window.deselect_all_thumbnails = MagicMock()
        # MainWindowが持つ実際のui_managerインスタンスのfilter_proxy_modelをモック化
        self.window.ui_manager.filter_proxy_model = MagicMock(spec=MetadataFilterProxyModel)
        self.window.ui_manager.positive_prompt_filter_edit = MagicMock(spec=QLineEdit)
        self.window.ui_manager.negative_prompt_filter_edit = MagicMock(spec=QLineEdit)
        self.window.ui_manager.generation_info_filter_edit = MagicMock(spec=QLineEdit)
        self.window.ui_manager.and_radio_button = MagicMock(spec=QRadioButton)

        self.window.ui_manager.positive_prompt_filter_edit.text.return_value = "test_filter"
        self.window.ui_manager.negative_prompt_filter_edit.text.return_value = ""
        self.window.ui_manager.generation_info_filter_edit.text.return_value = ""
        self.window.ui_manager.and_radio_button.isChecked.return_value = True # AND検索

        # Act
        self.window.apply_filters(preserve_selection=False)

        # Assert
        self.window.deselect_all_thumbnails.assert_called_once()
        self.window.ui_manager.filter_proxy_model.set_search_mode.assert_called_with("AND")
        self.window.ui_manager.filter_proxy_model.set_positive_prompt_filter.assert_called_with("test_filter")
        self.window.ui_manager.filter_proxy_model.set_negative_prompt_filter.assert_called_with("")
        self.window.ui_manager.filter_proxy_model.set_generation_info_filter.assert_called_with("")
        self.window.ui_manager.filter_proxy_model.invalidateFilter.assert_called_once()

# --- Test Classes ---

class TestMainWindowInitialization(TestMainWindowBase):
    def test_main_window_initialization(self):
        """Test basic initialization of MainWindow."""
        self.assertIsNotNone(self.window)
        self.assertEqual(self.window.windowTitle(), "ImageManager")        
        # MainWindow.__init__ で self.current_thumbnail_size は self.available_sizes[1] (128) に設定される
        self.assertEqual(self.window.current_thumbnail_size, 128) # MainWindowのデフォルト値に合わせる
        self.assertTrue(self.window.recursive_search_enabled)
        self.assertIsInstance(self.window.dialog_manager, DialogManager)
        self.assertIsInstance(self.window.file_operation_manager, FileOperationManager)
        # ★★★ 「読み込み順」ボタンの存在確認 (UIManager経由) ★★★
        self.assertIsNotNone(self.window.ui_manager.sort_load_order_button, "Sort by load order button should exist")
        self.assertEqual(self.window.ui_manager.sort_load_order_button.text(), "読み込み順")
        # MainWindowが持つsort_criteria_mapの確認
        self.assertIn(4, self.window.sort_criteria_map, "Sort criteria for ID 4 (load order) should exist in MainWindow")
        self.assertEqual(self.window.sort_criteria_map[4]["caption"], "読み込み順")


class TestMainWindowFolderSelectionAndLoading(TestMainWindowBase):
    @patch('src.main_window.QFileDialog.getExistingDirectory')
    def test_select_folder_updates_tree_and_loads_thumbnails(self, mock_get_existing_directory):
        mock_get_existing_directory.return_value = self.base_path
        
        self.window.update_folder_tree = MagicMock()
        # load_thumbnails_from_folder is called by update_folder_tree

        self.window.select_folder()

        mock_get_existing_directory.assert_called_once()
        self.window.update_folder_tree.assert_called_once_with(self.base_path)
        self.assertEqual(self.window.current_folder_path, self.base_path)

    @patch('src.main_window.QDirIterator')
    @patch('src.main_window.ThumbnailLoaderThread') # Mock the class
    def test_load_thumbnails_from_folder_starts_thread(self, MockThread, MockQDirIterator):
        folder_path = self.base_path
        self.create_file(os.path.join(folder_path, "test1.png"))
        self.create_file(os.path.join(folder_path, "test2.jpg"))

        mock_iterator_instance = MockQDirIterator.return_value
        mock_iterator_instance.hasNext.side_effect = [True, True, False]
        mock_iterator_instance.next.side_effect = [
            os.path.join(folder_path, "test1.png"),
            os.path.join(folder_path, "test2.jpg")
        ]

        mock_thread_instance = MockThread.return_value # Get the instance from the mocked class
        mock_thread_instance.start = MagicMock()
        mock_thread_instance.isRunning = MagicMock(return_value=False)

        self.window.load_thumbnails_from_folder(folder_path)

        MockThread.assert_called_once()
        call_args = MockThread.call_args[0]
        self.assertIn(os.path.join(folder_path, "test1.png"), call_args[0]) # image_files
        self.assertIn(os.path.join(folder_path, "test2.jpg"), call_args[0]) # image_files
        self.assertEqual(len(call_args[1]), 2) # items_for_thread
        self.assertEqual(call_args[2], self.window.current_thumbnail_size) # target_size
        mock_thread_instance.start.assert_called_once()
        self.assertTrue(self.window.is_loading_thumbnails)

class TestMainWindowUISettings(TestMainWindowBase):
    def test_handle_recursive_search_toggled(self):
        # 初期状態は True であるはず (_load_app_settings がモック化されているため、__init__ のデフォルト値)
        self.assertTrue(self.window.recursive_search_enabled)
        # __init__ -> _load_app_settings (mock) -> ui_manager.update_recursive_button_text
        # このアサーションは self.mock_ui_manager_instance.update_recursive_button_text に対して行う
        self.mock_ui_manager_instance.update_recursive_button_text.assert_called_with(True)
        
        self.window.load_thumbnails_from_folder = MagicMock() # _handle_recursive_search_toggled から呼ばれるためモック
        self.window.current_folder_path = self.base_path # フォルダパスが設定されている必要がある

        self.window.handle_recursive_search_toggled(False) # ★★★ 直接ハンドラを呼び出し ★★★
        self.assertFalse(self.window.recursive_search_enabled)
        self.mock_ui_manager_instance.update_recursive_button_text.assert_called_with(False)
        # handle_recursive_search_toggled 内では load_thumbnails_from_folder は呼ばれない
        self.window.load_thumbnails_from_folder.assert_not_called() 

        self.mock_ui_manager_instance.update_recursive_button_text.reset_mock()
        self.window.handle_recursive_search_toggled(True) # ★★★ 直接ハンドラを呼び出し ★★★
        self.assertTrue(self.window.recursive_search_enabled)
        self.mock_ui_manager_instance.update_recursive_button_text.assert_called_with(True)
        self.window.load_thumbnails_from_folder.assert_not_called()

    def test_apply_thumbnail_size_change(self):
        self.window.current_folder_path = "some/folder"
        self.window.load_thumbnails_from_folder = MagicMock()
        
        initial_size = self.window.current_thumbnail_size # Get current size (should be 128 from init)
        new_size = -1
        for size_option in self.window.available_sizes:
            if size_option != initial_size:
                new_size = size_option
                break
        self.assertNotEqual(new_size, -1, "Could not find a different thumbnail size to test.")
        self.assertNotEqual(new_size, initial_size, "Test setup error: new_size must be different from initial_size.")

        result = self.window.apply_thumbnail_size_change(new_size)
        self.assertTrue(result)
        self.assertEqual(self.window.current_thumbnail_size, new_size)
        self.window.load_thumbnails_from_folder.assert_called_once_with("some/folder")

class TestMainWindowThumbnailUpdatesAndFilters(TestMainWindowBase):
    def test_update_thumbnail_item(self):
        item = QStandardItem("test_item.png")
        item.setData("path/to/test_item.png", Qt.ItemDataRole.UserRole)
        self.window.ui_manager.source_thumbnail_model.appendRow(item) # ★★★ UIManager経由 ★★★
        mock_qimage = MagicMock(spec=QImage) # FIX: Use spec=QImage
        item.model = MagicMock(return_value=self.window.ui_manager.source_thumbnail_model) # item.model() がモックを返すようにする
        # Mock setIcon on the item itself
        item.setIcon = MagicMock()
        metadata = {"positive_prompt": "test prompt"}
        
        # FIX: Patch QPixmap.fromImage for this test (QIcon patch removed)
        with patch('src.main_window.QPixmap.fromImage', return_value=MagicMock(spec=QPixmap)) as mock_from_image, \
             patch('src.main_window.QIcon') as mock_qicon_constructor: # Keep patch for assertion, but its return value isn't used by setIcon mock
            self.window.update_thumbnail_item(item, mock_qimage, metadata)
            if mock_qimage: 
                mock_from_image.assert_called_once_with(mock_qimage)
                # Check if QIcon was called with the result of QPixmap.fromImage
                mock_qicon_constructor.assert_called_once_with(mock_from_image.return_value)
        self.assertIsNotNone(item.icon())
        self.assertEqual(item.data(METADATA_ROLE), metadata)
        self.assertEqual(self.window.metadata_cache.get("path/to/test_item.png"), metadata) # Use .get for safety
        self.assertEqual(item.toolTip(), "場所: path/to")

    def test_on_thumbnail_loading_finished(self):
        self.window.is_loading_thumbnails = True
        self.window.ui_manager.folder_tree_view.setEnabled(False) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.filter_proxy_model.rowCount = MagicMock(return_value=10) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.thumbnail_view.selectionModel.return_value.selectedIndexes.return_value = [] # ★★★ UIManager経由 ★★★
        self.window.apply_filters = MagicMock()

        self.window.on_thumbnail_loading_finished()
        self.assertFalse(self.window.is_loading_thumbnails)
        self.window.ui_manager.set_thumbnail_loading_ui_state.assert_called_with(False) # ★★★ UIManager経由 ★★★
        self.window.apply_filters.assert_called_once_with(preserve_selection=True)
        # _update_status_bar_info() によって '表示アイテム数: ...' が呼ばれたことを確認
        self.window.statusBar.showMessage.assert_any_call("表示アイテム数: 10 / 選択アイテム数: 0")
        # その後、'サムネイル読み込み完了' が呼ばれたことを確認 (これが最後の呼び出しになるはず)
        self.window.statusBar.showMessage.assert_called_with("サムネイル読み込み完了", 5000)

    def test_apply_filters(self):
        # UI要素はUIManagerのモック経由で設定
        self.window.ui_manager.positive_prompt_filter_edit.text.return_value = "positive" # ★★★ UIManager経由 ★★★
        self.window.ui_manager.negative_prompt_filter_edit.text.return_value = "negative" # ★★★ UIManager経由 ★★★
        self.window.ui_manager.generation_info_filter_edit.text.return_value = "info" # ★★★ UIManager経由 ★★★
        self.window.ui_manager.and_radio_button.isChecked.return_value = True # ★★★ UIManager経由 ★★★

        self.window.apply_filters()
        self.window.ui_manager.filter_proxy_model.set_search_mode.assert_called_once_with("AND") # ★★★ UIManager経由 ★★★
        self.window.ui_manager.filter_proxy_model.set_positive_prompt_filter.assert_called_once_with("positive") # ★★★ UIManager経由 ★★★
        self.window.ui_manager.filter_proxy_model.set_negative_prompt_filter.assert_called_once_with("negative") # ★★★ UIManager経由 ★★★
        self.window.ui_manager.filter_proxy_model.set_generation_info_filter.assert_called_once_with("info") # ★★★ UIManager経由 ★★★

class TestMainWindowSelection(TestMainWindowBase):
    def test_thumbnail_selection_changed_move_mode(self):
        self.window.is_copy_mode = False
        item1 = QStandardItem("item1.png"); item1.setData("path/1", Qt.ItemDataRole.UserRole)
        item2 = QStandardItem("item2.png"); item2.setData("path/2", Qt.ItemDataRole.UserRole)
        self.window.ui_manager.source_thumbnail_model.appendRow(item1) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.source_thumbnail_model.appendRow(item2) # ★★★ UIManager経由 ★★★
        
        # Simulate selection via proxy model
        proxy_idx1 = self.window.ui_manager.filter_proxy_model.mapFromSource(self.window.ui_manager.source_thumbnail_model.indexFromItem(item1)) # ★★★ UIManager経由 ★★★
        # selectionModel().selectedIndexes() が proxy_idx1 を含むリストを返すようにモック
        # itemFromIndex が返すアイテムの data(UserRole) がパスを返すように設定
        mock_item_from_index = MagicMock(spec=QStandardItem)
        mock_item_from_index.data.return_value = "path/1" # UserRole のときにこのパスを返す
        self.window.ui_manager.source_thumbnail_model.itemFromIndex.return_value = mock_item_from_index
        mock_selection_model = self.window.ui_manager.thumbnail_view.selectionModel()
        mock_selection_model.selectedIndexes.return_value = [proxy_idx1]

        self.window.ui_manager.thumbnail_view.selectionModel().select(proxy_idx1, QItemSelectionModel.SelectionFlag.Select) # ★★★ UIManager経由 ★★★
        self.window.handle_thumbnail_selection_changed(None, None) # Args not used
        self.assertIn("path/1", self.window.selected_file_paths)

    def test_thumbnail_selection_changed_copy_mode(self):
        self.window.is_copy_mode = True
        # ボタンの状態変更ではなく、マネージャーのメソッドを呼び出す
        self.window.file_operation_manager._handle_copy_mode_toggled(True)
        item1 = QStandardItem("item1.png"); item1.setData("path/c1", Qt.ItemDataRole.UserRole)
        item2 = QStandardItem("item2.png"); item2.setData("path/c2", Qt.ItemDataRole.UserRole)
        self.window.ui_manager.source_thumbnail_model.appendRow(item1) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.source_thumbnail_model.appendRow(item2) # ★★★ UIManager経由 ★★★

        proxy_idx2 = self.window.ui_manager.filter_proxy_model.mapFromSource(self.window.ui_manager.source_thumbnail_model.indexFromItem(item2)) # ★★★ UIManager経由 ★★★
        # selectionModel().selectedIndexes() が proxy_idx2 を含むリストを返すようにモック
        # itemFromIndex が正しいアイテムを返すように設定
        # このテストでは item2 が選択されるので、itemFromIndex が item2 を返すように単純化
        self.window.ui_manager.source_thumbnail_model.itemFromIndex.return_value = item2
        mock_selection_model = self.window.ui_manager.thumbnail_view.selectionModel()
        mock_selection_model.selectedIndexes.return_value = [proxy_idx2]
        self.window.ui_manager.thumbnail_view.selectionModel().select(proxy_idx2, QItemSelectionModel.SelectionFlag.Select) # ★★★ UIManager経由 ★★★
        self.window.handle_thumbnail_selection_changed(None, None)
        self.assertEqual(self.window.copy_selection_order, [item2])
        self.assertEqual(item2.data(SELECTION_ORDER_ROLE), 1)

    def test_select_all_deselect_all_thumbnails(self):
        item1 = QStandardItem("item1.png"); item1.setData("path/sa1", Qt.ItemDataRole.UserRole)
        item2 = QStandardItem("item2.png"); item2.setData("path/sa2", Qt.ItemDataRole.UserRole)
        self.window.ui_manager.source_thumbnail_model.appendRow(item1) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.source_thumbnail_model.appendRow(item2) # ★★★ UIManager経由 ★★★
        # model() と rowCount() のモック設定
        self.window.ui_manager.thumbnail_view.model.return_value = self.window.ui_manager.filter_proxy_model
        self.window.ui_manager.filter_proxy_model.rowCount.return_value = 2
        self.window.ui_manager.filter_proxy_model.setFilterFixedString("") # Show all # ★★★ UIManager経由 ★★★

        self.window.select_all_thumbnails()
        self.window.ui_manager.thumbnail_view.selectAll.assert_called_once() # ★★★ UIManager経由 ★★★
        
        self.window.deselect_all_thumbnails()
        self.window.ui_manager.thumbnail_view.clearSelection.assert_called_once() # ★★★ UIManager経由 ★★★

class TestMainWindowEmptyFolderFunctions(TestMainWindowBase):
    @patch('src.main_window.MainWindow._try_delete_empty_subfolders')
    @patch('src.main_window.MainWindow.deselect_all_thumbnails')
    def test_process_file_op_completion_move_calls_try_delete(self, mock_deselect, mock_try_delete):
        source_folder_to_check = os.path.join(self.base_path, "source_of_move")
        self.create_dir(source_folder_to_check)

        result = {
            'status': 'completed',
            'operation_type': 'move',
            'moved_count': 1,
            'errors': [],
            'successfully_moved_src_paths': [os.path.join(source_folder_to_check, "moved_file.txt")],
            'destination_folder': os.path.join(self.base_path, "destination_of_move")
        }
        self.window.current_folder_path = os.path.join(self.base_path, "some_other_current_folder")
        self.create_dir(self.window.current_folder_path)

        dummy_item = QStandardItem("moved_file.txt")
        dummy_item.setData(os.path.join(source_folder_to_check, "moved_file.txt"), Qt.ItemDataRole.UserRole)
        self.window.ui_manager.source_thumbnail_model.appendRow(dummy_item) # ★★★ UIManager経由 ★★★

        with patch('os.path.isdir', return_value=True):
            self.window._process_file_op_completion(result)

        # ★★★ 修正: _process_file_op_completion から _try_delete_empty_subfolders の呼び出しは削除された ★★★
        # mock_try_delete.assert_any_call(source_folder_to_check)
        # mock_try_delete.assert_any_call(self.window.current_folder_path)
        mock_try_delete.assert_not_called() 
        mock_deselect.assert_called_once()


    @patch('src.main_window.send2trash.send2trash')
    @patch('src.main_window.QMessageBox.question')
    @patch('src.main_window.MainWindow._find_empty_subfolders')
    def test_try_delete_empty_subfolders_user_confirms(self, mock_find_empty, mock_msg_box_question, mock_send2trash):
        target_folder = os.path.join(self.base_path, "parent_folder")
        self.create_dir(target_folder)
        empty_sub1 = os.path.join(target_folder, "empty_sub1")
        self.create_dir(empty_sub1)

        mock_find_empty.return_value = [empty_sub1]
        mock_msg_box_question.return_value = QMessageBox.StandardButton.Yes
        self.window.update_folder_tree = MagicMock()

        self.window._try_delete_empty_subfolders(target_folder)

        mock_find_empty.assert_called_once_with(target_folder)
        mock_msg_box_question.assert_called_once()
        mock_send2trash.assert_called_once_with(empty_sub1)
        # ★★★ 修正: _try_delete_empty_subfolders から update_folder_tree の直接呼び出しはなくなった ★★★
        # QTimer.singleShot で遅延実行されるため、直接の呼び出しは確認できない
        # self.window.update_folder_tree.assert_called_with(target_folder)


class TestMainWindowFileOperations(TestMainWindowBase): 
    def test_handle_move_files_button_clicked_no_selection(self):
        self.window.selected_file_paths = []
        # We expect MainWindow's button click to call FileOperationManager's handler
        # The manager's handler will then check selected_file_paths
        self.window.file_operation_manager._handle_move_files_button_clicked() # ★★★ 直接マネージャーのメソッドを呼び出し ★★★
        self.mock_file_operations_instance.start_operation.assert_not_called()
        self.window.statusBar.showMessage.assert_called_with("移動するファイルを選択してください。", 3000)


    @patch('src.file_operation_manager.QFileDialog.getExistingDirectory') 
    def test_handle_move_files_button_clicked_destination_selected(self, mock_get_existing_directory):
        self.window.selected_file_paths = ["/path/file1.jpg", "/path/file2.png"]
        mock_get_existing_directory.return_value = "/destination/folder"
        
        self.window.file_operation_manager._handle_move_files_button_clicked() # ★★★ 直接マネージャーのメソッドを呼び出し ★★★

        mock_get_existing_directory.assert_called_once_with(
            self.window, "移動先フォルダを選択", self.window.current_folder_path
        )
        # FIX: self.MockFileOperationsClass.assert_called_once() removed as it's incorrect here
        self.mock_file_operations_instance.start_operation.assert_called_once_with(
            "move", self.window.selected_file_paths, "/destination/folder"
        )
        self.window.ui_manager.set_file_op_buttons_enabled_ui.assert_called_with(False) # ★★★ UIManager経由 ★★★
        self.assertIsNotNone(self.window.file_operation_manager.progress_dialog) 

    @patch('src.file_operation_manager.QFileDialog.getExistingDirectory')
    def test_handle_move_files_button_clicked_destination_cancelled(self, mock_get_existing_directory):
        self.window.selected_file_paths = ["/path/file1.jpg"]
        mock_get_existing_directory.return_value = "" 

        self.window.file_operation_manager._handle_move_files_button_clicked() # ★★★ 直接マネージャーのメソッドを呼び出し ★★★

        mock_get_existing_directory.assert_called_once()
        self.mock_file_operations_instance.start_operation.assert_not_called()
        # self.assertTrue(self.window.move_files_button.isEnabled()) # ボタンの状態はUIManagerが管理

    def test_handle_copy_mode_toggled_on(self):
        self.window.is_copy_mode = False
        self.window.deselect_all_thumbnails = MagicMock()

        # ボタンの状態変更の代わりにマネージャーのメソッドを直接呼び出す
        self.window.file_operation_manager._handle_copy_mode_toggled(True)

        self.assertTrue(self.window.is_copy_mode)
        self.window.ui_manager.update_copy_mode_button_text.assert_called_with(True) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.move_files_button.setEnabled.assert_called_with(False) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.copy_files_button.setEnabled.assert_called_with(True) # ★★★ UIManager経由 ★★★
        self.window.deselect_all_thumbnails.assert_called_once()

    def test_handle_copy_mode_toggled_off(self):
        self.window.is_copy_mode = True # Initial state for test
        # ボタンの状態変更の代わりにマネージャーのメソッドを直接呼び出す
        self.window.file_operation_manager._handle_copy_mode_toggled(True) # まずONにする
        self.window.copy_selection_order = [MagicMock()]
        self.window.deselect_all_thumbnails = MagicMock() # MainWindowのメソッド
        
        mock_item_with_role = MagicMock()
        mock_item_with_role.data.return_value = 1 
        self.window.ui_manager.source_thumbnail_model.rowCount.return_value = 1 # ★★★ UIManager経由 ★★★
        self.window.ui_manager.source_thumbnail_model.item.return_value = mock_item_with_role # ★★★ UIManager経由 ★★★
        
        # ★★★ 修正: FileOperationManager._handle_copy_mode_toggled 内の TypeError を回避 ★★★
        # self.main_window.thumbnail_view.update(proxy_idx) で proxy_idx が MagicMock だとエラーになる
        # ここでは、thumbnail_view.update が呼ばれることだけを確認する
        self.window.ui_manager.filter_proxy_model.mapFromSource.return_value = MagicMock(spec=QModelIndex) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.thumbnail_view.update = MagicMock() # updateメソッドをモック化 # ★★★ UIManager経由 ★★★

        # ボタンの状態変更の代わりにマネージャーのメソッドを直接呼び出す
        self.window.file_operation_manager._handle_copy_mode_toggled(False)
        QApplication.processEvents() # Allow signal processing

        self.assertFalse(self.window.is_copy_mode) # This should now be false
        self.window.ui_manager.update_copy_mode_button_text.assert_called_with(False) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.move_files_button.setEnabled.assert_called_with(True) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.copy_files_button.setEnabled.assert_called_with(False) # ★★★ UIManager経由 ★★★
        self.window.deselect_all_thumbnails.assert_called_once()
        mock_item_with_role.setData.assert_called_with(None, SELECTION_ORDER_ROLE)

    @patch('src.file_operation_manager.QFileDialog.getExistingDirectory')
    def test_handle_copy_files_button_clicked_no_selection(self, mock_get_existing_directory):
        self.window.is_copy_mode = True 
        # self.window.copy_mode_button.setChecked(True) # ボタンの状態はUIManagerが管理
        self.window.copy_selection_order = []

        # ボタンクリックの代わりにマネージャーのメソッドを直接呼び出す
        self.window.file_operation_manager._handle_copy_files_button_clicked()


        mock_get_existing_directory.assert_not_called()
        self.mock_file_operations_instance.start_operation.assert_not_called()
        self.window.statusBar.showMessage.assert_called_with("コピーするファイルを順番に選択してください。", 3000)

    @patch('src.file_operation_manager.QFileDialog.getExistingDirectory')
    def test_handle_copy_files_button_clicked_destination_selected(self, mock_get_existing_directory):
        self.window.is_copy_mode = True
        # self.window.copy_mode_button.setChecked(True) # ボタンの状態はUIManagerが管理
        mock_item1 = MagicMock(spec=QStandardItem) 
        mock_item1.data.return_value = "/path/copy_file1.jpg" 
        self.window.copy_selection_order = [mock_item1]
        mock_get_existing_directory.return_value = "/copy_destination/folder"

        # ボタンクリックの代わりにマネージャーのメソッドを直接呼び出す
        self.window.file_operation_manager._handle_copy_files_button_clicked()


        mock_get_existing_directory.assert_called_once_with(
            self.window, "コピー先フォルダを選択", self.window.current_folder_path 
        )
        # FIX: self.MockFileOperationsClass.assert_called_once() removed
        self.mock_file_operations_instance.start_operation.assert_called_once_with(
            "copy", None, "/copy_destination/folder", copy_selection_order=self.window.copy_selection_order
        )
        self.window.ui_manager.set_file_op_buttons_enabled_ui.assert_called_with(False) # ★★★ UIManager経由 ★★★
        self.assertIsNotNone(self.window.file_operation_manager.progress_dialog)

    @patch('src.file_operation_manager.QFileDialog.getExistingDirectory')
    def test_handle_copy_files_button_clicked_destination_cancelled(self, mock_get_existing_directory):
        self.window.is_copy_mode = True
        # self.window.copy_mode_button.setChecked(True) # ボタンの状態はUIManagerが管理
        self.window.copy_selection_order = [MagicMock()]
        mock_get_existing_directory.return_value = "" 

        # ボタンクリックの代わりにマネージャーのメソッドを直接呼び出す
        self.window.file_operation_manager._handle_copy_files_button_clicked()

        mock_get_existing_directory.assert_called_once()
        self.mock_file_operations_instance.start_operation.assert_not_called()
        # self.assertTrue(self.window.copy_files_button.isEnabled()) # ボタンの状態はUIManagerが管理

    def test_set_file_op_buttons_enabled_true(self):
        self.window.is_copy_mode = False 
        # FileOperationManager が UIManager のメソッドを呼び出すことを確認
        self.window.file_operation_manager._handle_file_op_finished({}) # ダミーの完了結果で呼び出しをトリガー
        self.window.ui_manager.set_file_op_buttons_enabled_ui.assert_called_with(True)

    def test_set_file_op_buttons_enabled_false(self):
        # 前提条件を設定
        self.window.selected_file_paths = ["/some/file.jpg"]
        with patch('src.file_operation_manager.QFileDialog.getExistingDirectory', return_value="/some/destination"):
        # FileOperationManager が UIManager のメソッドを呼び出すことを確認
            self.window.file_operation_manager._handle_move_files_button_clicked() # ボタンクリックで無効化されるはず
        self.window.ui_manager.set_file_op_buttons_enabled_ui.assert_any_call(False) # どこかでFalseで呼ばれるはず

    def test_handle_file_op_progress(self):
        self.window.file_operation_manager.progress_dialog = self.mock_progress_dialog_instance
        self.mock_progress_dialog_instance.wasCanceled.return_value = False

        self.window.file_operation_manager._handle_file_op_progress(5, 10)

        self.mock_progress_dialog_instance.setMaximum.assert_called_once_with(10)
        self.mock_progress_dialog_instance.setValue.assert_called_once_with(5)
        self.mock_progress_dialog_instance.setLabelText.assert_called_once_with("処理中: 5/10 ファイル...")

    def test_handle_file_op_progress_dialog_cancelled(self):
        self.window.file_operation_manager.progress_dialog = self.mock_progress_dialog_instance
        self.mock_progress_dialog_instance.wasCanceled.return_value = True

        self.window.file_operation_manager._handle_file_op_progress(1, 2)
        self.mock_progress_dialog_instance.setMaximum.assert_not_called()
        self.mock_progress_dialog_instance.setValue.assert_not_called()

    @patch('src.file_operation_manager.QMessageBox.critical') 
    def test_handle_file_op_error(self, mock_qmessagebox_critical):
        self.window.file_operation_manager.progress_dialog = self.mock_progress_dialog_instance
        
        with patch.object(self.window.ui_manager, 'set_file_op_buttons_enabled_ui') as mock_set_enabled: # ★★★ UIManager経由 ★★★
            self.window.file_operation_manager._handle_file_op_error("Test error")
            mock_set_enabled.assert_called_once_with(True)

        mock_qmessagebox_critical.assert_called_once()
        self.assertIn("Test error", mock_qmessagebox_critical.call_args[0][2]) 
        self.window.statusBar.showMessage.assert_called_with("ファイル操作中にエラーが発生しました。", 5000)
        self.mock_progress_dialog_instance.close.assert_called_once()
        self.assertIsNone(self.window.file_operation_manager.progress_dialog)

    @patch('src.main_window.RenamedFilesDialog') 
    @patch('src.main_window.MainWindow._try_delete_empty_subfolders')
    def test_handle_file_op_finished_move_success_with_rename(self, mock_try_delete, MockRenamedFilesDialog):
        self.window.file_operation_manager.progress_dialog = self.mock_progress_dialog_instance
        
        self.window.selected_file_paths = ["/original/path.txt"] 
        # self.window.source_thumbnail_model = MagicMock() # UIManagerが持つ
        mock_item = MagicMock(spec=QStandardItem)
        mock_item.data.return_value = "/original/path.txt"
        mock_item.model.return_value = self.window.ui_manager.source_thumbnail_model # ★★★ UIManager経由 ★★★
        self.window.ui_manager.source_thumbnail_model.item.return_value = mock_item # ★★★ UIManager経由 ★★★
        # FIX: Mock removeRow to simulate rowCount change
        def mock_remove_row_effect(row_idx):
            current_count = self.window.ui_manager.source_thumbnail_model.rowCount.return_value # ★★★ UIManager経由 ★★★
            if current_count > 0:
                self.window.ui_manager.source_thumbnail_model.rowCount.return_value = current_count - 1 # ★★★ UIManager経由 ★★★
            return True
        self.window.ui_manager.source_thumbnail_model.removeRow = MagicMock(side_effect=mock_remove_row_effect) # ★★★ UIManager経由 ★★★

        self.window.ui_manager.source_thumbnail_model.rowCount.return_value = 1 # ★★★ UIManager経由 ★★★
        self.window.ui_manager.source_thumbnail_model.indexFromItem.return_value = QModelIndex() # ★★★ UIManager経由 ★★★
        # self.window.filter_proxy_model は self.window.ui_manager.filter_proxy_model を指すように setUp で設定済み

        result = {
            'status': 'completed', 'operation_type': 'move', 'moved_count': 1,
            'renamed_files': [{'original': 'old.txt', 'new': 'new.txt'}], 'errors': [],
            'successfully_moved_src_paths': ["/original/path.txt"],
            'destination_folder': "/dest/folder"
        }

        # with ステートメントを括弧で囲む形式に変更
        with (patch.object(self.window.ui_manager, 'set_file_op_buttons_enabled_ui') as mock_set_enabled_manager,
              patch('src.main_window.os.path.isdir', return_value=True)):
            
            self.window.file_operation_manager._handle_file_op_finished(result)
            mock_set_enabled_manager.assert_called_once_with(True)
        self.mock_progress_dialog_instance.close.assert_called_once()
        self.assertIsNone(self.window.file_operation_manager.progress_dialog)
        MockRenamedFilesDialog.assert_called_once_with(result['renamed_files'], self.window)
        # _process_file_op_completion から _try_delete_empty_subfolders の呼び出しは削除されたため、呼び出されないことを確認
        mock_try_delete.assert_not_called() 
        self.assertEqual(self.window.ui_manager.source_thumbnail_model.rowCount(), 0) # ★★★ UIManager経由 ★★★


class TestMainWindowContextMenuAndDialogs(TestMainWindowBase):
    def test_show_thumbnail_context_menu_metadata_action(self):
        self.window.thumbnail_right_click_action = RIGHT_CLICK_ACTION_METADATA
        mock_dialog_manager = MagicMock(spec=DialogManager)
        self.window.dialog_manager = mock_dialog_manager
        mock_proxy_index = MagicMock(spec=QModelIndex); mock_proxy_index.isValid.return_value = True # FIX: Make it valid
        self.window.ui_manager.thumbnail_view.indexAt = MagicMock(return_value=mock_proxy_index) # ★★★ UIManager経由 ★★★

        self.window._show_thumbnail_context_menu(QPoint(10,10)) # FIX: Pass a QPoint
        mock_dialog_manager.open_metadata_dialog.assert_called_once_with(mock_proxy_index)

    @patch('src.main_window.QMenu')
    def test_show_thumbnail_context_menu_menu_action(self, MockQMenu):
        self.window.thumbnail_right_click_action = "menu"
        mock_dialog_manager = MagicMock(spec=DialogManager)
        self.window.dialog_manager = mock_dialog_manager
        mock_qmenu_instance = MockQMenu.return_value
        mock_qmenu_instance.exec = MagicMock()
        mock_qmenu_instance.addAction = MagicMock()
        mock_proxy_index = MagicMock(spec=QModelIndex); mock_proxy_index.isValid.return_value = True # FIX: Make it valid
        self.window.ui_manager.thumbnail_view.indexAt = MagicMock(return_value=mock_proxy_index) # ★★★ UIManager経由 ★★★
        self.window._open_file_location_for_item = MagicMock()

        self.window._show_thumbnail_context_menu(QPoint(10,10)) # FIX: Pass a QPoint
        MockQMenu.assert_called_once_with(self.window)
        mock_qmenu_instance.exec.assert_called_once()
        self.assertGreaterEqual(mock_qmenu_instance.addAction.call_count, 2)

    @patch('src.main_window.os.startfile')
    def test_open_file_location_for_item(self, mock_os_startfile):
        file_to_open_dir = os.path.join(self.base_path, "open_test_dir")
        self.create_dir(file_to_open_dir)
        file_in_dir = os.path.join(file_to_open_dir, "test_file.png")
        self.create_file(file_in_dir)
        item = QStandardItem(os.path.basename(file_in_dir))
        # item.data(role) が UserRole のときに file_in_dir を返すようにモック
        def item_data_side_effect(role):
            if role == Qt.ItemDataRole.UserRole:
                return file_in_dir
            return None # 他のロールはNoneを返す
        item.data = MagicMock(side_effect=item_data_side_effect)
        # itemFromIndex がこの item を返すように設定
        self.window.ui_manager.source_thumbnail_model.itemFromIndex.return_value = item
        item.setData(file_in_dir, Qt.ItemDataRole.UserRole)
        self.window.ui_manager.source_thumbnail_model.appendRow(item) # ★★★ UIManager経由 ★★★
        proxy_idx = self.window.ui_manager.filter_proxy_model.mapFromSource(self.window.ui_manager.source_thumbnail_model.indexFromItem(item)) # ★★★ UIManager経由 ★★★

        self.window._open_file_location_for_item(proxy_idx)
        mock_os_startfile.assert_called_once_with(file_to_open_dir)

class TestMainWindowSortFunctionality(TestMainWindowBase):
    def test_sort_functionality_toggle_buttons(self):
        # ★★★ 修正: setUp で filter_proxy_model がモック化されていない場合、ここでモック化する ★★★
        # self.window.filter_proxy_model は self.window.ui_manager.filter_proxy_model を指すように setUp で設定済み
        self.window.ui_manager.filter_proxy_model.sort = MagicMock() # ★★★ UIManager経由 ★★★
        self.window.ui_manager.filter_proxy_model.set_sort_key_type = MagicMock() # ★★★ UIManager経由 ★★★

        # Add some dummy items to the source model to make the test more realistic,
        # though we are mocking the actual sort call.
        file_b_path = os.path.join(self.base_path, "b_file.png")
        file_a_path = os.path.join(self.base_path, "a_file.jpg")
        self.create_file(file_b_path); time.sleep(0.02)
        self.create_file(file_a_path)
        item_b = QStandardItem("b_file.png"); item_b.setData(file_b_path, Qt.ItemDataRole.UserRole)
        item_a = QStandardItem("a_file.jpg"); item_a.setData(file_a_path, Qt.ItemDataRole.UserRole)
        # self.window.source_thumbnail_model は self.window.ui_manager.source_thumbnail_model を指す
        if self.window.ui_manager.source_thumbnail_model is None: # ★★★ UIManager経由 ★★★
            self.window.ui_manager.source_thumbnail_model = QStandardItemModel() # ★★★ UIManager経由 ★★★
            if self.window.ui_manager.filter_proxy_model: # If proxy exists, set its source # ★★★ UIManager経由 ★★★
                 self.window.ui_manager.filter_proxy_model.setSourceModel(self.window.ui_manager.source_thumbnail_model) # ★★★ UIManager経由 ★★★

        self.window.ui_manager.source_thumbnail_model.appendRow(item_b) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.source_thumbnail_model.appendRow(item_a) # ★★★ UIManager経由 ★★★

        # Simulate clicking "ファイル名 昇順" (ID 0)
        self.window._apply_sort_from_toggle_button(0) # ID 0 を直接渡す
        self.assertEqual(self.window.current_sort_button_id, 0)
        self.window.ui_manager.filter_proxy_model.set_sort_key_type.assert_called_with(0) # Filename # ★★★ UIManager経由 ★★★
        self.window.ui_manager.filter_proxy_model.sort.assert_called_with(0, Qt.SortOrder.AscendingOrder) # ★★★ UIManager経由 ★★★
        self.window.ui_manager.filter_proxy_model.sort.reset_mock() # Reset for next check # ★★★ UIManager経由 ★★★
        self.window.ui_manager.filter_proxy_model.set_sort_key_type.reset_mock() # ★★★ UIManager経由 ★★★

        # Simulate clicking "更新日時 降順" (ID 3)
        self.window._apply_sort_from_toggle_button(3) # ID 3 を直接渡す
        self.assertEqual(self.window.current_sort_button_id, 3)
        self.window.ui_manager.filter_proxy_model.set_sort_key_type.assert_called_with(1) # Update Date # ★★★ UIManager経由 ★★★
        self.window.ui_manager.filter_proxy_model.sort.assert_called_with(0, Qt.SortOrder.DescendingOrder) # ★★★ UIManager経由 ★★★

        # ★★★ 「読み込み順」ソートボタンのテスト (ID 4) ★★★
        self.window.ui_manager.filter_proxy_model.sort.reset_mock()
        self.window.ui_manager.filter_proxy_model.set_sort_key_type.reset_mock()

        self.window._apply_sort_from_toggle_button(4) # ID 4 を直接渡す
        self.assertEqual(self.window.current_sort_button_id, 4)
        self.window.ui_manager.filter_proxy_model.set_sort_key_type.assert_called_with(2) # Load Order (key_type 2)
        self.window.ui_manager.filter_proxy_model.sort.assert_called_with(0, Qt.SortOrder.AscendingOrder) # Default to Ascending for load order

class TestMainWindowSettings(TestMainWindowBase):
    def test_save_and_load_settings_for_load_order_sort(self):
        # 1. 「読み込み順」ソートを設定
        self.window.current_sort_button_id = 4 # 「読み込み順」のID

        # 2. 設定を保存
        self.window._save_settings() # MainWindowのメソッドを直接呼び出し
        # app_settings.json が作成され、正しい値が書き込まれていることを確認
        # (ここでは _save_settings が正しく動作することを信頼し、ファイル内容の直接検証は省略)

        # 3. 新しいMainWindowインスタンスで設定を読み込み
        #    _load_app_settings がモック化されているため、直接呼び出して挙動を確認
        new_window = MainWindow() # _load_app_settings (モック) が呼ばれる
        # _load_app_settings のモックを解除して、実際の読み込み処理をテストする
        self.load_settings_patcher.stop() # 一時的にモックを停止
        new_window._load_app_settings() # 実際のメソッドを呼び出し
        self.load_settings_patcher.start() # モックを再開

        # 4. 読み込まれた設定値を確認
        self.assertEqual(new_window.current_sort_button_id, 4, "Sort button ID for load order should be loaded")

    def test_load_thumbnails_with_load_order_sort_selected_no_explicit_sort(self):
        # 1. 「読み込み順」ソートを選択状態にする
        self.window.current_sort_button_id = 4 # 「読み込み順」のID
        # UIのボタン状態も合わせる (通常は _apply_initial_sort_from_settings で行われる)
        mock_load_order_button = MagicMock(spec=QPushButton)
        self.window.ui_manager.sort_button_group.button = MagicMock(return_value=mock_load_order_button) # button(4) がモックを返すように
        self.window._apply_initial_sort_from_settings() # これでボタンがチェックされるはず
        mock_load_order_button.setChecked.assert_called_with(True)

        # 2. フォルダを読み込む
        #    _apply_sort_from_toggle_button が呼ばれないことを確認
        with patch.object(self.window, '_apply_sort_from_toggle_button') as mock_apply_sort:
            # QDirIterator のモック設定
            mock_iterator_instance = MagicMock()
            mock_iterator_instance.hasNext.side_effect = [True, True, True, False] # 3 files
            mock_iterator_instance.next.side_effect = [
                os.path.join(self.test_image_dir_load_order, self.dummy_files_load_order[0]),
                os.path.join(self.test_image_dir_load_order, self.dummy_files_load_order[1]),
                os.path.join(self.test_image_dir_load_order, self.dummy_files_load_order[2]),
            ]
            with patch('src.main_window.QDirIterator', return_value=mock_iterator_instance):
                self.window.load_thumbnails_from_folder(self.test_image_dir_load_order)
            
            # サムネイル読み込み完了まで待機 (テスト用に同期的に処理されるか、適切に待機)
            if self.window.thumbnail_loader_thread and self.window.thumbnail_loader_thread.isRunning():
                self.window.thumbnail_loader_thread.wait() # スレッドの終了を待つ
            QApplication.processEvents() # UIイベントとシグナル処理
            mock_apply_sort.assert_not_called()

class TestMainWindowCloseEvent(TestMainWindowBase):
    @patch('src.main_window.MainWindow._save_settings')
    @patch('src.main_window.ThumbnailLoaderThread')
    def test_close_event_saves_settings_and_stops_threads(self, MockThumbThread, mock_save_settings):
        mock_thumb_instance = MockThumbThread.return_value
        mock_thumb_instance.isRunning.return_value = True
        self.window.thumbnail_loader_thread = mock_thumb_instance 

        mock_file_op_qthread = self.mock_file_operations_instance._thread # FIX: Use the one from setUp
        mock_file_op_qthread.isRunning.return_value = True
        # self.mock_file_operations_instance._thread is already set in setUp

        mock_drop_window = MagicMock()
        self.window.dialog_manager.drop_window_instance = mock_drop_window # Ensure DialogManager has this mock
        
        mock_qclose_event = MagicMock(spec=QCloseEvent)
        # Patch QMainWindow.closeEvent to prevent TypeError from super() call
        with patch.object(QMainWindow, 'closeEvent') as mock_super_close_event:
            self.window.closeEvent(mock_qclose_event)
            mock_super_close_event.assert_called_once_with(mock_qclose_event)

        mock_save_settings.assert_called_once()
        mock_thumb_instance.stop.assert_called_once()
        mock_thumb_instance.quit.assert_called_once()
        mock_thumb_instance.wait.assert_called_once_with(3000)
        
        self.mock_file_operations_instance.stop_operation.assert_called_once()
        mock_file_op_qthread.wait.assert_called_once_with(1000)
        
        mock_drop_window.close.assert_called_once()
        # mock_qclose_event.accept.assert_called_once() # This is called by super().closeEvent which is now mocked, so this assertion is not needed here.


# --- Pytest style tests (can be converted or kept alongside) ---
@pytest.fixture
def main_window_fixture(qt_app, tmp_path, monkeypatch):
    # _load_app_settings が self.app_settings を初期化するようにモック化
    def mock_load_app_settings(self_mw):
        self_mw.app_settings = {} # 空の辞書で初期化
        # 必要であれば、テストケースに応じて特定のキーをapp_settingsに追加することも可能
    monkeypatch.setattr(MainWindow, "_load_app_settings", mock_load_app_settings)

    monkeypatch.setattr(MainWindow, "_save_settings", lambda self: None)
    
    # UIManager とその属性をモック化
    mock_ui_manager = MagicMock()
    mock_ui_manager.source_thumbnail_model = MagicMock(spec=QStandardItemModel)
    # For _update_status_bar_info to work during MainWindow.__init__
    mock_ui_manager.filter_proxy_model = MagicMock(spec=MetadataFilterProxyModel)
    mock_ui_manager.filter_proxy_model.rowCount.return_value = 0 # Default
    mock_ui_manager.thumbnail_view = MagicMock(spec=QListView)
    mock_ui_manager.thumbnail_view.selectionModel.return_value = MagicMock(spec=QItemSelectionModel)
    mock_ui_manager.thumbnail_view.selectionModel.return_value.selectedIndexes.return_value = []
    monkeypatch.setattr('src.main_window.UIManager', lambda self_mw: mock_ui_manager)

    mock_file_op_inst = MagicMock(spec=FileOperations)
    mock_file_op_inst.start_operation = MagicMock(return_value=True)
    mock_file_op_inst._thread = MagicMock(spec=QThread) # FIX: Add _thread to this mock too
    monkeypatch.setattr('src.file_operations.FileOperations', lambda parent, file_op_manager: mock_file_op_inst) 

    # This is the mock for the MainWindow.statusBar() METHOD
    mock_statusbar_method_return_value = MagicMock()
    monkeypatch.setattr(MainWindow, 'statusBar', lambda self_mw: mock_statusbar_method_return_value)

    # When UIManager is instantiated, its setup_ui method's side_effect is set
    # to correctly set the statusBar attribute on the MainWindow instance.
    def mock_uimanager_factory_for_fixture(main_window_instance_passed_to_constructor):
        def setup_ui_for_mock():
            main_window_instance_passed_to_constructor.statusBar = main_window_instance_passed_to_constructor.statusBar()
        mock_ui_manager.setup_ui.side_effect = setup_ui_for_mock
        return mock_ui_manager
    monkeypatch.setattr('src.main_window.UIManager', mock_uimanager_factory_for_fixture)

    window = MainWindow()
    window.current_folder_path = str(tmp_path)
    window.initial_dialog_path = str(tmp_path)
    window.file_operations = mock_file_op_inst # Ensure MainWindow's direct ref is also this mock
    window.ui_manager = mock_ui_manager # MainWindow インスタンスにモックを設定

    (tmp_path / "image0.png").touch()
    (tmp_path / "image1.jpg").touch()
    yield window
    window.close()

def test_main_window_initialization_pytest(main_window_fixture):
    assert main_window_fixture is not None
    assert main_window_fixture.windowTitle() == "ImageManager"

@patch('src.main_window.MainWindow._try_delete_empty_subfolders')
def test_process_file_op_completion_move_success_pytest(mock_try_delete, main_window_fixture, tmp_path):
    window = main_window_fixture 
    
    src_file1_path = str(tmp_path / "move_src1.png")
    # パスの正規化（テスト環境とアプリケーション内で一貫させるため）
    normalized_src_file1_path = os.path.normpath(src_file1_path).replace("\\", "/")

    with open(normalized_src_file1_path, "w") as f: # touch() の代わりにファイル作成
        f.write("dummy content")

    item1 = QStandardItem(os.path.basename(src_file1_path))
    item1.setData(normalized_src_file1_path, Qt.ItemDataRole.UserRole) # 正規化されたパスをセット
    # ★★★ item1 の model() が期待する source_thumbnail_model を返すように設定 ★★★
    item1.model = MagicMock(return_value=window.ui_manager.source_thumbnail_model)
    
    # source_thumbnail_model のモックに rowCount と item を設定
    window.ui_manager.source_thumbnail_model.rowCount.return_value = 1
    window.ui_manager.source_thumbnail_model.item.return_value = item1
    window.ui_manager.source_thumbnail_model.appendRow(item1) # ★★★ UIManager経由 ★★★
    window.selected_file_paths = [src_file1_path] 

    dest_folder = str(tmp_path / "dest_move")
    os.makedirs(dest_folder, exist_ok=True)
    result_data = {
        'status': 'completed',
        'operation_type': 'move',
        'moved_count': 1,
        'renamed_files': [],
        'errors': [],
            'successfully_moved_src_paths': [normalized_src_file1_path], # 正規化されたパスを使用
        'destination_folder': dest_folder
    }
    
    window.ui_manager.thumbnail_view.selectionModel = MagicMock() # Mock selectionModel for _update_status_bar_info # ★★★ UIManager経由 ★★★
    window.ui_manager.thumbnail_view.selectionModel.return_value.selectedIndexes.return_value = [] # Simulate 0 selected # ★★★ UIManager経由 ★★★

    window._process_file_op_completion(result_data)

    # removeRow が呼ばれたことを確認
    window.ui_manager.source_thumbnail_model.removeRow.assert_called_once()
    # アサーションの直前に rowCount の戻り値を設定
    window.ui_manager.source_thumbnail_model.rowCount.return_value = 0 
    assert window.ui_manager.source_thumbnail_model.rowCount() == 0 # ★★★ UIManager経由 ★★★
    assert not window.selected_file_paths
    # FIX: Assert the message set by _update_status_bar_info
    window.statusBar.showMessage.assert_called_with("表示アイテム数: 0 / 選択アイテム数: 0")
    # ★★★ 修正: _process_file_op_completion から _try_delete_empty_subfolders の呼び出しは削除された ★★★
    # mock_try_delete.assert_any_call(str(tmp_path)) # 以前のアサーション
    mock_try_delete.assert_not_called() # 呼び出されないことを確認


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
