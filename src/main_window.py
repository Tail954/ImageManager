import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeView, QSplitter, QFrame, QFileDialog, QSlider, QListView, QDialog, # Added QListView and QDialog
    QAbstractItemView, QLineEdit, QMenu, QRadioButton, QButtonGroup, QMessageBox, QProgressDialog, QComboBox # Added QComboBox
)
from PyQt6.QtGui import QFileSystemModel, QPixmap, QIcon, QStandardItemModel, QStandardItem, QAction, QCloseEvent
from PyQt6.QtCore import Qt, QDir, QSize, QTimer, QDirIterator, QVariant, QSortFilterProxyModel
import os # For path operations
from pathlib import Path # For path operations
import json # For settings
import time # For load time measurement
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle

from .thumbnail_loader import ThumbnailLoaderThread
from .thumbnail_delegate import ThumbnailDelegate
from .metadata_filter_proxy_model import MetadataFilterProxyModel
from .image_metadata_dialog import ImageMetadataDialog
from .thumbnail_list_view import ToggleSelectionListView # Import custom ListView
from .file_operations import FileOperations # Import FileOperations
from .renamed_files_dialog import RenamedFilesDialog # Import new dialog
from .full_image_dialog import FullImageDialog # Import the new full image dialog
from .settings_dialog import SettingsDialog, PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM # Import settings dialog and constants
import send2trash # Import at module level

# PillowのImageオブジェクトをQImageに変換するために必要
import logging # Add logging import

# PIL.ImageQt が Pillow 9.0.0 以降で推奨される方法
try:
    from PIL import ImageQt
except ImportError:
    logging.error("Pillow (PIL) の ImageQt モジュールが見つかりません。pip install Pillow --upgrade を試してください。")
    ImageQt = None

logger = logging.getLogger(__name__)

APP_SETTINGS_FILE = "app_settings.json"

