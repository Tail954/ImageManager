# src/main_window.py
# (DropWindow 連携機能を統合した完全版)

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeView, QSplitter, QFrame, QFileDialog, QSlider, QListView, QDialog,
     QAbstractItemView, QLineEdit, QMenu, QRadioButton, QButtonGroup, QMessageBox, QProgressDialog, QComboBox, QStyledItemDelegate
)
from PyQt6.QtGui import QFileSystemModel, QPixmap, QIcon, QStandardItemModel, QStandardItem, QAction, QCloseEvent
from PyQt6.QtCore import Qt, QDir, QSize, QTimer, QVariant, QSortFilterProxyModel, QDirIterator, QModelIndex, QItemSelection # <--- ★QDirIterator, QModelIndex, QItemSelection をインポート
import os # For path operations
from pathlib import Path # For path operations
import json # For settings / metadata parsing
import time # For load time measurement
import logging # Add logging import

# PillowのImageオブジェクトをQImageに変換するために必要
# PIL.ImageQt が Pillow 9.0.0 以降で推奨される方法
try:
    from PIL import Image, ImageQt
except ImportError:
    logging.error("Pillow (PIL) の ImageQt モジュールが見つかりません。pip install Pillow --upgrade を試してください。")
    ImageQt = None
    Image = None # ImageもNoneにしておく

import send2trash # Import at module level

from .thumbnail_loader import ThumbnailLoaderThread
from .thumbnail_delegate import ThumbnailDelegate
from .metadata_filter_proxy_model import MetadataFilterProxyModel
from .image_metadata_dialog import ImageMetadataDialog
from .thumbnail_list_view import ToggleSelectionListView
from .file_operations import FileOperations # Import FileOperations
from .renamed_files_dialog import RenamedFilesDialog # Import new dialog
from .full_image_dialog import FullImageDialog
from .settings_dialog import SettingsDialog
from .drop_window import DropWindow
from .wc_creator_dialog import WCCreatorDialog
from .metadata_utils import extract_image_metadata # Import shared metadata extraction
from .dialog_manager import DialogManager # Import DialogManager
from .file_operation_manager import FileOperationManager # New import