from .constants import (
    METADATA_ROLE, SELECTION_ORDER_ROLE,
    THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.thumbnail_loader_thread = None
        self.metadata_cache = {} # Cache for metadata: {file_path: metadata_dict}
        self.metadata_dialog_instance = None # To keep track of the metadata dialog
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
        self.file_operations = FileOperations(self) # Initialize FileOperations
        self.progress_dialog = None # For cancellation dialog
        self.initial_dialog_path = None # For storing path from settings
        self.metadata_dialog_last_geometry = None # To store the last geometry of the metadata dialog
        self.full_image_dialog_instance = None # To store the single instance of FullImageDialog
        self.image_preview_mode = PREVIEW_MODE_FIT # Default, will be overwritten by _load_app_settings
        self.current_sort_key_index = 0 # 0: Filename, 1: Update Date
        self.current_sort_order = Qt.SortOrder.AscendingOrder # Qt.SortOrder.AscendingOrder or Qt.SortOrder.DescendingOrder
        self.load_start_time = None # For load time measurement
        self.thumbnail_right_click_action = RIGHT_CLICK_ACTION_METADATA # Default value

        # Load application-wide settings first
        self._load_app_settings()

        # Menu Bar
        self._create_menu_bar()

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
        self.move_files_button.clicked.connect(self._handle_move_files_button_clicked)
        file_op_layout.addWidget(self.move_files_button)

        self.copy_mode_button = QPushButton("Copy Mode")
        self.copy_mode_button.setCheckable(True)
        self.copy_mode_button.toggled.connect(self._handle_copy_mode_toggled)
        file_op_layout.addWidget(self.copy_mode_button)

        self.copy_files_button = QPushButton("ファイルをコピー")
        self.copy_files_button.clicked.connect(self._handle_copy_files_button_clicked)
        self.copy_files_button.setEnabled(False) # Initially disabled
        file_op_layout.addWidget(self.copy_files_button)

        # self.cancel_op_button = QPushButton("キャンセル") # Removed, will use QProgressDialog
        # self.cancel_op_button.clicked.connect(self._handle_cancel_op_button_clicked)
        # self.cancel_op_button.setEnabled(False) # Initially disabled
        # file_op_layout.addWidget(self.cancel_op_button)

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
        # self.thumbnail_view.metadata_requested.connect(self.handle_metadata_requested) # Disconnected, replaced by customContextMenuRequested
        self.thumbnail_view.item_double_clicked.connect(self.handle_thumbnail_double_clicked) # Connect custom double click signal
        
        self.thumbnail_delegate = ThumbnailDelegate(self.thumbnail_view) # Create delegate instance
        self.thumbnail_view.setItemDelegate(self.thumbnail_delegate) # Set delegate
        self.thumbnail_view.setStyleSheet("""
            QListView::item:selected {
                border: 3px solid orange;
                /* background-color: transparent; */ /* Optional: if default selection bg is an issue */
            }
            QListView::item {
                border: none; /* Ensure non-selected items have no border from this stylesheet */
                /* padding: 3px; */ /* Adjust if border makes items too close without it */
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

        self._load_settings() # Load UI specific settings after all UI elements are initialized
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
        """
        Sorts the items in the source_thumbnail_model based on the current
        sort key and order.
        """
        if not self.source_thumbnail_model:
            logger.warning("_perform_sort called but source_thumbnail_model is None.")
            return

        num_items = self.source_thumbnail_model.rowCount()
        if num_items == 0:
            logger.debug("_perform_sort: No items in model to sort.")
            return

        logger.info(f"Performing sort. Key: {self.current_sort_key_index}, Order: {self.current_sort_order}. Items: {num_items}")

        # Disable sort UI during sort operation
        self.sort_key_combo.setEnabled(False)
        self.sort_order_button.setEnabled(False)
        QApplication.processEvents() # Ensure UI updates
        sort_start_time = time.time()

        try:
            # 1. Get all item data from the model
            item_data_list = []
            for i in range(num_items):
                item = self.source_thumbnail_model.item(i)
                if item:
                    file_path = item.data(Qt.ItemDataRole.UserRole)
                    icon = item.icon()
                    text = item.text()
                    metadata = item.data(METADATA_ROLE)
                    # mtime_cached = item.data(MTIME_ROLE) # Get cached mtime # MTIME_ROLE removed
                    item_data_list.append({
                        "file_path": file_path,
                        "icon": icon,
                        "text": text,
                        "metadata": metadata,
                        # "mtime_cached": mtime_cached # MTIME_ROLE removed
                    })

            # 2. Define sort key function based on extracted data
            def sort_key_func(data_dict):
                file_path = data_dict["file_path"]
                if file_path is None: # Should ideally not happen if items are valid
                    return "" if self.current_sort_key_index == 0 else 0

                if self.current_sort_key_index == 0:  # Filename
                    return os.path.basename(file_path).lower()
                elif self.current_sort_key_index == 1:  # Update Date
                    # mtime = data_dict.get("mtime_cached") # MTIME_ROLE removed
                    # if mtime is None: # MTIME_ROLE removed
                    try:
                        # logger.warning(f"MTIME_ROLE data not found for {file_path} in sort_key_func (mtime_cached was None), fetching from disk.") # MTIME_ROLE removed
                        return os.path.getmtime(file_path)
                    except FileNotFoundError:
                        logger.warning(f"File not found for mtime (fallback): {file_path}, using 0 for sort.")
                        return 0.0 
                    except Exception as e:
                        logger.error(f"Error getting mtime for {file_path} (fallback): {e}. Using 0 for sort.")
                        return 0.0
                    # return float(mtime) if mtime is not None else 0.0 # MTIME_ROLE removed
                return "" 

            # 3. Sort the list of item data
            item_data_list.sort(key=sort_key_func, reverse=(self.current_sort_order == Qt.SortOrder.DescendingOrder))
            
            # 4. Rebuild the model with new items created from sorted data
            self.source_thumbnail_model.beginResetModel()
            self.source_thumbnail_model.clear() 
            for data_dict in item_data_list:
                new_item = QStandardItem()
                new_item.setIcon(data_dict["icon"])
                new_item.setText(data_dict["text"])
                new_item.setData(data_dict["file_path"], Qt.ItemDataRole.UserRole)
                new_item.setData(data_dict["metadata"], METADATA_ROLE)
                # new_item.setData(data_dict.get("mtime_cached"), MTIME_ROLE) # MTIME_ROLE removed
                new_item.setEditable(False) 
                self.source_thumbnail_model.appendRow(new_item)
            self.source_thumbnail_model.endResetModel()
            logger.info(f"Sort performed and model updated. Items: {self.source_thumbnail_model.rowCount()}")

        except Exception as e:
            logger.error(f"Error during sort operation: {e}", exc_info=True)
        finally:
            # Re-enable sort UI after sort operation
            self.sort_key_combo.setEnabled(True)
            self.sort_order_button.setEnabled(True)
            sort_end_time = time.time()
            logger.info(f"Sort operation took: {sort_end_time - sort_start_time:.4f} seconds.")
            self._update_status_bar_info() # Update status bar after sort


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
        # self.current_sort_key_index is updated by sort_key_combo.currentIndexChanged directly
        # self.current_sort_order is updated by _toggle_sort_order_and_apply
        # So, when this method is called, these should already reflect the desired state.
        
        # Ensure current_sort_key_index is up-to-date from the combo box,
        # as this method can also be called by sort_key_combo.currentIndexChanged
        self.current_sort_key_index = self.sort_key_combo.currentIndex()

        logger.info(f"Applying sort and filter. Key Index: {self.current_sort_key_index}, Order: {self.current_sort_order}")
        
        # Perform sort on the source model directly
        self._perform_sort()

        # After sorting the source model, the filter proxy model will automatically reflect changes
        # if its source has been reset. If filters are active, they will be re-applied.
        # We might still want to explicitly call invalidateFilter on the proxy if only sort changed
        # and we want to ensure the view updates correctly with existing filters.
        # However, beginResetModel/endResetModel on source should be sufficient.

        # For now, let's assume the filter proxy model handles updates correctly after source reset.
        # If filtering needs to be explicitly re-triggered after a sort, we can add:
        # if self.filter_proxy_model:
        #     self.filter_proxy_model.invalidateFilter()

        # The old QSortFilterProxyModel specific calls are removed:
        # if self.filter_proxy_model:
            # logger.debug(f"Calling filter_proxy_model.set_sort_criteria({self.current_sort_key_index}, {self.current_sort_order})")
            # self.filter_proxy_model.set_sort_criteria(self.current_sort_key_index, self.current_sort_order)
            
            # Use the proxy model's current sort column, which might be set or defaulted.
            # Our custom lessThan primarily uses self.sort_key_index and self.sort_order from set_sort_criteria.
            # sort_column_to_use = self.filter_proxy_model.sortColumn() # Get current sort column from proxy
            # if sort_column_to_use == -1: # If no sort column is set, default to 0
            #     sort_column_to_use = 0
            
            # Log the state of the proxy model's sort properties BEFORE calling sort
            # logger.debug(f"ProxyModel state before set_sort_criteria: source_rows={self.source_thumbnail_model.rowCount()}, proxy_rows={self.filter_proxy_model.rowCount()}, sortColumn={self.filter_proxy_model.sortColumn()}, sortOrder={self.filter_proxy_model.sortOrder()}, dynamicSortFilter={self.filter_proxy_model.dynamicSortFilter()}, sortRole={self.filter_proxy_model.sortRole()}")

            # self.filter_proxy_model.set_sort_criteria(self.current_sort_key_index, self.current_sort_order) # This is already called before this block
            # logger.debug(f"ProxyModel state after set_sort_criteria: source_rows={self.source_thumbnail_model.rowCount()}, proxy_rows={self.filter_proxy_model.rowCount()}")

            # Explicitly set sort column and order on the proxy model itself
            # logger.debug(f"Explicitly setting proxy sortColumn to {sort_column_to_use} and sortOrder to {self.current_sort_order}")
            # self.filter_proxy_model.setSortColumn(sort_column_to_use) # Removed: QSortFilterProxyModel does not have this public setter
            # self.filter_proxy_model.setSortOrder(self.current_sort_order) # Removed: QSortFilterProxyModel does not have this public setter

            # logger.debug(f"Calling filter_proxy_model.apply_internal_sort({sort_column_to_use}, {self.current_sort_order})")
            
            # self.filter_proxy_model.beginResetModel() # Removed: Moved to overridden sort method in proxy model
            # self.filter_proxy_model.apply_internal_sort(sort_column_to_use, self.current_sort_order) 
            # self.filter_proxy_model.endResetModel() # Removed: Moved to overridden sort method in proxy model
            
            # logger.debug(f"ProxyModel state after apply_internal_sort: source_rows={self.source_thumbnail_model.rowCount()}, proxy_rows={self.filter_proxy_model.rowCount()}, sortColumn={self.filter_proxy_model.sortColumn()}, sortOrder={self.filter_proxy_model.sortOrder()}")
            
            # logger.info(f"Proxy model sort triggered. Key Index: {self.current_sort_key_index}, Order: {self.current_sort_order}")

            # --- Add debug log for first few items after sort ---
            # proxy_row_count = self.filter_proxy_model.rowCount()
            # logger.debug(f"Proxy model row count after sort: {proxy_row_count}")
            # if proxy_row_count > 0:
            #     num_items_to_log = min(3, proxy_row_count)
            #     logger.debug(f"First {num_items_to_log} items in proxy model after sort:")
            #     for i in range(num_items_to_log):
            #         proxy_idx = self.filter_proxy_model.index(i, 0)
            #         if proxy_idx.isValid():
            #             source_idx = self.filter_proxy_model.mapToSource(proxy_idx)
            #             # It's safer to get data directly from source model if item might be complex
            #             file_path = self.source_thumbnail_model.data(self.source_thumbnail_model.index(source_idx.row(), 0), Qt.ItemDataRole.UserRole)
            #             logger.debug(f"  ProxyRow {i}: FilePath = {os.path.basename(file_path if file_path else 'N/A')}")
            #         else:
            #             logger.debug(f"  ProxyRow {i}: Invalid proxy index.")
            # else:
            #     logger.debug("Proxy model is empty after sort (no items to log).")
            # --- End debug log ---
        # else:
            # logger.warning("Filter proxy model not available for sorting yet.")
        
        # After sorting, it's good practice to re-apply filters if they are active,
        # or at least ensure the view is updated.
        # self.apply_filters(preserve_selection=True) # Re-apply filters to ensure view consistency

    # Removed _simple_debug_test_slot and the test_debug_button creation

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        settings_action = QAction("&設定", self)
        settings_action.triggered.connect(self._open_settings_dialog)
        menu_bar.addAction(settings_action)

    def _open_settings_dialog(self):
        dialog = SettingsDialog(
            current_thumbnail_size=self.current_thumbnail_size,
            available_thumbnail_sizes=self.available_sizes,
            current_preview_mode=self.image_preview_mode,
            current_right_click_action=self.thumbnail_right_click_action, # Pass current right-click action
            parent=self
        )
        if dialog.exec():
            # Preview mode handling
            new_preview_mode = dialog.get_selected_preview_mode()
            if self.image_preview_mode != new_preview_mode:
                self.image_preview_mode = new_preview_mode
                logger.info(f"画像表示モードが変更されました: {self.image_preview_mode}")

            # Thumbnail Right-Click Action handling
            new_right_click_action = dialog.get_selected_right_click_action()
            if self.thumbnail_right_click_action != new_right_click_action:
                self.thumbnail_right_click_action = new_right_click_action
                logger.info(f"サムネイル右クリック時の動作が変更されました: {self.thumbnail_right_click_action}")

            # Thumbnail size handling
            new_thumbnail_size = dialog.get_selected_thumbnail_size()
            old_thumbnail_size = self.current_thumbnail_size # Store before potential change by dialog

            if new_thumbnail_size != old_thumbnail_size:
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Icon.Question)
                msg_box.setWindowTitle("サムネイルサイズ変更の確認")
                msg_box.setText(f"サムネイルサイズを {new_thumbnail_size}px に変更しますか？\n"
                                 "表示中の全サムネイルが再生成されます。\n"
                                 "画像の枚数によっては時間がかかる場合があります。")
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)
                reply = msg_box.exec() # This returns an integer (the enum value)

                # QMessageBox.StandardButton.Ok.value is typically 1024
                if reply == 1024: # Explicitly compare with the integer value of Ok
                    logger.info(f"ユーザーがサムネイルサイズ変更を承認: {old_thumbnail_size}px -> {new_thumbnail_size}px")
                    if self.apply_thumbnail_size_change(new_thumbnail_size):
                        # self.current_thumbnail_size is updated within apply_thumbnail_size_change
                        logger.info(f"サムネイルサイズが {self.current_thumbnail_size}px に適用されました。")
                    else:
                        # Change was not applied (e.g., loading, or same size)
                        # Revert the dialog's potential change if it wasn't applied by MainWindow
                        # This path should ideally not be hit if apply_thumbnail_size_change handles all cases
                        logger.warning(f"サムネイルサイズ変更 {new_thumbnail_size}px の適用に失敗、または変更なし。")
                        # No need to revert self.current_thumbnail_size as it's only set on success in apply_thumbnail_size_change
                else:
                    logger.info("ユーザーがサムネイルサイズ変更をキャンセルしました。")
                    # If user cancels, we should ensure the dialog reflects the original size if it was changed internally
                    # For now, SettingsDialog is expected to manage its internal state until OK.
                    # If OK is pressed and then this confirmation is cancelled, the setting should not persist.
                    # The new_thumbnail_size from dialog.get_selected_thumbnail_size() was the one *before* this confirmation.
                    # We don't update self.current_thumbnail_size.
                    # The settings file will be written with the *original* self.current_thumbnail_size
                    # unless the user confirmed the change.

            # Save all settings (including potentially updated preview mode and thumbnail size)
            # This ensures that even if only one setting was changed in the dialog,
            # all settings managed by MainWindow are saved correctly.
            current_app_settings = self._read_app_settings_file()
            current_app_settings["image_preview_mode"] = self.image_preview_mode
            current_app_settings["thumbnail_size"] = self.current_thumbnail_size # Save the confirmed size
            current_app_settings[THUMBNAIL_RIGHT_CLICK_ACTION] = self.thumbnail_right_click_action # Add this line
            self._write_app_settings_file(current_app_settings)
            logger.info("設定ダイアログがOKで閉じられました。設定を保存しました。")

        else:
            logger.info("設定ダイアログがキャンセルされました。変更は保存されません。")

    def _read_app_settings_file(self):
        """Reads the entire app_settings.json file."""
        # This method is similar to SettingsDialog._load_settings but only reads.
        # Consider refactoring to a common utility if this becomes unwieldy.
        try:
            if os.path.exists(APP_SETTINGS_FILE):
                with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    return settings
        except Exception as e:
            logger.error(f"Error reading {APP_SETTINGS_FILE} in MainWindow: {e}")
        return {} # Return empty dict on error or if file doesn't exist

    def _write_app_settings_file(self, settings_dict):
        """Writes the given dictionary to app_settings.json."""
        try:
            with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings_dict, f, indent=4)
            logger.info(f"App settings saved via MainWindow to {APP_SETTINGS_FILE}")
        except Exception as e:
            logger.error(f"Error writing to {APP_SETTINGS_FILE} via MainWindow: {e}")

    def _load_app_settings(self):
        """Loads application-specific settings like image_preview_mode."""
        # This method should ideally be the single source for loading from APP_SETTINGS_FILE
        # for settings MainWindow cares about.
        
        settings = self._read_app_settings_file()
        self.image_preview_mode = settings.get("image_preview_mode", PREVIEW_MODE_FIT)
        logger.info(f"読み込まれた画像表示モード (MainWindow): {self.image_preview_mode}")

        self.thumbnail_right_click_action = settings.get(THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA)
        logger.info(f"読み込まれたサムネイル右クリック動作 (MainWindow): {self.thumbnail_right_click_action}")
        
        # Load thumbnail size
        loaded_thumbnail_size = settings.get("thumbnail_size", self.available_sizes[1]) # Default to 128 if not found
        if loaded_thumbnail_size in self.available_sizes:
            self.current_thumbnail_size = loaded_thumbnail_size
        else:
            logger.warning(f"保存されたサムネイルサイズ {loaded_thumbnail_size}px は無効です。デフォルトの {self.available_sizes[1]}px を使用します。")
            self.current_thumbnail_size = self.available_sizes[1]
        logger.info(f"読み込まれたサムネイルサイズ (MainWindow): {self.current_thumbnail_size}px")

        # _load_settings() handles UI state like last folder, recursive search.
        # These are loaded separately as they might affect UI elements directly during init.

    def select_folder(self):
        start_dir = ""
        if self.current_folder_path and os.path.isdir(self.current_folder_path):
            start_dir = self.current_folder_path
        elif self.initial_dialog_path and os.path.isdir(self.initial_dialog_path):
            start_dir = self.initial_dialog_path
        
        folder_path = QFileDialog.getExistingDirectory(self, "画像フォルダを選択", start_dir)
        if folder_path:
            logger.info(f"選択されたフォルダ: {folder_path}")
            self.update_folder_tree(folder_path)

    def update_folder_tree(self, folder_path):
        self.current_folder_path = folder_path # Store user-selected path for thumbnail loading

        parent_dir = QDir(folder_path)
        root_display_path = folder_path
        if parent_dir.cdUp():
            root_display_path = parent_dir.path()
        
        logger.debug(f"ユーザー選択フォルダ: {folder_path}")
        logger.debug(f"ツリー表示ルート: {root_display_path}")

        self.file_system_model.setRootPath(root_display_path)
        root_index = self.file_system_model.index(root_display_path)
        self.folder_tree_view.setRootIndex(root_index)
        
        # Expand to the selected folder and select it
        selected_folder_index = self.file_system_model.index(folder_path)
        if selected_folder_index.isValid():
            self.folder_tree_view.expand(selected_folder_index.parent()) # Ensure parent is expanded
            self.folder_tree_view.setCurrentIndex(selected_folder_index)
            self.folder_tree_view.scrollTo(selected_folder_index, QTreeView.ScrollHint.PositionAtCenter)

        logger.info(f"フォルダツリーを更新しました。表示ルート: {root_display_path}, 選択中: {folder_path}")
        self.load_thumbnails_from_folder(folder_path) # Load images from the user-selected folder
        # Attempt to clean empty subfolders after loading thumbnails for the folder selected via button
        if os.path.isdir(folder_path): # Ensure path is still a valid directory
            self._try_delete_empty_subfolders(folder_path)

    def on_folder_tree_clicked(self, index):
        path = self.file_system_model.filePath(index)
        if self.file_system_model.isDir(index):
            logger.info(f"フォルダがクリックされました: {path}")
            self.current_folder_path = path
            self.load_thumbnails_from_folder(path)
            # Attempt to clean empty subfolders after loading thumbnails for the selected folder
            if os.path.isdir(path): # Ensure path is still a valid directory
                self._try_delete_empty_subfolders(path)
        else:
            logger.debug(f"ファイルがクリックされました: {path}")

    def load_thumbnails_from_folder(self, folder_path):
        if ImageQt is None: # Ensure ImageQt is available before loading
            self.statusBar.showMessage("ImageQtモジュールが見つかりません。処理を中止します。", 5000)
            logger.error("ImageQt module not found. Cannot load thumbnails.")
            return

        logger.info(f"{folder_path} からサムネイルを読み込みます。")
        self.load_start_time = time.time() # Record start time
        image_files = []
        try:
            search_flags = QDirIterator.IteratorFlag.Subdirectories if self.recursive_search_enabled else QDirIterator.IteratorFlag.NoIteratorFlags
            iterator = QDirIterator(folder_path,
                                    ["*.png", "*.jpg", "*.jpeg", "*.webp"],
                                    QDir.Filter.Files | QDir.Filter.NoSymLinks,
                                    search_flags)
            while iterator.hasNext():
                image_files.append(iterator.next())
            
            logger.info(f"見つかった画像ファイル (再帰検索{'含む' if self.recursive_search_enabled else '含まない'}): {len(image_files)}個")
            
            self.is_loading_thumbnails = True
            # self.size_slider.setEnabled(False) # Removed
            self.folder_tree_view.setEnabled(False)
            self.recursive_toggle_button.setEnabled(False)
            self.deselect_all_button.setEnabled(False)
            self.select_all_button.setEnabled(False) # Disable during load
            self.positive_prompt_filter_edit.setEnabled(False)
            self.negative_prompt_filter_edit.setEnabled(False)
            self.generation_info_filter_edit.setEnabled(False)
            self.and_radio_button.setEnabled(False)
            self.or_radio_button.setEnabled(False)
            self.sort_key_combo.setEnabled(False) # Disable sort UI
            self.sort_order_button.setEnabled(False) # Disable sort UI

            self.source_thumbnail_model.clear() # Clear the source model
            self.selected_file_paths.clear() # Clear selection list
            self.metadata_cache.clear() # Clear metadata cache as well
            # self.thumbnail_view.clearSelection() # Model clear should handle this

            self.thumbnail_view.setIconSize(QSize(self.current_thumbnail_size, self.current_thumbnail_size))
            self.thumbnail_view.setGridSize(QSize(self.current_thumbnail_size + 10, self.current_thumbnail_size + 10))

            placeholder_pixmap = QPixmap(self.current_thumbnail_size, self.current_thumbnail_size)
            placeholder_pixmap.fill(Qt.GlobalColor.transparent)
            placeholder_icon = QIcon(placeholder_pixmap)
            items_for_thread = [] # Collect items to pass to the thread

            for f_path in image_files:
                item = QStandardItem()
                item.setIcon(placeholder_icon)
                item.setText(QDir().toNativeSeparators(f_path).split(QDir.separator())[-1])
                item.setEditable(False)
                item.setData(f_path, Qt.ItemDataRole.UserRole) # Store file path
                # Metadata will be added in update_thumbnail_item via METADATA_ROLE
                self.source_thumbnail_model.appendRow(item)
                items_for_thread.append(item) # Add to list

        except Exception as e:
            logger.error(f"サムネイル読み込み準備中にエラー: {e}", exc_info=True)
        
        if self.thumbnail_loader_thread and self.thumbnail_loader_thread.isRunning():
            logger.info("既存のスレッドを停止します...")
            self.thumbnail_loader_thread.stop()
            self.thumbnail_loader_thread.quit()
            if not self.thumbnail_loader_thread.wait(5000):
                logger.warning("既存スレッドの終了待機がタイムアウトしました。")
            else:
                logger.info("既存スレッドが正常に終了しました。")

        self.thumbnail_loader_thread = ThumbnailLoaderThread(image_files, items_for_thread, self.current_thumbnail_size) # Pass items_for_thread
        self.thumbnail_loader_thread.thumbnailLoaded.connect(self.update_thumbnail_item)
        self.thumbnail_loader_thread.progressUpdated.connect(self.update_progress_bar)
        self.thumbnail_loader_thread.finished.connect(self.on_thumbnail_loading_finished)
        if image_files:
            self.statusBar.showMessage(f"サムネイル読み込み中... 0/{len(image_files)}")
            self.thumbnail_loader_thread.start()
        else:
            self.statusBar.showMessage("フォルダに画像がありません", 5000)
            self.is_loading_thumbnails = False # Reset flag if no files
            # self.size_slider.setEnabled(True) # Removed
            self.folder_tree_view.setEnabled(True)
            self.recursive_toggle_button.setEnabled(True)
            self.deselect_all_button.setEnabled(True)
            self.select_all_button.setEnabled(True) # Enable after load
            self.positive_prompt_filter_edit.setEnabled(True)
            self.negative_prompt_filter_edit.setEnabled(True)
            self.generation_info_filter_edit.setEnabled(True)
            self.sort_key_combo.setEnabled(True) # Re-enable sort UI
            self.sort_order_button.setEnabled(True) # Re-enable sort UI

    def handle_recursive_search_toggled(self, checked):
        self.recursive_search_enabled = checked
        self.recursive_toggle_button.setText(f"サブフォルダ検索: {'ON' if checked else 'OFF'}")
        logger.info(f"再帰検索設定変更: {'ON' if checked else 'OFF'}. 次回フォルダ読み込み時に適用されます。")

    def apply_thumbnail_size_change(self, new_size):
        # logger.debug(f"apply_thumbnail_size_change called with new_size={new_size}. self.is_loading_thumbnails={self.is_loading_thumbnails}, self.current_thumbnail_size={self.current_thumbnail_size}") # DEBUG LOG REMOVED
        if self.is_loading_thumbnails:
            logger.info("現在サムネイル読み込み中のため、サイズ変更はスキップされました。")
            return False # Indicate that the change was not applied

        if new_size not in self.available_sizes:
            logger.warning(f"要求されたサムネイルサイズ {new_size}px は利用可能なサイズではありません。")
            return False

        if new_size != self.current_thumbnail_size:
            self.current_thumbnail_size = new_size
            logger.info(f"サムネイルサイズを {self.current_thumbnail_size}px に変更します。")
            if self.current_folder_path:
                logger.info(f"サムネイルサイズ変更適用: {self.current_thumbnail_size}px. 再読み込み開始...")
                self.load_thumbnails_from_folder(self.current_folder_path)
                return True # Change applied
            else:
                logger.info("再読み込みするフォルダが選択されていません。サイズは次回フォルダ選択時に適用されます。")
                # Update icon and grid sizes for next load, even if no folder is current
                self.thumbnail_view.setIconSize(QSize(self.current_thumbnail_size, self.current_thumbnail_size))
                self.thumbnail_view.setGridSize(QSize(self.current_thumbnail_size + 10, self.current_thumbnail_size + 10))
                return True # Size preference updated
        else:
            logger.info("選択されたサイズは現在のサイズと同じため、再読み込みは行いません。")
            return False # No change needed

    def update_progress_bar(self, processed_count, total_files):
        self.statusBar.showMessage(f"サムネイル読み込み中... {processed_count}/{total_files}")

    def update_thumbnail_item(self, item, q_image, metadata): # Removed mtime parameter
        if ImageQt is None: return
        if not item: # Should not happen if thread sends valid items
            logger.error("update_thumbnail_item received a None item.")
            return

        file_path = item.data(Qt.ItemDataRole.UserRole) # Get file_path from item for cache key

        pixmap = None
        if q_image: # q_image can be None if loading failed in thread
            pixmap = QPixmap.fromImage(q_image)
        
        if pixmap:
            temp_icon = QIcon(pixmap)
            item.setIcon(temp_icon)
        else:
            if file_path: # Log with file_path if available
                logger.warning(f"update_thumbnail_item for {file_path}: pixmap is None (q_image was None or conversion failed). Icon not set.")
            else: # Fallback log if file_path couldn't be retrieved
                logger.warning(f"update_thumbnail_item for an item (path unknown): pixmap is None. Icon not set.")
        
        # Store metadata in cache (if file_path is valid) and item
        if file_path:
            self.metadata_cache[file_path] = metadata
        else:
            logger.error("Cannot cache metadata as file_path is missing from item in update_thumbnail_item.")
            
        item.setData(metadata, METADATA_ROLE) # Store metadata dict directly
        # item.setData(mtime, MTIME_ROLE) # Store mtime # MTIME_ROLE removed

        if file_path:
            directory_path = os.path.dirname(file_path)
            item.setToolTip(f"場所: {directory_path}")
                
        # # --- End Debug Log ---

    def on_thumbnail_loading_finished(self):
        logger.info("サムネイルの非同期読み込みが完了しました。")
        self.statusBar.showMessage("サムネイル読み込み完了", 5000)
        self.is_loading_thumbnails = False
        # self.size_slider.setEnabled(True) # Removed
        self.folder_tree_view.setEnabled(True)
        self.recursive_toggle_button.setEnabled(True)
        self.deselect_all_button.setEnabled(True)
        self.select_all_button.setEnabled(True)
        self.positive_prompt_filter_edit.setEnabled(True)
        self.negative_prompt_filter_edit.setEnabled(True)
        self.generation_info_filter_edit.setEnabled(True)
        self.and_radio_button.setEnabled(True)
        self.or_radio_button.setEnabled(True)
        self.sort_key_combo.setEnabled(True) # Re-enable sort UI
        self.sort_order_button.setEnabled(True) # Re-enable sort UI

        if self.filter_proxy_model: # Apply initial filter if model exists
            self.apply_filters(preserve_selection=True) # Preserve selection after loading
        
        self._update_status_bar_info() # Update status bar after loading

        if self.thumbnail_loader_thread:
            self.thumbnail_loader_thread.deleteLater()
            self.thumbnail_loader_thread = None

        if self.load_start_time:
            elapsed_time = time.time() - self.load_start_time
            logger.info(f"Total thumbnail loading time for {self.current_folder_path}: {elapsed_time:.2f} seconds.")
            self.load_start_time = None # Reset for next load

    def handle_thumbnail_selection_changed(self, selected, deselected):
        if self.is_copy_mode:
            # --- Copy Mode Selection Logic ---
            # Use a list for selected_items_now as QStandardItem is not hashable for sets
            selected_items_now_list = [] 
            for proxy_idx in self.thumbnail_view.selectionModel().selectedIndexes():
                source_idx = self.filter_proxy_model.mapToSource(proxy_idx)
                item = self.source_thumbnail_model.itemFromIndex(source_idx)
                if item:
                    selected_items_now_list.append(item)

            # Items that were in copy_selection_order but are not selected anymore
            removed_items = [item for item in self.copy_selection_order if item not in selected_items_now_list]
            for item_to_remove in removed_items:
                if item_to_remove in self.copy_selection_order: # Ensure it's still there before removing
                    self.copy_selection_order.remove(item_to_remove)
                item_to_remove.setData(None, SELECTION_ORDER_ROLE) # Clear order number
                # Trigger update for this item
                source_idx = self.source_thumbnail_model.indexFromItem(item_to_remove)
                proxy_idx = self.filter_proxy_model.mapFromSource(source_idx)
                if proxy_idx.isValid():
                    self.thumbnail_view.update(proxy_idx)


            # Items that are selected now but were not in copy_selection_order
            newly_selected_items = [item for item in selected_items_now_list if item not in self.copy_selection_order]
            for item_to_add in newly_selected_items:
                self.copy_selection_order.append(item_to_add) # Add to end of list

            # Re-assign order numbers based on current self.copy_selection_order
            items_to_update_display = [] # Use list instead of set
            for i, item_in_order in enumerate(self.copy_selection_order):
                new_order_num = i + 1
                old_order_num = item_in_order.data(SELECTION_ORDER_ROLE)
                if old_order_num != new_order_num:
                    item_in_order.setData(new_order_num, SELECTION_ORDER_ROLE)
                    if item_in_order not in items_to_update_display: # Avoid duplicates
                        items_to_update_display.append(item_in_order)
            
            # Also update items that were newly selected and might not have had their order set yet
            for item_to_add in newly_selected_items:
                 if item_to_add not in items_to_update_display : 
                    current_order_idx = -1
                    try:
                        current_order_idx = self.copy_selection_order.index(item_to_add)
                    except ValueError:
                        logger.error(f"Item {item_to_add.data(Qt.ItemDataRole.UserRole)} not found in copy_selection_order during update.")
                        continue # Skip if item somehow isn't in the list
                    
                    current_order = current_order_idx + 1
                    item_to_add.setData(current_order, SELECTION_ORDER_ROLE) # Ensure it has an order
                    if item_to_add not in items_to_update_display: # Avoid duplicates
                        items_to_update_display.append(item_to_add)


            for item_to_update in items_to_update_display:
                source_idx = self.source_thumbnail_model.indexFromItem(item_to_update)
                proxy_idx = self.filter_proxy_model.mapFromSource(source_idx)
                if proxy_idx.isValid():
                    self.thumbnail_view.update(proxy_idx)
            
            logger.debug(f"Copy mode selection order: {[item.data(Qt.ItemDataRole.UserRole) for item in self.copy_selection_order]}")
            # In copy mode, self.selected_file_paths is not primarily used for file operations,
            # but we can update it for consistency or other potential uses.
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
        
        # Update status bar or other UI elements based on selection count if needed
        # self.statusBar.showMessage(f"{len(self.selected_file_paths)} items selected")
        self._update_status_bar_info()


    def select_all_thumbnails(self):
        # Operates on the view, which uses the (proxy) model
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

    def apply_filters(self, preserve_selection=False): # Added preserve_selection parameter
        # Clear current selection before applying filters, unless preserving
        if not preserve_selection:
            self.deselect_all_thumbnails()

        if self.filter_proxy_model:
            search_mode = "AND" if self.and_radio_button.isChecked() else "OR"
            self.filter_proxy_model.set_search_mode(search_mode)
            logger.debug(f"Search mode set to: {search_mode}")

            self.filter_proxy_model.set_positive_prompt_filter(self.positive_prompt_filter_edit.text())
            self.filter_proxy_model.set_negative_prompt_filter(self.negative_prompt_filter_edit.text())
            self.filter_proxy_model.set_generation_info_filter(self.generation_info_filter_edit.text())
            # invalidateFilter() is called within the proxy model's setters for text filters
        else:
            logger.debug("Filter proxy model not yet initialized for apply_filters call.")
        self._update_status_bar_info() # Update status bar after applying filters

    def handle_metadata_requested(self, proxy_index):
        if not proxy_index.isValid():
            logger.debug("handle_metadata_requested: Received invalid proxy_index.")
            return

        source_index = self.filter_proxy_model.mapToSource(proxy_index)
        item = self.source_thumbnail_model.itemFromIndex(source_index)
        if not item:
            logger.debug(f"handle_metadata_requested: Could not get item from source_index {source_index.row()},{source_index.column()}.")
            return

        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            logger.warning(f"handle_metadata_requested: No file path associated with item at proxy_index {proxy_index.row()},{proxy_index.column()}.")
            return
        
        data_from_item = item.data(METADATA_ROLE)
        final_metadata_to_show = {} 

        if isinstance(data_from_item, dict):
            final_metadata_to_show = data_from_item
            # logger.debug(f"Metadata for {file_path} from item role: {final_metadata_to_show}")
        else:
            # logger.debug(f"Metadata for {file_path} not in item role (Type: {type(data_from_item)}). Trying cache.")
            cached_metadata = self.metadata_cache.get(file_path)
            if isinstance(cached_metadata, dict):
                final_metadata_to_show = cached_metadata
                # logger.debug(f"Metadata for {file_path} from cache: {final_metadata_to_show}")
            else:
                logger.warning(f"Metadata for {file_path} not found or not a dict in cache either. Type: {type(cached_metadata)}. Using empty dict.")
        
        if not isinstance(final_metadata_to_show, dict):
            logger.error(f"CRITICAL - final_metadata_to_show is NOT a dict for {file_path}! Type: {type(final_metadata_to_show)}. Forcing empty dict.")
            final_metadata_to_show = {}
            
        self.show_metadata_dialog_for_item(final_metadata_to_show, file_path)

    def show_metadata_dialog_for_item(self, metadata_dict, item_file_path_for_debug=None): # Added item_file_path_for_debug
        # # --- Added Debug Log ---
        # if item_file_path_for_debug:
            # normalized_image_path_log = item_file_path_for_debug.replace("\\", "/")
            # target_file_for_debug_log_raw = r"G:\test\00005-4187066497.jpg"
            # normalized_target_path_log = target_file_for_debug_log_raw.replace("\\", "/")
            # if normalized_image_path_log == normalized_target_path_log:
                # logger.info(f"DEBUG_TARGET_MAIN_WINDOW_SHOW_DIALOG: show_metadata_dialog_for_item called for {item_file_path_for_debug}")
                # logger.info(f"DEBUG_TARGET_MAIN_WINDOW_SHOW_DIALOG: Metadata to show: {metadata_dict}")
        # # --- End Debug Log ---

        # If the instance is None (no dialog open, or previous was closed and reference cleared)
        if self.metadata_dialog_instance is None:
            self.metadata_dialog_instance = ImageMetadataDialog(metadata_dict, self, item_file_path_for_debug)
            self.metadata_dialog_instance.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self.metadata_dialog_instance.finished.connect(self._on_metadata_dialog_finished)
            
            if self.metadata_dialog_last_geometry:
                # Ensure the geometry is valid and on a visible screen
                # For simplicity, we'll just restore it. Advanced checks can be added later.
                # A basic check: ensure it's not off-screen in a very obvious way (e.g. negative coords far off)
                # More robust check would involve QScreen.availableGeometry()
                screen_rect = QApplication.primaryScreen().availableGeometry()
                if screen_rect.intersects(self.metadata_dialog_last_geometry):
                    self.metadata_dialog_instance.setGeometry(self.metadata_dialog_last_geometry)
                else:
                    logger.warning("Last metadata dialog geometry is off-screen, centering instead.")
                    # Center on parent logic could be added here if needed
            
            self.metadata_dialog_instance.show()
        else:
            # If instance is not None, it means it's already open. Update its content.
            self.metadata_dialog_instance.update_metadata(metadata_dict, item_file_path_for_debug)
            if not self.metadata_dialog_instance.isVisible():
                self.metadata_dialog_instance.show() 
        
        self.metadata_dialog_instance.raise_()
        self.metadata_dialog_instance.activateWindow()

    def _on_metadata_dialog_finished(self, result): # result is QDialog.DialogCode (accepted/rejected)
        # Slot to be called when the metadata dialog is closed.
        sender_dialog = self.sender()
        if sender_dialog == self.metadata_dialog_instance:
            if isinstance(sender_dialog, QDialog):
                 self.metadata_dialog_last_geometry = sender_dialog.geometry()
                 logger.debug(f"Metadata dialog closed. Stored geometry: {self.metadata_dialog_last_geometry}")
            self.metadata_dialog_instance = None

    def _on_full_image_dialog_finished(self):
        """Slot to clear the reference when FullImageDialog is closed."""
        if self.sender() == self.full_image_dialog_instance:
            logger.debug("FullImageDialog closed, clearing instance reference.")
            self.full_image_dialog_instance = None

    def handle_thumbnail_double_clicked(self, proxy_index):
        if not proxy_index.isValid():
            logger.debug("handle_thumbnail_double_clicked: Received invalid proxy_index.")
            return

        source_index = self.filter_proxy_model.mapToSource(proxy_index)
        item = self.source_thumbnail_model.itemFromIndex(source_index)
        if not item:
            logger.debug(f"handle_thumbnail_double_clicked: Could not get item from source_index {source_index.row()},{source_index.column()}.")
            return

        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            logger.warning(f"handle_thumbnail_double_clicked: No file path associated with item at proxy_index {proxy_index.row()},{proxy_index.column()}.")
            return
        
        logger.info(f"Thumbnail double-clicked: {file_path}")
        
        
        logger.info(f"Thumbnail double-clicked: {file_path}")

        # Prepare list of all currently visible (filtered) image paths
        visible_image_paths = []
        for row in range(self.filter_proxy_model.rowCount()):
            proxy_idx = self.filter_proxy_model.index(row, 0)
            source_idx = self.filter_proxy_model.mapToSource(proxy_idx)
            item = self.source_thumbnail_model.itemFromIndex(source_idx)
            if item:
                visible_image_paths.append(item.data(Qt.ItemDataRole.UserRole))
        
        current_idx_in_visible_list = -1
        if file_path in visible_image_paths:
            current_idx_in_visible_list = visible_image_paths.index(file_path)
        else:
            # Should not happen if double-clicked item is from the view
            logger.error(f"Double-clicked file path {file_path} not found in visible items list.")
            return

        try:
            if self.full_image_dialog_instance is None:
                logger.debug(f"No existing FullImageDialog instance, creating new one with mode: {self.image_preview_mode}")
                self.full_image_dialog_instance = FullImageDialog(
                    visible_image_paths, 
                    current_idx_in_visible_list, 
                    preview_mode=self.image_preview_mode, # Pass the preview mode
                    parent=self
                )
                self.full_image_dialog_instance.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                self.full_image_dialog_instance.finished.connect(self._on_full_image_dialog_finished)
                self.full_image_dialog_instance.show()
            else:
                logger.debug(f"Existing FullImageDialog instance found, updating image list, index, and mode: {self.image_preview_mode}")
                # update_image in FullImageDialog needs to accept preview_mode if it can change dynamically
                # For now, FullImageDialog sets its mode on __init__. If mode changes while dialog is open,
                # it won't reflect until dialog is recreated.
                # The current update_image in FullImageDialog doesn't take preview_mode.
                # This implies that if the setting changes, an open dialog won't change its mode.
                # This is acceptable for now as per plan.
                self.full_image_dialog_instance.update_image(visible_image_paths, current_idx_in_visible_list)
        except Exception as e:
            logger.error(f"Error opening or updating full image dialog for {file_path}: {e}", exc_info=True)
            QMessageBox.critical(self, "画像表示エラー", f"画像ダイアログの表示・更新中にエラーが発生しました:\n{e}")
            if self.full_image_dialog_instance: # If instance exists but failed, clear it
                self.full_image_dialog_instance.close() # Attempt to close gracefully
                self.full_image_dialog_instance = None


    # --- File Operation Handlers ---
    def _handle_copy_mode_toggled(self, checked):
        self.is_copy_mode = checked
        if checked:
            self.copy_mode_button.setText("Copy Mode Exit")
            self.move_files_button.setEnabled(False)
            self.copy_files_button.setEnabled(True)
            self.deselect_all_thumbnails() # Clear selection
            self.copy_selection_order.clear() # Clear copy order
            logger.info("Copy Mode Enabled.")
            # TODO: Implement logic to show numbers on thumbnails when selected in copy mode
        else:
            self.copy_mode_button.setText("Copy Mode")
            self.move_files_button.setEnabled(True)
            self.copy_files_button.setEnabled(False)
            self.deselect_all_thumbnails() # Clear selection
            self.copy_selection_order.clear() # Clear copy order
            logger.info("Copy Mode Disabled (Move Mode Enabled).")
            # Clear any existing order numbers from items when exiting copy mode
            for row in range(self.source_thumbnail_model.rowCount()):
                item = self.source_thumbnail_model.item(row)
                if item and item.data(SELECTION_ORDER_ROLE) is not None:
                    item.setData(None, SELECTION_ORDER_ROLE)
                    # Trigger update for this item if it's visible
                    source_idx = self.source_thumbnail_model.indexFromItem(item)
                    proxy_idx = self.filter_proxy_model.mapFromSource(source_idx)
                    if proxy_idx.isValid():
                         self.thumbnail_view.update(proxy_idx) # Or self.source_thumbnail_model.itemChanged(item)

    def _handle_move_files_button_clicked(self):
        logger.debug(f"Move files button clicked. Selected files: {self.selected_file_paths}")
        if not self.selected_file_paths:
            logger.info("移動するファイルが選択されていません。")
            self.statusBar.showMessage("移動するファイルを選択してください。", 3000)
            return

        destination_folder = QFileDialog.getExistingDirectory(self, "移動先フォルダを選択", self.current_folder_path or "")
        if destination_folder:
            logger.info(f"移動先フォルダが選択されました: {destination_folder}")
            logger.info(f"移動対象ファイル: {self.selected_file_paths}")
            if self.file_operations.start_operation("move", self.selected_file_paths, destination_folder):
                self._set_file_op_buttons_enabled(False) # Disable buttons first
                # Show progress dialog
                total_files_to_move = len(self.selected_file_paths)
                self.progress_dialog = QProgressDialog(
                    f"ファイルを移動中... (0/{total_files_to_move})", 
                    "キャンセル", 0, total_files_to_move, self
                )
                self.progress_dialog.setWindowTitle("ファイル移動")
                self.progress_dialog.setMinimumDuration(0) # Show immediately
                self.progress_dialog.canceled.connect(self.file_operations.stop_operation)
                self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                self.progress_dialog.setValue(0)
                # self.statusBar.showMessage(f"移動処理を開始しました... ({len(self.selected_file_paths)}個のファイル)", 0) # Progress dialog will show info
            else:
                self.statusBar.showMessage("別のファイル操作が実行中です。", 3000)
        else:
            logger.info("移動先フォルダの選択がキャンセルされました。")

    def _handle_copy_files_button_clicked(self):
        logger.debug(f"Copy files button clicked. Copy selection order: {[item.data(Qt.ItemDataRole.UserRole) for item in self.copy_selection_order]}")
        if not self.copy_selection_order:
            logger.info("コピーするファイルが選択されていません (選択順)。")
            self.statusBar.showMessage("コピーするファイルを順番に選択してください。", 3000)
            return

        destination_folder = QFileDialog.getExistingDirectory(self, "コピー先フォルダを選択", self.current_folder_path or "")
        if destination_folder:
            # Pass the QStandardItem list directly for copy_selection_order
            if self.file_operations.start_operation("copy", None, destination_folder, copy_selection_order=self.copy_selection_order):
                self._set_file_op_buttons_enabled(False) # Disable buttons first
                # Show progress dialog
                total_files_to_copy = len(self.copy_selection_order)
                self.progress_dialog = QProgressDialog(
                    f"ファイルをコピー中... (0/{total_files_to_copy})", 
                    "キャンセル", 0, total_files_to_copy, self
                )
                self.progress_dialog.setWindowTitle("ファイルコピー")
                self.progress_dialog.setMinimumDuration(0) # Show immediately
                self.progress_dialog.canceled.connect(self.file_operations.stop_operation)
                self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                self.progress_dialog.setValue(0)
                # self.statusBar.showMessage(f"コピー処理を開始しました... ({len(self.copy_selection_order)}個のファイル)", 0) # Progress dialog will show info
            else:
                self.statusBar.showMessage("別のファイル操作が実行中です。", 3000)
        else:
            logger.info("コピー先フォルダの選択がキャンセルされました。")

    def _set_file_op_buttons_enabled(self, enabled):
        """Enable/disable file operation related buttons."""
        # 'enabled' is True when operations are NOT running (i.e., buttons should be active)
        # 'enabled' is False when an operation IS running (i.e., buttons should be inactive)
        self.move_files_button.setEnabled(enabled and not self.is_copy_mode)
        self.copy_files_button.setEnabled(enabled and self.is_copy_mode)
        self.copy_mode_button.setEnabled(enabled)
        
        # self.cancel_op_button.setEnabled(not enabled) # Removed, QProgressDialog handles cancel

        # Potentially disable other UI elements like folder tree, filters during operation
        self.folder_select_button.setEnabled(enabled)
        self.folder_tree_view.setEnabled(enabled)
        # Add other UI elements that should be disabled during file operations

    def _handle_cancel_op_button_clicked(self):
        logger.info("Cancel button clicked. Requesting to stop file operation.")
        self.file_operations.stop_operation()
        # The cancel button will be disabled by _handle_file_op_finished or _handle_file_op_error
        # once the worker acknowledges the stop and finishes.
        # We can also disable it immediately here for faster UI feedback,
        # but it might be re-enabled briefly if the worker takes time to stop.
        # For now, let the finish/error handlers manage its final state.

    def _handle_file_op_progress(self, processed_count, total_count):
        dialog = self.progress_dialog # Assign to a local variable at the start of the slot
        if dialog:
            # Check if the dialog was cancelled by the user.
            if dialog.wasCanceled():
                logger.debug(f"Progress update ({processed_count}/{total_count}) received but progress_dialog was canceled by user.")
                return

            try:
                # Use the local 'dialog' variable for all operations
                dialog.setMaximum(total_count)
                dialog.setValue(processed_count)
                dialog.setLabelText(f"処理中: {processed_count}/{total_count} ファイル...")
            except RuntimeError as e: # Catches errors like "wrapped C/C++ object of type QProgressDialog has been deleted"
                logger.warning(f"Error updating progress dialog (likely already closed or invalid): {e}")
                # If a RuntimeError occurs, it means the Qt object is gone.
                # self.progress_dialog might be cleared by another slot (_handle_file_op_finished/_error)
                # so we don't strictly need to set self.progress_dialog = None here,
                # but it's good to be aware the 'dialog' reference is now stale.
        else:
            logger.debug(f"Progress update ({processed_count}/{total_count}) received but self.progress_dialog was already None.")


    def _handle_file_op_error(self, error_message):
        logger.error(f"File operation error: {error_message}")
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        QMessageBox.critical(self, "ファイル操作エラー", f"エラーが発生しました:\n{error_message}")
        self.statusBar.showMessage("ファイル操作中にエラーが発生しました。", 5000)
        self._set_file_op_buttons_enabled(True) # Re-enable buttons on error

    def _handle_file_op_finished(self, result):
        logger.info(f"File operation finished. Result: {result}")
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        self._set_file_op_buttons_enabled(True)

        status = result.get('status', 'unknown')
        operation_type = result.get('operation_type', 'unknown') # Get operation_type from result

        if status == 'cancelled':
            self.statusBar.showMessage("ファイル操作がキャンセルされました。", 5000)
            return

        errors = result.get('errors', [])
        
        if operation_type == "move":
            moved_count = result.get('moved_count', 0)
            renamed_files = result.get('renamed_files', [])
            
            # Remove successfully moved files from the model
            # This requires careful handling if source_paths were QStandardItems or just paths
            # Assuming self.selected_file_paths was used for move
            # successfully_moved_paths = set(self.selected_file_paths) # Start with all initially selected
            # if errors: # If there were errors, some files might not have moved
                # This part is tricky: we need to know which specific files failed.
                # For now, we assume if errors exist, we might not remove all from view,
                # or rely on a refresh. A more robust way is for worker to return list of successful paths.
                # Let's assume for now that if an error occurs for a file, it's in the error list.
                # A simple approach: if any error, don't remove from view automatically, user might want to retry.
                # Or, only remove those that are NOT associated with an error.
                # For now, let's just show message. Actual removal from view needs more thought.
                # pass


            # Refresh the view for the source folder if files were moved from it
            successfully_moved_src_paths = result.get('successfully_moved_src_paths', [])
            if moved_count > 0 and successfully_moved_src_paths:
                 logger.info(f"Successfully moved {moved_count} files. Updating model.")
                 
                 # Build a path-to-item map for quick lookup
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
                         # This case should ideally not happen if successfully_moved_src_paths
                         # are accurate and were part of the model.
                         logger.warning(f"Moved path {path_to_remove} not found in source model's path_to_item_map for removal.")
                 
                 # Remove items in reverse order of their rows to maintain index validity
                 # It's important that items_to_remove_from_model contains valid QStandardItem instances
                 # that are still part of the source_thumbnail_model.
                 items_to_remove_from_model.sort(key=lambda x: x.row() if x and x.model() == self.source_thumbnail_model else -1, reverse=True)
                 
                 for item_to_remove_instance in items_to_remove_from_model:
                     if item_to_remove_instance and item_to_remove_instance.model() == self.source_thumbnail_model:
                         self.source_thumbnail_model.removeRow(item_to_remove_instance.row())
                     elif item_to_remove_instance:
                         logger.warning(f"Item for path {item_to_remove_instance.data(Qt.ItemDataRole.UserRole)} is no longer in the expected model or is invalid, skipping removal.")
                     # If item_to_remove_instance was None (from path_to_item_map.get()), it's already handled by not being in the list effectively.

                 # Clear selected_file_paths as they have been processed (moved)
                 # Only clear those that were successfully moved.
                 # For simplicity, if an operation was started, we clear the whole list,
                 # assuming user will re-select if some failed.
                 # A more precise way would be to remove only successful paths from selected_file_paths.
                 self.selected_file_paths.clear()
                 self._update_status_bar_info() # Update status bar after model changes
            
            # After a move operation, the current folder view might be stale or show less items.
            # It's not strictly necessary to reload the entire folder view,
            # as items are removed. However, if the move was *within* the current view's subfolders,
            # a refresh of the specific destination in the tree might be desired by user,
            # but that's a more complex UI enhancement. For now, removing items is the main goal.


            if renamed_files:
                # Use the new custom dialog
                dialog = RenamedFilesDialog(renamed_files, self)
                dialog.exec()
            
            if errors:
                QMessageBox.warning(self, "移動エラー", "以下のエラーが発生しました:\n" + "\n".join(errors))
            
            if moved_count > 0:
                # Check if destination is within the current view root
                # Get destination_folder from the result dictionary
                destination_folder_from_result = result.get('destination_folder')
                if not destination_folder_from_result:
                    logger.error("Destination folder not found in operation result for move.")
                    # Fallback or decide how to handle this missing info
                    # For now, we might not be able to perform the relative path check accurately
                    # and will assume it's an external move for message purposes.
                    self.statusBar.showMessage(f"{moved_count}個のファイルを移動しました。", 5000)
                    # Skip the relative path logic if destination_folder is missing
                else:
                    destination_path_obj = Path(destination_folder_from_result)
                    current_root_path_obj = Path(self.current_folder_path) if self.current_folder_path else None
                    
                    is_within_current_root = False
                    if current_root_path_obj: # Only proceed if current_folder_path is set
                        try:
                            # Check if destination_folder is a sub-path of current_folder_path
                            if destination_path_obj == current_root_path_obj or \
                               destination_path_obj.resolve().is_relative_to(current_root_path_obj.resolve()):
                                is_within_current_root = True
                        except Exception as e: # Path.is_relative_to can raise ValueError on Windows for different drives
                            logger.warning(f"Could not determine if destination is relative to current root: {e}")
                            try:
                                common = Path(os.path.commonpath([str(destination_path_obj.resolve()), str(current_root_path_obj.resolve())]))
                                if common == current_root_path_obj.resolve():
                                     is_within_current_root = True
                            except ValueError:
                                 pass

                    if is_within_current_root and current_root_path_obj: # Ensure current_root_path_obj is not None
                        relative_dest_path = os.path.relpath(str(destination_path_obj), str(current_root_path_obj))
                        if relative_dest_path == ".": relative_dest_path = "現在のフォルダ"

                        if moved_count == 1 and successfully_moved_src_paths:
                            moved_filename = os.path.basename(successfully_moved_src_paths[0])
                            msg = f"ファイル「{moved_filename}」は表示中フォルダ内で「{relative_dest_path}」へ移動されました。\n" \
                                  f"ビューから非表示になります。移動先フォルダを選択するか、現在のフォルダを再選択すると確認できます。"
                            QMessageBox.information(self, "ファイル移動完了", msg)
                        else:
                            msg = f"{moved_count}個のファイルは表示中フォルダ内で移動されました。\n" \
                                  f"ビューから非表示になります。移動先フォルダを選択するか、現在のフォルダを再選択すると確認できます。"
                            QMessageBox.information(self, "ファイル移動完了", msg)
                        self.statusBar.showMessage(f"{moved_count}個のファイルを移動しました。", 5000)
                    else:
                        self.statusBar.showMessage(f"{moved_count}個のファイルを移動しました。", 5000)

            elif not errors: # This was 'elif not errors:' which might be too broad if moved_count is 0 but no errors
                 self.statusBar.showMessage("移動するファイルがありませんでした、または処理が完了しました。", 3000)
            # Ensure status bar is updated even if moved_count is 0 and there are errors
            elif errors and moved_count == 0:
                 self.statusBar.showMessage("ファイルの移動に失敗しました。", 3000)


        elif operation_type == "copy":
            copied_count = result.get('copied_count', 0)
            # destination_folder_from_result = result.get('destination_folder') # Also available for copy if needed
            if errors:
                is_within_current_root = False
                try:
                    # Check if destination_folder is a sub-path of current_folder_path
                    # This check is true if destination_folder is current_folder_path or a subdirectory
                    if destination_path_obj == current_root_path_obj or \
                       destination_path_obj.resolve().is_relative_to(current_root_path_obj.resolve()):
                        is_within_current_root = True
                except Exception as e: # Path.is_relative_to can raise ValueError on Windows for different drives
                    logger.warning(f"Could not determine if destination is relative to current root: {e}")
                    # Fallback: check if common path is the current root path
                    try:
                        common = Path(os.path.commonpath([str(destination_path_obj.resolve()), str(current_root_path_obj.resolve())]))
                        if common == current_root_path_obj.resolve():
                             is_within_current_root = True
                    except ValueError: # commonpath can fail if paths are on different drives
                         pass


                if is_within_current_root:
                    relative_dest_path = os.path.relpath(str(destination_path_obj), str(current_root_path_obj))
                    if relative_dest_path == ".": relative_dest_path = "現在のフォルダ"

                    if moved_count == 1 and successfully_moved_src_paths:
                        moved_filename = os.path.basename(successfully_moved_src_paths[0])
                        msg = f"ファイル「{moved_filename}」は表示中フォルダ内で「{relative_dest_path}」へ移動されました。\n" \
                              f"ビューから非表示になります。移動先フォルダを選択するか、現在のフォルダを再選択すると確認できます。"
                        QMessageBox.information(self, "ファイル移動完了", msg)
                    else:
                        msg = f"{moved_count}個のファイルは表示中フォルダ内で移動されました。\n" \
                              f"ビューから非表示になります。移動先フォルダを選択するか、現在のフォルダを再選択すると確認できます。"
                        QMessageBox.information(self, "ファイル移動完了", msg)
                    self.statusBar.showMessage(f"{moved_count}個のファイルを移動しました。", 5000)
                else:
                    self.statusBar.showMessage(f"{moved_count}個のファイルを移動しました。", 5000)

            elif not errors:
                 self.statusBar.showMessage("移動するファイルがありませんでした、または処理が完了しました。", 3000)


        elif operation_type == "copy":
            copied_count = result.get('copied_count', 0)
            if errors:
                QMessageBox.warning(self, "コピーエラー", "以下のエラーが発生しました:\n" + "\n".join(errors))
            
            if copied_count > 0:
                self.statusBar.showMessage(f"{copied_count}個のファイルをコピーしました。", 5000)
                # Specific cleanup for copy_selection_order is now handled below
                # if status is 'completed' and no errors.
            elif not errors:
                self.statusBar.showMessage("コピーするファイルがありませんでした、または処理が完了しました。", 3000)
        
        # General cleanup for completed operations without errors
        if status == 'completed' and not errors:
            self.deselect_all_thumbnails() # Single call to deselect

            if operation_type == "copy": # Specific cleanup for copy mode after deselection
                # Clear selection order data from items after successful copy
                for item_in_order in self.copy_selection_order: # Iterate before clearing
                    if item_in_order.data(SELECTION_ORDER_ROLE) is not None:
                        item_in_order.setData(None, SELECTION_ORDER_ROLE)
                        source_idx = self.source_thumbnail_model.indexFromItem(item_in_order)
                        proxy_idx = self.filter_proxy_model.mapFromSource(source_idx)
                        if proxy_idx.isValid():
                            self.thumbnail_view.update(proxy_idx) # Ensure item repaints
                self.copy_selection_order.clear()
            # For move operations, selected_file_paths is already cleared if successful.
            
            # After successful file operations, check the source folder of the move for empty subdirectories
            if operation_type == "move" and status == 'completed' and not errors:
                # Determine the source folder. This is tricky if files were from multiple subfolders.
                # For simplicity, if self.current_folder_path was the origin of *some* moved files, check it.
                # A more robust approach would be to get the parent directory of each moved file.
                # Let's assume the operation was on files within self.current_folder_path or its direct children.
                
                # Get the source folder from which files were moved.
                # This information is not directly in 'result' for 'move'.
                # We need to infer it. If selected_file_paths contained the moved files,
                # we can take the common parent of these paths.
                # However, selected_file_paths is cleared by this point if successful.
                # We need the source folder path *before* it's cleared or changed.
                # Let's use the `successfully_moved_src_paths` from the result.
                
                source_folders_to_check = set()
                if successfully_moved_src_paths: # successfully_moved_src_paths is available from the result
                    for src_path in successfully_moved_src_paths:
                        parent_dir = os.path.dirname(src_path)
                        if os.path.isdir(parent_dir): # Ensure parent directory still exists
                             source_folders_to_check.add(parent_dir)
                
                # Also consider the folder that was active in the UI, if it was a source
                if self.current_folder_path and os.path.isdir(self.current_folder_path):
                    # Check if any moved file's parent is the current_folder_path
                    # This logic might be redundant if current_folder_path is already in source_folders_to_check
                    # from the successfully_moved_src_paths.
                    # For now, let's add it to be sure, if it's a valid directory.
                    source_folders_to_check.add(self.current_folder_path)


                for folder_to_check in source_folders_to_check:
                    if os.path.isdir(folder_to_check): # Double check it's still a dir
                        logger.info(f"ファイル移動完了後、移動元フォルダ '{folder_to_check}' の空サブフォルダ削除を試みます。")
                        self._try_delete_empty_subfolders(folder_to_check)
                    else:
                        logger.debug(f"ファイル移動完了後、フォルダ '{folder_to_check}' は存在しないかディレクトリではないため、空フォルダチェックをスキップします。")


    def _save_settings(self):
        # Read existing settings first to preserve other values like image_preview_mode
        settings = self._read_app_settings_file() 
        
        # Update the settings MainWindow is responsible for
        settings["last_folder_path"] = self.current_folder_path
        settings["recursive_search"] = self.recursive_search_enabled
        settings["image_preview_mode"] = self.image_preview_mode
        settings["thumbnail_size"] = self.current_thumbnail_size # Ensure this is also saved
        settings[THUMBNAIL_RIGHT_CLICK_ACTION] = self.thumbnail_right_click_action
        settings["sort_key_index"] = self.current_sort_key_index
        settings["sort_order"] = self.current_sort_order.value # Store enum's integer value

        # Write the combined settings back
        self._write_app_settings_file(settings)
        # logger.info(f"設定を保存しました (MainWindow): {APP_SETTINGS_FILE}") # _write_app_settings_file already logs

    def _load_settings(self):
        try:
            if os.path.exists(APP_SETTINGS_FILE):
                with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                last_folder_path = settings.get("last_folder_path")
                if last_folder_path and os.path.isdir(last_folder_path):
                    logger.info(f"前回終了時のフォルダパスを読み込みました: {last_folder_path} (ダイアログ初期位置用)")
                    self.initial_dialog_path = last_folder_path
                    # Do not automatically load the folder view, just set for dialog
                else:
                    if last_folder_path: # Path was in settings but not a valid dir
                         logger.warning(f"保存されたフォルダパスが無効または見つかりません: {last_folder_path}")
                
                recursive_enabled_from_settings = settings.get("recursive_search")
                if isinstance(recursive_enabled_from_settings, bool):
                    # This will trigger the toggled signal if the state changes,
                    # which in turn calls handle_recursive_search_toggled to update
                    # self.recursive_search_enabled and the button text.
                    self.recursive_toggle_button.setChecked(recursive_enabled_from_settings)
                    logger.info(f"再帰検索設定を読み込みました: {'ON' if recursive_enabled_from_settings else 'OFF'}")
                
                # Load sort settings
                loaded_sort_key_index = settings.get("sort_key_index", 0) # Default to filename
                if 0 <= loaded_sort_key_index < self.sort_key_combo.count():
                    self.current_sort_key_index = loaded_sort_key_index
                    self.sort_key_combo.setCurrentIndex(self.current_sort_key_index)
                else:
                    logger.warning(f"保存されたソートキーインデックスが無効: {loaded_sort_key_index}")

                loaded_sort_order_int = settings.get("sort_order", Qt.SortOrder.AscendingOrder.value) # Use .value for default
                self.current_sort_order = Qt.SortOrder(loaded_sort_order_int) # Convert int back to Qt.SortOrder
                
                if self.current_sort_order == Qt.SortOrder.AscendingOrder:
                    self.sort_order_button.setText("昇順 ▲")
                else:
                    self.sort_order_button.setText("降順 ▼")
                # self.sort_order_button.setChecked(self.current_sort_order == Qt.SortOrder.DescendingOrder) # Not needed as button is not checkable

                logger.info(f"ソート設定を読み込みました: Key Index: {self.current_sort_key_index}, Order: {self.current_sort_order}")
                # Apply sort settings after loading them and updating UI elements
                # self._apply_sort_and_filter_update() # Removed from here
            else:
                logger.info(f"設定ファイルが見つかりません ({APP_SETTINGS_FILE})。デフォルト状態で起動します。")
                # Apply default sort settings if no settings file
                # self._apply_sort_and_filter_update() # Removed from here

        except json.JSONDecodeError as e:
            logger.error(f"設定ファイルの読み込み中にJSONデコードエラーが発生しました: {e}", exc_info=True)
        except IOError as e:
            logger.error(f"設定ファイルの読み込み中にIOエラーが発生しました: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"設定の読み込み中に予期せぬエラーが発生しました: {e}", exc_info=True)

    # Removed _debug_button_click_and_call_handler

    def _try_delete_empty_subfolders(self, target_folder_path):
        """
        Attempts to find and delete empty subfolders within the target_folder_path.
        This method is designed to be called internally.
        The actual deletion confirmation (Yes/No) is handled by _handle_send_empty_folders_to_trash.
        """
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
        """
        Handles the actual deletion of a list of pre-identified empty folders.
        Shows confirmation and summary messages.
        parent_folder_path_for_context is the folder that was initially targeted for the scan.
        empty_folders_to_delete is the list of specific empty subfolders found within it.
        """
        logger.debug(f"_handle_send_empty_folders_to_trash called for parent '{parent_folder_path_for_context}' with {len(empty_folders_to_delete)} folders.")

        if not empty_folders_to_delete:
            logger.info("削除対象の空フォルダがありません。")
            return

        confirm_message = "空のサブフォルダが見つかりました。ゴミ箱に移動しますか？\n\n"
        for folder in empty_folders_to_delete:
            confirm_message += f"- {folder}\n"
        
        # Add a reference to the parent folder in the message if needed for clarity, 
        # but the primary request is to simplify the first line.
        # For now, let's keep the parent folder context out of the main question line.
        # confirm_message += f"\n(対象親フォルダ: {parent_folder_path_for_context})" # Optional addition for context

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
        # Iterate over subdirectories non-recursively first
        for entry in os.scandir(parent_dir):
            if entry.is_dir():
                # Recursively check if this subdirectory is empty or contains only empty subdirectories
                if self._is_dir_empty_recursive(entry.path):
                    empty_folders.append(entry.path)
        return empty_folders

    def _is_dir_empty_recursive(self, dir_path):
        try:
            # Attempt to list entries. If this fails (e.g. permission denied),
            # we can't know if it's empty, so treat as non-empty.
            entries = list(os.scandir(dir_path))
        except OSError as e:
            logger.warning(f"Could not scan directory '{dir_path}' due to OSError: {e}. Treating as non-empty for empty folder check.")
            return False # Cannot determine, assume not empty for safety

        if not entries:
            # logger.debug(f"Directory '{dir_path}' has no entries, considered empty by itself.")
            return True # No entries at all (no files, no subdirs)

        for entry in entries:
            if entry.is_file():
                # logger.debug(f"Directory '{dir_path}' contains file '{entry.name}', not empty.")
                return False # Found a file, not empty
            elif entry.is_dir():
                # logger.debug(f"Directory '{dir_path}' contains subdir '{entry.name}', checking recursively.")
                if not self._is_dir_empty_recursive(entry.path):
                    # logger.debug(f"Subdirectory '{entry.path}' is not empty, so '{dir_path}' is not empty.")
                    return False # Found a non-empty subdirectory
        
        # If loop completes, means no files were found, and all subdirectories were recursively empty
        # logger.debug(f"Directory '{dir_path}' contains no files and all subdirs are empty, considered empty.")
        return True

    def closeEvent(self, event: QCloseEvent): # Add type hint for event
        logger.info("アプリケーション終了処理を開始します...")
        self._save_settings()
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
            # Wait a bit for the thread to acknowledge and finish
            # Note: This might block UI if wait is too long.
            # Consider if a more sophisticated shutdown is needed for file_operations.
            # For now, a short wait.
            if not self.file_operations._thread.wait(1000):
                 logger.warning("ファイル操作スレッドの終了待機がタイムアウトしました。")


        logger.info("アプリケーションを終了します。")
        super().closeEvent(event)

    def _show_thumbnail_context_menu(self, pos):
        proxy_index = self.thumbnail_view.indexAt(pos)
        if not proxy_index.isValid():
            return

        if self.thumbnail_right_click_action == RIGHT_CLICK_ACTION_METADATA:
            self.handle_metadata_requested(proxy_index)
        elif self.thumbnail_right_click_action == RIGHT_CLICK_ACTION_MENU:
            menu = QMenu(self)
            
            metadata_action = QAction("メタデータを表示", self)
            metadata_action.triggered.connect(lambda: self.handle_metadata_requested(proxy_index))
            menu.addAction(metadata_action)

            open_location_action = QAction("ファイルの場所を開く", self)
            open_location_action.triggered.connect(lambda: self._open_file_location_for_item(proxy_index))
            menu.addAction(open_location_action)
            
            menu.exec(self.thumbnail_view.viewport().mapToGlobal(pos))
        else:
            logger.warning(f"不明なサムネイル右クリック動作設定: {self.thumbnail_right_click_action}")
            # フォールバックとしてメタデータを表示するなどの処理も検討可能
            self.handle_metadata_requested(proxy_index)

    def _open_file_location_for_item(self, proxy_index):
        if not proxy_index.isValid():
            logger.warning("ファイルの場所を開く操作が、無効なインデックスで呼び出されました。")
            return

        source_index = self.filter_proxy_model.mapToSource(proxy_index)
        item = self.source_thumbnail_model.itemFromIndex(source_index)

        if not item:
            logger.warning(f"ファイルの場所を開く操作: インデックスからアイテムを取得できませんでした (proxy: {proxy_index.row()},{proxy_index.column()}; source: {source_index.row()},{source_index.column()}).")
            return

        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            logger.warning("ファイルの場所を開く操作: アイテムにファイルパスが関連付けられていません。")
            QMessageBox.warning(self, "エラー", "アイテムにファイルパスが関連付けられていません。")
            return

        dir_path = os.path.dirname(file_path)
        if not os.path.isdir(dir_path):
            logger.warning(f"ファイルの場所を開く操作: ディレクトリ '{dir_path}' が見つかりません (元ファイル: {file_path})。")
            QMessageBox.warning(self, "エラー", f"ディレクトリ '{dir_path}' が見つかりません。")
            return
        
        try:
            logger.info(f"エクスプローラで '{dir_path}' を開きます。")
            os.startfile(dir_path)
        except AttributeError:
            logger.error("os.startfile が現在のプラットフォームでサポートされていません。")
            QMessageBox.critical(self, "エラー", "このプラットフォームではファイルの場所を開く機能はサポートされていません。")
        except FileNotFoundError: # Should be caught by os.path.isdir, but as a safeguard
            logger.error(f"os.startfile でディレクトリ '{dir_path}' が見つかりませんでした。")
            QMessageBox.critical(self, "エラー", f"ディレクトリ '{dir_path}' が見つかりませんでした。")
        except Exception as e:
            logger.error(f"ディレクトリ '{dir_path}' を開く際に予期せぬエラーが発生しました: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"ディレクトリを開く際にエラーが発生しました:\n{e}")