from .constants import (
    APP_SETTINGS_FILE,
    METADATA_ROLE, SELECTION_ORDER_ROLE, PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM,
    THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU,
    WC_COMMENT_OUTPUT_FORMAT, WC_FORMAT_HASH_COMMENT, WC_FORMAT_BRACKET_COMMENT
)

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    # ----------------------------------------------------------------------
    # --------------------------------------------------------------------

    def __init__(self):
        super().__init__()
        self.thumbnail_loader_thread = None
        self.metadata_cache = {}
        # self.metadata_dialog_instance = None # DialogManagerが管理
        self.drop_window_instance = None # <--- ★追加: DropWindowのインスタンスを保持
        self.dialog_manager = DialogManager(self) # DialogManagerのインスタンス化

        self.setWindowTitle("ImageManager")
        self.setGeometry(100, 100, 1200, 800)

        self.available_sizes = [96, 128, 200]
        self.current_thumbnail_size = self.available_sizes[1] # Default to 128
        self.current_folder_path = None # To store the currently selected folder path
        self.is_loading_thumbnails = False # Flag to indicate loading state
        self.recursive_search_enabled = True # Default to ON
        self.selected_file_paths = [] # List to store paths of selected thumbnails
        self.is_copy_mode = False # Flag for copy mode state, True if copy mode is active
        self.copy_selection_order = [] # Stores QStandardItem references in copy mode selection order        
        self._hidden_moved_file_paths = set() # Set to store paths of files moved out of the current view
        # self.progress_dialog = None # Moved to FileOperationManager
        self.progress_dialog = None # For cancellation dialog
        self.initial_dialog_path = None # For storing path from settings
        self.metadata_dialog_last_geometry = None # DialogManagerがMainWindowのこの属性を参照・更新する
        # self.full_image_dialog_instance = None # DialogManagerが管理する
        self.image_preview_mode = PREVIEW_MODE_FIT # Default, will be overwritten by _load_app_settings
        self.current_sort_key_index = 0 # 0: Filename, 1: Update Date
        self.current_sort_order = Qt.SortOrder.AscendingOrder # Qt.SortOrder.AscendingOrder or Qt.SortOrder.DescendingOrder
        self.load_start_time = None # For load time measurement
        self.thumbnail_right_click_action = RIGHT_CLICK_ACTION_METADATA # Default value
        self.wc_creator_comment_format = WC_FORMAT_HASH_COMMENT

        self.file_operation_manager = FileOperationManager(self) # New instance
        self.file_operations = FileOperations(parent=self, file_op_manager=self.file_operation_manager) # Pass manager

        # Load application-wide settings first
        self._load_app_settings()

        # Menu Bar
        self._create_menu_bar() # <-- ★ここでメニューが作成される

        # Status bar
        self.statusBar = self.statusBar()

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)

        # Splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel (folder tree and button)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.folder_select_button = QPushButton("フォルダを選択...")
        self.folder_select_button.clicked.connect(self.select_folder)
        left_layout.addWidget(self.folder_select_button)

        # Selection buttons layout
        selection_button_layout = QHBoxLayout()
        self.select_all_button = QPushButton("全選択")
        self.select_all_button.clicked.connect(self.select_all_thumbnails)
        selection_button_layout.addWidget(self.select_all_button)

        self.deselect_all_button = QPushButton("全選択解除")
        self.deselect_all_button.clicked.connect(self.deselect_all_thumbnails)
        selection_button_layout.addWidget(self.deselect_all_button)
        # left_layout.addLayout(selection_button_layout) # Removed from here

        self.recursive_toggle_button = QPushButton("サブフォルダ検索: ON")
        self.recursive_toggle_button.setCheckable(True)
        self.recursive_toggle_button.setChecked(self.recursive_search_enabled)
        self.recursive_toggle_button.toggled.connect(self.handle_recursive_search_toggled)
        left_layout.addWidget(self.recursive_toggle_button)

        # --- Sort Options UI ---
        sort_options_group_box = QFrame()
        sort_options_group_box.setFrameShape(QFrame.Shape.StyledPanel)
        sort_options_layout = QVBoxLayout(sort_options_group_box)
        sort_options_layout.setContentsMargins(5,5,5,5)

        sort_controls_layout = QHBoxLayout()
        sort_controls_layout.addWidget(QLabel("ソート:"))

        self.sort_key_combo = QComboBox()
        self.sort_key_combo.addItems(["ファイル名", "更新日時"])
        self.sort_key_combo.currentIndexChanged.connect(self._apply_sort_and_filter_update)
        sort_controls_layout.addWidget(self.sort_key_combo)

        self.sort_order_button = QPushButton()
        if self.current_sort_order == Qt.SortOrder.AscendingOrder: # Set initial text based on default
            self.sort_order_button.setText("昇順 ▲")
        else:
            self.sort_order_button.setText("降順 ▼")
        self.sort_order_button.clicked.connect(self._toggle_sort_order_and_apply)
        sort_controls_layout.addWidget(self.sort_order_button)

        sort_options_layout.addLayout(sort_controls_layout)
        left_layout.addWidget(sort_options_group_box)
        # --- End Sort Options UI ---

        # --- Filter UI Elements ---
        filter_group_box = QFrame() # Using QFrame for visual grouping, could be QGroupBox
        filter_group_box.setFrameShape(QFrame.Shape.StyledPanel)
        filter_layout = QVBoxLayout(filter_group_box)
        filter_layout.setContentsMargins(5,5,5,5)
        filter_layout.addWidget(QLabel("フィルター (カンマ区切りで複数ワード):"))

        # AND/OR Radio Buttons
        search_mode_layout = QHBoxLayout()
        search_mode_label = QLabel("検索条件:")
        search_mode_layout.addWidget(search_mode_label)
        self.and_radio_button = QRadioButton("AND検索")
        self.and_radio_button.setChecked(True) # Default to AND
        # self.and_radio_button.toggled.connect(self.apply_filters) # Disconnect to prevent auto-filtering
        search_mode_layout.addWidget(self.and_radio_button)
        self.or_radio_button = QRadioButton("OR検索")
        # self.or_radio_button.toggled.connect(self.apply_filters) # Disconnect to prevent auto-filtering
        search_mode_layout.addWidget(self.or_radio_button)

        # Group for exclusive selection
        self.search_mode_button_group = QButtonGroup(self)
        self.search_mode_button_group.addButton(self.and_radio_button)
        self.search_mode_button_group.addButton(self.or_radio_button)
        filter_layout.addLayout(search_mode_layout)

        self.positive_prompt_filter_edit = QLineEdit()
        self.positive_prompt_filter_edit.setPlaceholderText("Positive Prompt を含む...")
        # self.positive_prompt_filter_edit.textChanged.connect(self.apply_filters) # Disconnect textChanged
        self.positive_prompt_filter_edit.returnPressed.connect(self.apply_filters) # Connect returnPressed
        filter_layout.addWidget(self.positive_prompt_filter_edit)

        self.negative_prompt_filter_edit = QLineEdit()
        self.negative_prompt_filter_edit.setPlaceholderText("Negative Prompt を含む...")
        # self.negative_prompt_filter_edit.textChanged.connect(self.apply_filters) # Disconnect textChanged
        self.negative_prompt_filter_edit.returnPressed.connect(self.apply_filters) # Connect returnPressed
        filter_layout.addWidget(self.negative_prompt_filter_edit)

        self.generation_info_filter_edit = QLineEdit()
        self.generation_info_filter_edit.setPlaceholderText("Generation Info を含む...")
        # self.generation_info_filter_edit.textChanged.connect(self.apply_filters) # Disconnect textChanged
        self.generation_info_filter_edit.returnPressed.connect(self.apply_filters) # Connect returnPressed
        filter_layout.addWidget(self.generation_info_filter_edit)

        self.apply_filter_button = QPushButton("フィルタ適用")
        self.apply_filter_button.clicked.connect(self.apply_filters)
        filter_layout.addWidget(self.apply_filter_button)

        left_layout.addWidget(filter_group_box)
        # --- End Filter UI ---

        # --- File Operations UI ---
        file_op_group_box = QFrame()
        file_op_group_box.setFrameShape(QFrame.Shape.StyledPanel)
        file_op_layout = QVBoxLayout(file_op_group_box)
        file_op_layout.setContentsMargins(5,5,5,5)
        file_op_layout.addWidget(QLabel("ファイル操作:"))

        file_op_layout.addLayout(selection_button_layout) # Added here

        self.move_files_button = QPushButton("ファイルを移動")
        self.move_files_button.clicked.connect(self.file_operation_manager._handle_move_files_button_clicked)
        file_op_layout.addWidget(self.move_files_button)

        self.copy_mode_button = QPushButton("Copy Mode: OFF")
        self.copy_mode_button.setCheckable(True)
        self.copy_mode_button.toggled.connect(self.file_operation_manager._handle_copy_mode_toggled)
        file_op_layout.addWidget(self.copy_mode_button)

        self.copy_files_button = QPushButton("ファイルをコピー")
        self.copy_files_button.clicked.connect(self.file_operation_manager._handle_copy_files_button_clicked)
        self.copy_files_button.setEnabled(False) # Initially disabled
        file_op_layout.addWidget(self.copy_files_button)

        left_layout.addWidget(file_op_group_box)
        # --- End File Operations UI ---

        self.folder_tree_view = QTreeView()
        self.folder_tree_view.setHeaderHidden(True)
        self.file_system_model = QFileSystemModel()
        self.file_system_model.setNameFilters(["*.png", "*.jpg", "*.jpeg", "*.webp"])
        self.file_system_model.setNameFilterDisables(False)
        self.folder_tree_view.setModel(self.file_system_model)
        for i in range(1, self.file_system_model.columnCount()):
            self.folder_tree_view.hideColumn(i)
        left_layout.addWidget(self.folder_tree_view)
        self.folder_tree_view.clicked.connect(self.on_folder_tree_clicked)

        splitter.addWidget(left_panel)

        self.thumbnail_view = ToggleSelectionListView() # Use custom ListView
        self.thumbnail_view.setViewMode(ToggleSelectionListView.ViewMode.IconMode) # Access ViewMode via class
        self.thumbnail_view.setResizeMode(ToggleSelectionListView.ResizeMode.Adjust) # Access ResizeMode via class
        self.thumbnail_view.setMovement(ToggleSelectionListView.Movement.Static) # Access Movement via class
        self.thumbnail_view.setSpacing(10)
        self.thumbnail_view.setIconSize(QSize(self.current_thumbnail_size, self.current_thumbnail_size))
        self.thumbnail_view.setGridSize(QSize(self.current_thumbnail_size + 10, self.current_thumbnail_size + 10))
        self.thumbnail_view.setUniformItemSizes(True)
        self.thumbnail_view.setLayoutMode(QListView.LayoutMode.Batched) # Use QListView.LayoutMode
        self.thumbnail_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel) # Enable pixel-based scrolling
        self.thumbnail_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) # This should be fine as QAbstractItemView is imported
        self.thumbnail_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumbnail_view.customContextMenuRequested.connect(self._show_thumbnail_context_menu)
        self.thumbnail_view.item_double_clicked.connect(self.dialog_manager.open_full_image_dialog) # DialogManager経由で呼び出し

        self.thumbnail_delegate = ThumbnailDelegate(self.thumbnail_view) # Create delegate instance
        self.thumbnail_view.setItemDelegate(self.thumbnail_delegate) # Set delegate
        self.thumbnail_view.setStyleSheet("""
            QListView::item:selected {
                border: 3px solid orange;
            }
            QListView::item {
                border: none;
            }
        """)

        self.source_thumbnail_model = QStandardItemModel(self) # Source model for thumbnails

        self.filter_proxy_model = MetadataFilterProxyModel(self)
        self.filter_proxy_model.setSourceModel(self.source_thumbnail_model)

        self.thumbnail_view.setModel(self.filter_proxy_model) # Use the proxy model

        self.thumbnail_view.selectionModel().selectionChanged.connect(self.handle_thumbnail_selection_changed)
        splitter.addWidget(self.thumbnail_view)

        splitter.setSizes([300, 900])
        main_layout.addWidget(splitter)

        # self._load_settings() # Load UI specific settings after all UI elements are initialized <=self._load_app_settings()に統合
        self._apply_sort_and_filter_update() # Apply initial sort based on loaded or default settings
        self._update_status_bar_info() # Initial status bar update


    def _update_status_bar_info(self):
        if not hasattr(self, 'statusBar') or not self.statusBar:
            return
        total_items = 0
        if self.filter_proxy_model:
            total_items = self.filter_proxy_model.rowCount()
        selected_items = 0
        if hasattr(self, 'thumbnail_view') and self.thumbnail_view.selectionModel():
            selected_items = len(self.thumbnail_view.selectionModel().selectedIndexes())
        self.statusBar.showMessage(f"表示アイテム数: {total_items} / 選択アイテム数: {selected_items}")

    def _perform_sort(self):
        if not self.source_thumbnail_model:
            logger.warning("_perform_sort called but source_thumbnail_model is None.")
            return
        num_items = self.source_thumbnail_model.rowCount()
        if num_items == 0:
            logger.debug("_perform_sort: No items in model to sort.")
            return
        logger.info(f"Performing sort. Key: {self.current_sort_key_index}, Order: {self.current_sort_order}. Items: {num_items}")
        self.sort_key_combo.setEnabled(False)
        self.sort_order_button.setEnabled(False)
        QApplication.processEvents() # Ensure UI updates
        sort_start_time = time.time()
        try:
            item_data_list = []
            for i in range(num_items):
                item = self.source_thumbnail_model.item(i)
                if item:
                    file_path = item.data(Qt.ItemDataRole.UserRole)
                    icon = item.icon()
                    text = item.text()
                    metadata = item.data(METADATA_ROLE)
                    item_data_list.append({
                        "file_path": file_path,
                        "icon": icon,
                        "text": text,
                        "metadata": metadata,
                    })
            def sort_key_func(data_dict):
                file_path = data_dict["file_path"]
                if file_path is None:
                    return "" if self.current_sort_key_index == 0 else 0
                if self.current_sort_key_index == 0:  # Filename
                    return os.path.basename(file_path).lower()
                elif self.current_sort_key_index == 1:  # Update Date
                    try:
                        return os.path.getmtime(file_path)
                    except FileNotFoundError:
                        logger.warning(f"File not found for mtime (fallback): {file_path}, using 0 for sort.")
                        return 0.0
                    except Exception as e:
                        logger.error(f"Error getting mtime for {file_path} (fallback): {e}. Using 0 for sort.")
                        return 0.0
                return ""
            item_data_list.sort(key=sort_key_func, reverse=(self.current_sort_order == Qt.SortOrder.DescendingOrder))
            self.source_thumbnail_model.beginResetModel()
            self.source_thumbnail_model.clear()
            for data_dict in item_data_list:
                new_item = QStandardItem()
                new_item.setIcon(data_dict["icon"])
                new_item.setText(data_dict["text"])
                new_item.setData(data_dict["file_path"], Qt.ItemDataRole.UserRole)
                new_item.setData(data_dict["metadata"], METADATA_ROLE)
                new_item.setEditable(False)
                # --- ツールチップの再設定 ---
                if data_dict["file_path"]:
                    directory_path = os.path.dirname(data_dict["file_path"])
                    new_item.setToolTip(f"場所: {directory_path}")
                self.source_thumbnail_model.appendRow(new_item)
            self.source_thumbnail_model.endResetModel()
            logger.info(f"Sort performed and model updated. Items: {self.source_thumbnail_model.rowCount()}")
        except Exception as e:
            logger.error(f"Error during sort operation: {e}", exc_info=True)
        finally:
            self.sort_key_combo.setEnabled(True)
            self.sort_order_button.setEnabled(True)
            sort_end_time = time.time()
            logger.info(f"Sort operation took: {sort_end_time - sort_start_time:.4f} seconds.")
            self._update_status_bar_info()

    def _toggle_sort_order_and_apply(self):
        logger.debug(f"Before toggle: self.current_sort_order = {self.current_sort_order}")
        if self.current_sort_order == Qt.SortOrder.AscendingOrder:
            self.current_sort_order = Qt.SortOrder.DescendingOrder
            new_button_text = "降順 ▼"
        else:
            self.current_sort_order = Qt.SortOrder.AscendingOrder
            new_button_text = "昇順 ▲"
        self.sort_order_button.setText(new_button_text)
        logger.debug(f"After toggle: self.current_sort_order = {self.current_sort_order}, Button text set to: {new_button_text}")
        self._apply_sort_and_filter_update()

    def _apply_sort_and_filter_update(self):
        self.current_sort_key_index = self.sort_key_combo.currentIndex()
        logger.info(f"Applying sort and filter. Key Index: {self.current_sort_key_index}, Order: {self.current_sort_order}")
        self._perform_sort()


    def _create_menu_bar(self):
        """ メニューバーを作成し、アクションを直接配置 """
        menu_bar = self.menuBar()

        # --- 「設定」アクションをメニューバーに直接追加 (以前のまま) ---
        settings_action = QAction("&設定", self)
        settings_action.setStatusTip("アプリケーションの設定を変更します")
        settings_action.triggered.connect(self.dialog_manager.open_settings_dialog) # DialogManager経由で呼び出し
        menu_bar.addAction(settings_action) # メニューバーに直接「設定」を配置

        # --- 「ツール」メニューの作成 ---
        tool_menu = menu_bar.addMenu("&ツール")

        # --- 「ツール」メニュー内のアクション定義と追加 ---

        # 「ワイルドカード作成」アクション
        wc_creator_action = QAction("ワイルドカード作成 (&W)", self) # '&W' でアクセスキー W
        wc_creator_action.setStatusTip("選択された画像のプロンプトを整形・出力します。")
        wc_creator_action.triggered.connect(self.dialog_manager.open_wc_creator_dialog) # DialogManager経由で呼び出し
        tool_menu.addAction(wc_creator_action)

        # 「D&Dウィンドウ」アクション
        toggle_drop_window_action = QAction("&D＆Dウィンドウ", self) # '&'でショートカットキーヒント
        toggle_drop_window_action.setStatusTip("画像のメタデータを表示するためのドラッグ＆ドロップウィンドウを開きます")
        toggle_drop_window_action.triggered.connect(self.dialog_manager.toggle_drop_window) # DialogManager経由で呼び出し
        tool_menu.addAction(toggle_drop_window_action) # 「D&Dウィンドウ」をツールメニューの一番下に追加

    def _save_settings(self):
        """現在の設定をJSONファイルに保存する。"""
        self.app_settings["thumbnail_size"] = self.current_thumbnail_size
        self.app_settings["image_preview_mode"] = self.image_preview_mode
        self.app_settings[THUMBNAIL_RIGHT_CLICK_ACTION] = self.thumbnail_right_click_action
        self.app_settings[WC_COMMENT_OUTPUT_FORMAT] = self.wc_creator_comment_format
        self.app_settings["last_folder_path"] = self.current_folder_path
        self.app_settings["recursive_search"] = self.recursive_search_enabled
        self.app_settings["sort_key_index"] = self.current_sort_key_index
        self.app_settings["sort_order"] = self.current_sort_order.value

        self._write_app_settings_file(self.app_settings)

    def _read_app_settings_file(self):
        try:
            if os.path.exists(APP_SETTINGS_FILE):
                with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    return settings
        except Exception as e:
            logger.error(f"Error reading {APP_SETTINGS_FILE} in MainWindow: {e}")
        return {}

    def _write_app_settings_file(self, settings_dict=None): # settings_dict引数を追加
        # settings_dictがNoneの場合（_save_settingsから呼ばれない場合）は、現在の状態から作成
        if settings_dict is None:
            settings_dict = {
                "thumbnail_size": self.current_thumbnail_size,
                "image_preview_mode": self.image_preview_mode,
                THUMBNAIL_RIGHT_CLICK_ACTION: self.thumbnail_right_click_action,
                WC_COMMENT_OUTPUT_FORMAT: self.wc_creator_comment_format,
                "last_folder_path": self.current_folder_path,
                "recursive_search": self.recursive_search_enabled,
                "sort_key_index": self.current_sort_key_index,
                "sort_order": self.current_sort_order.value
            }
        try:
            with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings_dict, f, indent=4)
            logger.info(f"App settings saved via MainWindow to {APP_SETTINGS_FILE}")
        except Exception as e:
            logger.error(f"Error writing to {APP_SETTINGS_FILE} via MainWindow: {e}")

    def _load_app_settings(self):
        """アプリケーション全体の設定を読み込み、UI要素に反映する"""
        self.app_settings = self._read_app_settings_file() # self.app_settings に読み込み結果を格納

        # 画像表示モード
        self.image_preview_mode = self.app_settings.get("image_preview_mode", PREVIEW_MODE_FIT)
        logger.info(f"読み込まれた画像表示モード: {self.image_preview_mode}")

        # サムネイル右クリック動作
        self.thumbnail_right_click_action = self.app_settings.get(THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA)
        logger.info(f"読み込まれたサムネイル右クリック動作: {self.thumbnail_right_click_action}")

        # サムネイルサイズ
        loaded_thumbnail_size = self.app_settings.get("thumbnail_size", self.available_sizes[1])
        if loaded_thumbnail_size in self.available_sizes:
            self.current_thumbnail_size = loaded_thumbnail_size
        else:
            logger.warning(f"保存されたサムネイルサイズ {loaded_thumbnail_size}px は無効です。デフォルトの {self.available_sizes[1]}px を使用します。")
            self.current_thumbnail_size = self.available_sizes[1]
        logger.info(f"読み込まれたサムネイルサイズ: {self.current_thumbnail_size}px")

        # WC Creator コメント形式
        self.wc_creator_comment_format = self.app_settings.get(WC_COMMENT_OUTPUT_FORMAT, WC_FORMAT_HASH_COMMENT)
        logger.info(f"読み込まれたWC Creatorコメント形式: {self.wc_creator_comment_format}")

        # 最終フォルダパス
        if lp_val := self.app_settings.get("last_folder_path"):
            if os.path.isdir(lp_val):
                self.initial_dialog_path = lp_val
                logger.info(f"前回終了時のフォルダパスを読み込みました: {self.initial_dialog_path}")
            else:
                logger.warning(f"保存されたフォルダパスが無効または見つかりません: {lp_val}")

        # 再帰検索設定
        self.recursive_search_enabled = self.app_settings.get("recursive_search", True)
        if hasattr(self, 'recursive_toggle_button') and self.recursive_toggle_button: # UI要素が存在すれば更新
            self.recursive_toggle_button.setChecked(self.recursive_search_enabled)
            self.recursive_toggle_button.setText(f"サブフォルダ検索: {'ON' if self.recursive_search_enabled else 'OFF'}")
        logger.info(f"再帰検索設定を読み込みました: {'ON' if self.recursive_search_enabled else 'OFF'}")

        # ソート設定
        self.current_sort_key_index = self.app_settings.get("sort_key_index", 0)
        if hasattr(self, 'sort_key_combo') and self.sort_key_combo: # UI要素が存在すれば更新
            if 0 <= self.current_sort_key_index < self.sort_key_combo.count():
                self.sort_key_combo.setCurrentIndex(self.current_sort_key_index)
            else:
                logger.warning(f"保存されたソートキーインデックスが無効: {self.current_sort_key_index}。0にリセットします。")
                self.current_sort_key_index = 0
                self.sort_key_combo.setCurrentIndex(0)

        self.current_sort_order = Qt.SortOrder(self.app_settings.get("sort_order", Qt.SortOrder.AscendingOrder.value))
        if hasattr(self, 'sort_order_button') and self.sort_order_button: # UI要素が存在すれば更新
            self.sort_order_button.setText("降順 ▼" if self.current_sort_order == Qt.SortOrder.DescendingOrder else "昇順 ▲")
        logger.info(f"ソート設定を読み込みました: Key Index: {self.current_sort_key_index}, Order: {self.current_sort_order}")


    def select_folder(self):
        start_dir = ""
        if self.current_folder_path and os.path.isdir(self.current_folder_path):
            start_dir = self.current_folder_path
        elif self.initial_dialog_path and os.path.isdir(self.initial_dialog_path):
            start_dir = self.initial_dialog_path
        folder_path = QFileDialog.getExistingDirectory(self, "画像フォルダを選択", start_dir)
        if folder_path:
            logger.info(f"選択されたフォルダ: {folder_path}")
            # ★★★ 空フォルダ削除処理をここに移動 ★★★
            if os.path.isdir(folder_path):
                self._try_delete_empty_subfolders(folder_path)
            self.update_folder_tree(folder_path)

    def update_folder_tree(self, folder_path):
        self.current_folder_path = folder_path
        parent_dir = QDir(folder_path)
        root_display_path = folder_path
        if parent_dir.cdUp():
            root_display_path = parent_dir.path()
        logger.debug(f"ユーザー選択フォルダ: {folder_path}")
        logger.debug(f"ツリー表示ルート: {root_display_path}")
        self.file_system_model.setRootPath(root_display_path)
        root_index = self.file_system_model.index(root_display_path)
        self.folder_tree_view.setRootIndex(root_index)
        selected_folder_index = self.file_system_model.index(folder_path)
        if selected_folder_index.isValid():
            self.folder_tree_view.expand(selected_folder_index.parent())
            self.folder_tree_view.setCurrentIndex(selected_folder_index)
            self.folder_tree_view.scrollTo(selected_folder_index, QTreeView.ScrollHint.PositionAtCenter)
        logger.info(f"フォルダツリーを更新しました。表示ルート: {root_display_path}, 選択中: {folder_path}")
        self.load_thumbnails_from_folder(folder_path)

    def on_folder_tree_clicked(self, index):
        path = self.file_system_model.filePath(index)
        if self.file_system_model.isDir(index):
            logger.info(f"フォルダがクリックされました: {path}")
            self.current_folder_path = path
            # ★★★ 空フォルダ削除処理をここに移動 ★★★
            if os.path.isdir(path):
                self._try_delete_empty_subfolders(path)
            self.load_thumbnails_from_folder(path)
        else:
            logger.debug(f"ファイルがクリックされました: {path}")

    def load_thumbnails_from_folder(self, folder_path):
        if ImageQt is None:
            self.statusBar.showMessage("ImageQtモジュールが見つかりません。処理を中止します。", 5000)
            logger.error("ImageQt module not found. Cannot load thumbnails.")
            return
        logger.info(f"{folder_path} からサムネイルを読み込みます。")
        self.load_start_time = time.time()
        items_for_thread = [] # <--- ★items_for_thread を try の前に初期化
        image_files = []
        try:
            # 既存のサムネイルローダースレッドを安全に停止する
            if self.thumbnail_loader_thread and self.thumbnail_loader_thread.isRunning():
                logger.info("既存のサムネイル読み込みスレッドを停止します...")
                # シグナル接続を解除
                try:
                    self.thumbnail_loader_thread.thumbnailLoaded.disconnect(self.update_thumbnail_item)
                    self.thumbnail_loader_thread.progressUpdated.disconnect(self.update_progress_bar)
                    self.thumbnail_loader_thread.finished.disconnect(self.on_thumbnail_loading_finished)
                    logger.debug("既存スレッドのシグナル接続を解除しました。")
                except TypeError: # disconnect中にエラーが発生することがある (既に接続されていない場合など)
                    logger.debug("既存スレッドのシグナル接続解除中にエラー発生、または既に解除済み。")
                except Exception as e:
                    logger.error(f"既存スレッドのシグナル接続解除中に予期せぬエラー: {e}", exc_info=True)

                self.thumbnail_loader_thread.stop() # スレッドに停止を要求
                if not self.thumbnail_loader_thread.wait(7000): # タイムアウトを少し長めに設定
                    logger.warning("既存スレッドの終了待機がタイムアウトしました。")
                else:
                    logger.info("既存スレッドが正常に終了しました。")
                self.thumbnail_loader_thread.deleteLater() # Qtのイベントループで安全に削除
                self.thumbnail_loader_thread = None # 参照をクリア

            search_flags = QDirIterator.IteratorFlag.Subdirectories if self.recursive_search_enabled else QDirIterator.IteratorFlag.NoIteratorFlags
            iterator = QDirIterator(folder_path,
                                    ["*.png", "*.jpg", "*.jpeg", "*.webp"],
                                    QDir.Filter.Files | QDir.Filter.NoSymLinks,
                                    search_flags)
            while iterator.hasNext():
                image_files.append(iterator.next())
            logger.info(f"見つかった画像ファイル (再帰検索{'含む' if self.recursive_search_enabled else '含まない'}): {len(image_files)}個")
            self.is_loading_thumbnails = True
            self.folder_tree_view.setEnabled(False)
            self.recursive_toggle_button.setEnabled(False)
            self.deselect_all_button.setEnabled(False)
            self.select_all_button.setEnabled(False)
            self.positive_prompt_filter_edit.setEnabled(False)
            self.negative_prompt_filter_edit.setEnabled(False)
            self.generation_info_filter_edit.setEnabled(False)
            self.and_radio_button.setEnabled(False)
            self.or_radio_button.setEnabled(False)
            self.sort_key_combo.setEnabled(False)
            self.sort_order_button.setEnabled(False)

            # モデルをクリアする前に、本当に古いスレッドがいないことを確認
            QApplication.processEvents() # 保留中のイベントを処理

            self.source_thumbnail_model.clear()
            # 新しいフォルダを読み込む際に、非表示リストをクリアしProxyModelに通知
            self._hidden_moved_file_paths.clear() # MainWindow's list of paths to hide
            self.filter_proxy_model.set_hidden_paths(self._hidden_moved_file_paths) # Update proxy model's hidden paths
            logger.debug("source_thumbnail_model をクリアしました。")
            self.selected_file_paths.clear()
            self.metadata_cache.clear() # メタデータキャッシュもクリア
            self.thumbnail_view.setIconSize(QSize(self.current_thumbnail_size, self.current_thumbnail_size))
            self.thumbnail_view.setGridSize(QSize(self.current_thumbnail_size + 10, self.current_thumbnail_size + 10))
            placeholder_pixmap = QPixmap(self.current_thumbnail_size, self.current_thumbnail_size)
            placeholder_pixmap.fill(Qt.GlobalColor.transparent)
            placeholder_icon = QIcon(placeholder_pixmap)
            # items_for_thread = [] # 初期化を try の前に移動
            for f_path in image_files:
                item = QStandardItem()
                item.setIcon(placeholder_icon)
                item.setText(QDir().toNativeSeparators(f_path).split(QDir.separator())[-1])
                item.setEditable(False)
                item.setData(f_path, Qt.ItemDataRole.UserRole)
                self.source_thumbnail_model.appendRow(item)
                items_for_thread.append(item)
        except Exception as e:
            logger.error(f"サムネイル読み込み準備中にエラー: {e}", exc_info=True)
        
        # 新しいスレッドを作成して開始
        self.thumbnail_loader_thread = ThumbnailLoaderThread(image_files, items_for_thread, self.current_thumbnail_size)
        self.thumbnail_loader_thread.thumbnailLoaded.connect(self.update_thumbnail_item)
        self.thumbnail_loader_thread.progressUpdated.connect(self.update_progress_bar)
        self.thumbnail_loader_thread.finished.connect(self.on_thumbnail_loading_finished)
        if image_files:
            self.statusBar.showMessage(f"サムネイル読み込み中... 0/{len(image_files)}")
            self.thumbnail_loader_thread.start()
        else:
            self.statusBar.showMessage("フォルダに画像がありません", 5000)
            self.is_loading_thumbnails = False
            self.folder_tree_view.setEnabled(True)
            self.recursive_toggle_button.setEnabled(True)
            self.deselect_all_button.setEnabled(True)
            self.select_all_button.setEnabled(True)
            self.positive_prompt_filter_edit.setEnabled(True)
            self.negative_prompt_filter_edit.setEnabled(True)
            self.generation_info_filter_edit.setEnabled(True)
            self.sort_key_combo.setEnabled(True)
            self.sort_order_button.setEnabled(True)
            self.on_thumbnail_loading_finished() # UI状態をリセットするために呼ぶ

    def handle_recursive_search_toggled(self, checked):
        self.recursive_search_enabled = checked
        self.recursive_toggle_button.setText(f"サブフォルダ検索: {'ON' if checked else 'OFF'}")
        logger.info(f"再帰検索設定変更: {'ON' if checked else 'OFF'}. 次回フォルダ読み込み時に適用されます。")

    def apply_thumbnail_size_change(self, new_size):
        if self.is_loading_thumbnails:
            logger.info("現在サムネイル読み込み中のため、サイズ変更はスキップされました。")
            return False
        if new_size not in self.available_sizes:
            logger.warning(f"要求されたサムネイルサイズ {new_size}px は利用可能なサイズではありません。")
            return False
        if new_size != self.current_thumbnail_size:
            self.current_thumbnail_size = new_size
            logger.info(f"サムネイルサイズを {self.current_thumbnail_size}px に変更します。")
            if self.current_folder_path:
                logger.info(f"サムネイルサイズ変更適用: {self.current_thumbnail_size}px. 再読み込み開始...")
                self.load_thumbnails_from_folder(self.current_folder_path)
                return True
            else:
                logger.info("再読み込みするフォルダが選択されていません。サイズは次回フォルダ選択時に適用されます。")
                self.thumbnail_view.setIconSize(QSize(self.current_thumbnail_size, self.current_thumbnail_size))
                self.thumbnail_view.setGridSize(QSize(self.current_thumbnail_size + 10, self.current_thumbnail_size + 10))
                return True
        else:
            logger.info("選択されたサイズは現在のサイズと同じため、再読み込みは行いません。")
            return False

    def update_progress_bar(self, processed_count, total_files):
        self.statusBar.showMessage(f"サムネイル読み込み中... {processed_count}/{total_files}")

    def update_thumbnail_item(self, item, q_image, metadata):
        if ImageQt is None: return
        try:
            # アイテムの有効性を確認
            if item is None or item.model() is None: # model() が None ならアイテムはモデルから削除されている可能性が高い
                logger.warning("update_thumbnail_item received an invalid or deleted item. Skipping update.")
                return

            file_path = item.data(Qt.ItemDataRole.UserRole) # この行でエラーが発生していた可能性

            # file_path が取得できた場合のみ処理を続行
            if file_path is None:
                logger.warning("update_thumbnail_item: item has no file_path data. Skipping update.")
                return

            pixmap = None
            if q_image:
                pixmap = QPixmap.fromImage(q_image)

            if pixmap:
                temp_icon = QIcon(pixmap)
                item.setIcon(temp_icon) # ここでも item が無効ならエラーの可能性
            else:
                logger.warning(f"update_thumbnail_item for {file_path}: pixmap is None. Icon not set.")

            self.metadata_cache[file_path] = metadata
            item.setData(metadata, METADATA_ROLE) # ここでも item が無効ならエラーの可能性
            
            directory_path = os.path.dirname(file_path)
            item.setToolTip(f"場所: {directory_path}")

        except RuntimeError as e:
            # "wrapped C/C++ object of type QStandardItem has been deleted" のようなエラーを捕捉
            logger.warning(f"RuntimeError in update_thumbnail_item (likely item deleted): {e}. Item text (if available): {item.text() if item and item.model() else 'N/A'}")
        except Exception as e:
            # その他の予期せぬエラー
            logger.error(f"Unexpected error in update_thumbnail_item: {e}", exc_info=True)

    def on_thumbnail_loading_finished(self):
        logger.info("サムネイルの非同期読み込みが完了しました。")
        self.statusBar.showMessage("サムネイル読み込み完了", 5000)
        self.is_loading_thumbnails = False
        self.folder_tree_view.setEnabled(True)
        self.recursive_toggle_button.setEnabled(True)
        self.deselect_all_button.setEnabled(True)
        self.select_all_button.setEnabled(True)
        self.positive_prompt_filter_edit.setEnabled(True)
        self.negative_prompt_filter_edit.setEnabled(True)
        self.generation_info_filter_edit.setEnabled(True)
        self.and_radio_button.setEnabled(True)
        self.or_radio_button.setEnabled(True)
        self.sort_key_combo.setEnabled(True)
        self.sort_order_button.setEnabled(True)
        if self.filter_proxy_model:
            self.apply_filters(preserve_selection=True)
        self._update_status_bar_info()
        if self.thumbnail_loader_thread:
            self.thumbnail_loader_thread.deleteLater()
            self.thumbnail_loader_thread = None
        if self.load_start_time:
            elapsed_time = time.time() - self.load_start_time
            logger.info(f"Total thumbnail loading time for {self.current_folder_path}: {elapsed_time:.2f} seconds.")
            self.load_start_time = None

    def handle_thumbnail_selection_changed(self, selected, deselected):
        if self.is_copy_mode:
            selected_items_now_list = []
            for proxy_idx in self.thumbnail_view.selectionModel().selectedIndexes():
                source_idx = self.filter_proxy_model.mapToSource(proxy_idx)
                item = self.source_thumbnail_model.itemFromIndex(source_idx)
                if item:
                    selected_items_now_list.append(item)
            removed_items = [item for item in self.copy_selection_order if item not in selected_items_now_list]
            for item_to_remove in removed_items:
                if item_to_remove in self.copy_selection_order:
                    self.copy_selection_order.remove(item_to_remove)
                item_to_remove.setData(None, SELECTION_ORDER_ROLE)
                source_idx = self.source_thumbnail_model.indexFromItem(item_to_remove)
                proxy_idx = self.filter_proxy_model.mapFromSource(source_idx)
                if proxy_idx.isValid():
                    self.thumbnail_view.update(proxy_idx)
            newly_selected_items = [item for item in selected_items_now_list if item not in self.copy_selection_order]
            for item_to_add in newly_selected_items:
                self.copy_selection_order.append(item_to_add)
            items_to_update_display = []
            for i, item_in_order in enumerate(self.copy_selection_order):
                new_order_num = i + 1
                old_order_num = item_in_order.data(SELECTION_ORDER_ROLE)
                if old_order_num != new_order_num:
                    item_in_order.setData(new_order_num, SELECTION_ORDER_ROLE)
                    if item_in_order not in items_to_update_display:
                        items_to_update_display.append(item_in_order)
            for item_to_add in newly_selected_items:
                 if item_to_add not in items_to_update_display :
                    current_order_idx = -1
                    try:
                        current_order_idx = self.copy_selection_order.index(item_to_add)
                    except ValueError:
                        logger.error(f"Item {item_to_add.data(Qt.ItemDataRole.UserRole)} not found in copy_selection_order during update.")
                        continue
                    current_order = current_order_idx + 1
                    item_to_add.setData(current_order, SELECTION_ORDER_ROLE)
                    if item_to_add not in items_to_update_display:
                        items_to_update_display.append(item_to_add)
            for item_to_update in items_to_update_display:
                source_idx = self.source_thumbnail_model.indexFromItem(item_to_update)
                proxy_idx = self.filter_proxy_model.mapFromSource(source_idx)
                if proxy_idx.isValid():
                    self.thumbnail_view.update(proxy_idx)
            logger.debug(f"Copy mode selection order: {[item.data(Qt.ItemDataRole.UserRole) for item in self.copy_selection_order]}")
            self.selected_file_paths = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items_now_list]
        else:
             # --- Normal (Move) Mode Selection Logic ---
            self.selected_file_paths.clear()
            for proxy_index in self.thumbnail_view.selectionModel().selectedIndexes():
                source_index = self.filter_proxy_model.mapToSource(proxy_index)
                item = self.source_thumbnail_model.itemFromIndex(source_index)
                if item:
                    file_path = item.data(Qt.ItemDataRole.UserRole)
                    if file_path:
                        self.selected_file_paths.append(file_path)
            logger.debug(f"Move mode selection: {self.selected_file_paths}")
        self._update_status_bar_info()

    def select_all_thumbnails(self):
        if self.thumbnail_view.model() and self.thumbnail_view.model().rowCount() > 0:
            self.thumbnail_view.selectAll()
            logger.info("すべての表示中サムネイルを選択しました。")
        else:
            logger.info("選択対象のサムネイルがありません。")
        self._update_status_bar_info()

    def deselect_all_thumbnails(self):
        self.thumbnail_view.clearSelection()
        logger.info("すべてのサムネイルの選択を解除しました。")
        self._update_status_bar_info()

    def apply_filters(self, preserve_selection=False):
        if not preserve_selection:
            self.deselect_all_thumbnails()
        if self.filter_proxy_model:
            search_mode = "AND" if self.and_radio_button.isChecked() else "OR"
            self.filter_proxy_model.set_search_mode(search_mode)
            logger.debug(f"Search mode set to: {search_mode}")
            self.filter_proxy_model.set_positive_prompt_filter(self.positive_prompt_filter_edit.text())
            self.filter_proxy_model.set_negative_prompt_filter(self.negative_prompt_filter_edit.text())
            self.filter_proxy_model.set_generation_info_filter(self.generation_info_filter_edit.text())
        else:
            logger.debug("Filter proxy model not yet initialized for apply_filters call.")
        self._update_status_bar_info()

    # --- ★★★ START: DropWindow連携メソッド ★★★ ---
    # --- ★★★ END: DropWindow連携メソッド ★★★ ---

    def _open_wc_creator_dialog(self):
        logger.info("ワイルドカード作成ツールを起動します。")

        selected_proxy_indexes = self.thumbnail_view.selectionModel().selectedIndexes()
        if not selected_proxy_indexes:
            QMessageBox.information(self, "情報", "作成対象の画像をサムネイル一覧から選択してください。")
            return

        selected_files_for_wc = []
        metadata_for_wc = []

        processed_paths = set()

        for proxy_idx in selected_proxy_indexes:
            if proxy_idx.column() == 0:
                source_idx = self.filter_proxy_model.mapToSource(proxy_idx)
                item = self.source_thumbnail_model.itemFromIndex(source_idx)
                if item:
                    file_path = item.data(Qt.ItemDataRole.UserRole)
                    if file_path and file_path not in processed_paths:
                        metadata = item.data(METADATA_ROLE)
                        if not isinstance(metadata, dict):
                            metadata = self.metadata_cache.get(file_path)
                        if not isinstance(metadata, dict):
                            logger.warning(f"WC Creator用メタデータ: {file_path} のキャッシュが見つからないため、再抽出します。")
                            metadata = extract_image_metadata(file_path)
                            self.metadata_cache[file_path] = metadata
                        
                        if isinstance(metadata, dict):
                            selected_files_for_wc.append(file_path)
                            metadata_for_wc.append(metadata)
                            processed_paths.add(file_path)
                        else:
                            logger.error(f"WC Creator: {file_path} のメタデータ取得に失敗しました。スキップします。")

        if not selected_files_for_wc:
            QMessageBox.warning(self, "エラー", "有効な画像データが見つかりませんでした。")
            return

        logger.info(f"{len(selected_files_for_wc)} 個の画像をWC Creatorに渡します。")
        wc_dialog = WCCreatorDialog(
            selected_file_paths=selected_files_for_wc,
            metadata_list=metadata_for_wc,
            output_format=self.wc_creator_comment_format,
            parent=self
        )
        wc_dialog.exec()
        logger.info("プロンプト整形ツールを閉じました。")

    # --- File Operation Completion Logic (called by FileOperationManager) ---
    def _process_file_op_completion(self, result):
        logger.info(f"File operation finished. Result: {result}")
        status = result.get('status', 'unknown')
        operation_type = result.get('operation_type', 'unknown')
        if status == 'cancelled':
            self.statusBar.showMessage("ファイル操作がキャンセルされました。", 5000)
            return
        errors = result.get('errors', [])
        successfully_moved_src_paths = result.get('successfully_moved_src_paths', []) # For move
        if operation_type == "move":
            moved_count = result.get('moved_count', 0)
            renamed_files = result.get('renamed_files', [])
            if moved_count > 0 and successfully_moved_src_paths:
                 logger.info(f"Successfully moved {moved_count} files. Updating model.")
                 path_to_item_map = {}
                 for row in range(self.source_thumbnail_model.rowCount()):
                     item = self.source_thumbnail_model.item(row)
                     if item:
                         item_path = item.data(Qt.ItemDataRole.UserRole)
                         if item_path:
                             path_to_item_map[item_path] = item
                 items_to_remove_from_model = []
                 for path_to_remove in successfully_moved_src_paths:
                     item_to_remove = path_to_item_map.get(path_to_remove)
                     if item_to_remove:
                         items_to_remove_from_model.append(item_to_remove)
                     else:
                         logger.warning(f"Moved path {path_to_remove} not found in source model's path_to_item_map for removal.")
                 items_to_remove_from_model.sort(key=lambda x: x.row() if x and x.model() == self.source_thumbnail_model else -1, reverse=True)

                 # --- 選択変更シグナルを一時的にブロック ---
                 try:
                     self.thumbnail_view.selectionModel().selectionChanged.disconnect(self.handle_thumbnail_selection_changed)
                     logger.debug("selectionChanged signal disconnected.")
                 except TypeError:
                     logger.warning("selectionChanged signal was not connected, cannot disconnect.")
                 # --- シグナルブロック終わり ---

                 # 削除対象の行番号リストを作成 (降順になっているはず)
                 rows_to_delete_indices = []
                 for item_to_remove_instance in items_to_remove_from_model:
                     if item_to_remove_instance and item_to_remove_instance.model() == self.source_thumbnail_model:
                         rows_to_delete_indices.append(item_to_remove_instance.row())
                     elif item_to_remove_instance:
                         logger.warning(f"Item for path {item_to_remove_instance.data(Qt.ItemDataRole.UserRole)} is no longer in the expected model or is invalid, skipping removal.")
                 if rows_to_delete_indices:
                     for row_num in rows_to_delete_indices:
                         # QModelIndex() は親がないトップレベルアイテムを示す
                         self.source_thumbnail_model.beginRemoveRows(QModelIndex(), row_num, row_num)
                         removed = self.source_thumbnail_model.removeRow(row_num)
                         self.source_thumbnail_model.endRemoveRows()
                         if not removed:
                             logger.warning(f"Failed to remove row {row_num} from source model.")                         
              
                 # --- 選択変更シグナルを再接続し、手動でハンドラを呼び出す ---
                 self.thumbnail_view.selectionModel().selectionChanged.connect(self.handle_thumbnail_selection_changed)
                 logger.debug("selectionChanged signal reconnected.")
                 # モデル変更後に選択状態が自動的に更新されるが、ハンドラは呼ばれない可能性があるため手動で呼ぶ
                 self.handle_thumbnail_selection_changed(QItemSelection(), QItemSelection()) # 空の選択変更としてハンドラをトリガー
                 self.selected_file_paths.clear()
                 # _update_status_bar_info() は handle_thumbnail_selection_changed 内で呼ばれる
                 self._update_status_bar_info()
            if renamed_files:
                dialog = RenamedFilesDialog(renamed_files, self)
                dialog.exec()
            if errors:
                QMessageBox.warning(self, "移動エラー", "以下のエラーが発生しました:\n" + "\n".join(errors))
            if moved_count > 0:
                 self.statusBar.showMessage(f"{moved_count}個のファイルを移動しました。", 5000)
            elif not errors:
                 self.statusBar.showMessage("移動するファイルがありませんでした、または処理が完了しました。", 3000)
            elif errors and moved_count == 0:
                 self.statusBar.showMessage("ファイルの移動に失敗しました。", 3000)
        elif operation_type == "copy":
            copied_count = result.get('copied_count', 0)
            if errors:
                QMessageBox.warning(self, "コピーエラー", "以下のエラーが発生しました:\n" + "\n".join(errors))
            if copied_count > 0:
                self.statusBar.showMessage(f"{copied_count}個のファイルをコピーしました。", 5000)
            elif not errors:
                self.statusBar.showMessage("コピーするファイルがありませんでした、または処理が完了しました。", 3000)
        if status == 'completed' and not errors:
            self.deselect_all_thumbnails()
            if operation_type == "copy":
                for item_in_order in self.copy_selection_order:
                    if item_in_order.data(SELECTION_ORDER_ROLE) is not None:
                        item_in_order.setData(None, SELECTION_ORDER_ROLE)
                        source_idx = self.source_thumbnail_model.indexFromItem(item_in_order)
                        proxy_idx = self.filter_proxy_model.mapFromSource(source_idx)
                        if proxy_idx.isValid():
                            self.thumbnail_view.update(proxy_idx)
                self.copy_selection_order.clear()
            # ★★★ ファイル移動完了後の自動的な空フォルダ削除処理を削除 ★★★


    def _try_delete_empty_subfolders(self, target_folder_path):
        if not target_folder_path or not os.path.isdir(target_folder_path):
            logger.debug(f"指定されたフォルダパス '{target_folder_path}' が無効なため、空フォルダ削除をスキップします。")
            return
        logger.info(f"'{target_folder_path}' 内の空サブフォルダ検索を開始します。")
        try:
            empty_folders = self._find_empty_subfolders(target_folder_path)
        except Exception as e:
            logger.error(f"'{target_folder_path}' の空フォルダ検索中にエラー: {e}", exc_info=True)
            return
        if not empty_folders:
            logger.info(f"'{target_folder_path}' 内に空のサブフォルダは見つかりませんでした。")
            return
        logger.info(f"'{target_folder_path}' 内に {len(empty_folders)} 個の空サブフォルダが見つかりました。削除処理を開始します。")
        self._handle_send_empty_folders_to_trash(target_folder_path, empty_folders)

    def _handle_send_empty_folders_to_trash(self, parent_folder_path_for_context, empty_folders_to_delete):
        logger.debug(f"_handle_send_empty_folders_to_trash called for parent '{parent_folder_path_for_context}' with {len(empty_folders_to_delete)} folders.")
        if not empty_folders_to_delete:
            logger.info("削除対象の空フォルダがありません。")
            return
        confirm_message = "空のサブフォルダが見つかりました。ゴミ箱に移動しますか？\n\n"
        for folder in empty_folders_to_delete:
            confirm_message += f"- {folder}\n"
        reply = QMessageBox.question(self, "空フォルダ削除の確認", confirm_message,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            successful_sends = []
            failed_sends = []
            logger.info(f"ユーザーが '{parent_folder_path_for_context}' 内の空フォルダ削除を承認しました。")
            try:
                for folder_path_str in empty_folders_to_delete:
                    normalized_path = ""
                    try:
                        normalized_path = os.path.normpath(folder_path_str)
                        logger.info(f"ゴミ箱へ移動 (正規化試行): {normalized_path} (元: {folder_path_str})")
                        send2trash.send2trash(normalized_path)
                        successful_sends.append(normalized_path)
                    except Exception as e:
                        path_for_error_msg = normalized_path if normalized_path else folder_path_str
                        logger.error(f"フォルダ '{path_for_error_msg}' のゴミ箱への移動に失敗: {e}", exc_info=True)
                        failed_sends.append(f"{path_for_error_msg}: {e}")
                summary_title = f"空フォルダ削除完了 ({os.path.basename(parent_folder_path_for_context)})"
                summary_text = f"{len(successful_sends)}個のフォルダをゴミ箱に移動しました。"
                if failed_sends:
                    summary_text += f"\n\n以下のフォルダの移動に失敗しました:\n" + "\n".join(failed_sends)
                    QMessageBox.warning(self, summary_title + "（一部エラー）", summary_text)
                else:
                    QMessageBox.information(self, summary_title, summary_text)
            except ImportError:
                logger.error("send2trashモジュールが見つかりません。pip install Send2Trash を実行してください。")
                QMessageBox.critical(self, "エラー", "send2trashモジュールが必要です。インストールしてください。")
                return
            except Exception as e:
                logger.error(f"空フォルダのゴミ箱への移動中に予期せぬエラー: {e}", exc_info=True)
                QMessageBox.critical(self, "エラー", f"処理中に予期せぬエラーが発生しました:\n{e}")
            finally:
                if successful_sends or failed_sends:
                    if os.path.exists(parent_folder_path_for_context):
                        logger.info(f"空フォルダ削除処理試行後、フォルダツリー '{parent_folder_path_for_context}' を更新します。")
                        self.update_folder_tree(parent_folder_path_for_context)
                    elif not os.path.exists(parent_folder_path_for_context) and successful_sends :
                        logger.info(f"スキャン対象フォルダ '{parent_folder_path_for_context}' が削除されたため、ツリーのルートをクリアします。")
                        self.file_system_model.setRootPath("")
                        self.source_thumbnail_model.clear()
                        if self.current_folder_path == parent_folder_path_for_context:
                            self.current_folder_path = None
        else:
             logger.info(f"'{parent_folder_path_for_context}' 内の空のサブフォルダのゴミ箱への移動はキャンセルされました。")

    def _find_empty_subfolders(self, parent_dir):
        empty_folders = []
        for entry in os.scandir(parent_dir):
            if entry.is_dir():
                if self._is_dir_empty_recursive(entry.path):
                    empty_folders.append(entry.path)
        return empty_folders

    def _is_dir_empty_recursive(self, dir_path):
        try:
            entries = list(os.scandir(dir_path))
        except OSError as e:
            logger.warning(f"Could not scan directory '{dir_path}' due to OSError: {e}. Treating as non-empty for empty folder check.")
            return False
        if not entries:
            return True
        for entry in entries:
            if entry.is_file():
                return False
            elif entry.is_dir():
                if not self._is_dir_empty_recursive(entry.path):
                    return False
        return True

    def closeEvent(self, event: QCloseEvent):
        """ ★★★ 修正: アプリケーション終了時にDropWindowも閉じる ★★★ """
        logger.info("アプリケーション終了処理を開始します...")
        self._save_settings()

        # --- ★追加★ ---
        # DialogManagerが管理するDropWindowインスタンスが存在すれば、閉じる
        if self.dialog_manager.drop_window_instance: # DialogManagerのインスタンスを参照
             try:
                 logger.debug("DropWindowインスタンスを閉じます。")
                 self.dialog_manager.drop_window_instance.close() # DialogManager経由で閉じる
             except Exception as e:
                 logger.error(f"DropWindowインスタンスのクローズ中にエラー: {e}")
        # --- ★追加 終わり★ ---

        # Ensure threads are properly shut down if any are running
        if self.thumbnail_loader_thread and self.thumbnail_loader_thread.isRunning():
            logger.info("サムネイル読み込みスレッドを停止します...")
            self.thumbnail_loader_thread.stop()
            self.thumbnail_loader_thread.quit()
            if not self.thumbnail_loader_thread.wait(3000): # Wait up to 3 seconds
                logger.warning("サムネイル読み込みスレッドの終了待機がタイムアウトしました。")

        if self.file_operations._thread and self.file_operations._thread.isRunning():
            logger.info("ファイル操作スレッドに停止を要求します...")
            self.file_operations.stop_operation()
            if not self.file_operations._thread.wait(1000):
                 logger.warning("ファイル操作スレッドの終了待機がタイムアウトしました。")

        logger.info("アプリケーションを終了します。")
        super().closeEvent(event)

    def _show_thumbnail_context_menu(self, pos):
        proxy_index = self.thumbnail_view.indexAt(pos)
        if not proxy_index.isValid():
            return
        if self.thumbnail_right_click_action == RIGHT_CLICK_ACTION_METADATA:
            self.dialog_manager.open_metadata_dialog(proxy_index) # DialogManager経由で呼び出し
        elif self.thumbnail_right_click_action == RIGHT_CLICK_ACTION_MENU:
            menu = QMenu(self)
            metadata_action = QAction("メタデータを表示", self)
            metadata_action.triggered.connect(lambda: self.dialog_manager.open_metadata_dialog(proxy_index)) # DialogManager経由
            menu.addAction(metadata_action)
            open_location_action = QAction("ファイルの場所を開く", self)
            open_location_action.triggered.connect(lambda: self._open_file_location_for_item(proxy_index))
            menu.addAction(open_location_action)
            menu.exec(self.thumbnail_view.viewport().mapToGlobal(pos))
        else:
            logger.warning(f"不明なサムネイル右クリック動作設定: {self.thumbnail_right_click_action}")
            self.dialog_manager.open_metadata_dialog(proxy_index) # DialogManager経由で呼び出し

    def _open_file_location_for_item(self, proxy_index):
        if not proxy_index.isValid():
            logger.warning("ファイルの場所を開く操作が、無効なインデックスで呼び出されました。")
            return
        source_index = self.filter_proxy_model.mapToSource(proxy_index)
        item = self.source_thumbnail_model.itemFromIndex(source_index)
        if not item:
             logger.warning(f"ファイルの場所を開く操作: インデックスからアイテムを取得できませんでした...")
             return
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            logger.warning("ファイルの場所を開く操作: アイテムにファイルパスが関連付けられていません。")
            QMessageBox.warning(self, "エラー", "アイテムにファイルパスが関連付けられていません。")
            return
        dir_path = os.path.dirname(file_path)
        if not os.path.isdir(dir_path):
            logger.warning(f"ファイルの場所を開く操作: ディレクトリ '{dir_path}' が見つかりません。")
            QMessageBox.warning(self, "エラー", f"ディレクトリ '{dir_path}' が見つかりません。")
            return
        try:
            logger.info(f"エクスプローラで '{dir_path}' を開きます。")
            os.startfile(dir_path)
        except AttributeError:
            logger.error("os.startfile が現在のプラットフォームでサポートされていません。")
            QMessageBox.critical(self, "エラー", "このプラットフォームではファイルの場所を開く機能はサポートされていません。")
        except FileNotFoundError:
            logger.error(f"os.startfile でディレクトリ '{dir_path}' が見つかりませんでした。")
            QMessageBox.critical(self, "エラー", f"ディレクトリ '{dir_path}' が見つかりませんでした。")
        except Exception as e:
            logger.error(f"ディレクトリ '{dir_path}' を開く際に予期せぬエラーが発生しました: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"ディレクトリを開く際にエラーが発生しました:\n{e}")


# (クラス定義の外、ファイルの末尾)
# このファイルが直接実行された場合の起動ロジックなどがあれば、
# それは変更せずにそのままにしてください。
# 例:
# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     # logging setup here, if any
#     main_win = MainWindow()
#     main_win.show()
#     sys.exit(app.exec())