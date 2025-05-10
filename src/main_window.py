import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeView, QSplitter, QFrame, QFileDialog, QSlider, QListView, # Added QListView
    QAbstractItemView, QLineEdit, QMenu, QRadioButton, QButtonGroup, QMessageBox, QProgressDialog # Added QProgressDialog
)
from PyQt6.QtGui import QFileSystemModel, QPixmap, QIcon, QStandardItemModel, QStandardItem, QAction
from PyQt6.QtCore import Qt, QDir, QSize, QTimer, QDirIterator, QVariant, QSortFilterProxyModel
import os # For path operations
from pathlib import Path # For path operations
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle

from .thumbnail_loader import ThumbnailLoaderThread
from .thumbnail_delegate import ThumbnailDelegate
from .metadata_filter_proxy_model import MetadataFilterProxyModel
from .image_metadata_dialog import ImageMetadataDialog
from .thumbnail_list_view import ToggleSelectionListView # Import custom ListView
from .file_operations import FileOperations # Import FileOperations
from .renamed_files_dialog import RenamedFilesDialog # Import new dialog

# PillowのImageオブジェクトをQImageに変換するために必要
import logging # Add logging import

# PIL.ImageQt が Pillow 9.0.0 以降で推奨される方法
try:
    from PIL import ImageQt
except ImportError:
    logging.error("Pillow (PIL) の ImageQt モジュールが見つかりません。pip install Pillow --upgrade を試してください。")
    ImageQt = None

logger = logging.getLogger(__name__)

from .constants import METADATA_ROLE, SELECTION_ORDER_ROLE # Import from constants

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

        size_control_layout = QHBoxLayout()
        self.size_label = QLabel(f"サイズ: {self.current_thumbnail_size}px")
        size_control_layout.addWidget(self.size_label)
        
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(0)
        self.size_slider.setMaximum(len(self.available_sizes) - 1)
        self.size_slider.setValue(self.available_sizes.index(self.current_thumbnail_size))
        self.size_slider.setTickInterval(1)
        self.size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.size_slider.valueChanged.connect(self.handle_slider_value_changed)
        self.size_slider.sliderReleased.connect(self.trigger_thumbnail_reload)
        size_control_layout.addWidget(self.size_slider)
        left_layout.addLayout(size_control_layout)

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
        self.thumbnail_view.customContextMenuRequested.connect(self.show_thumbnail_context_menu)
        
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

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "画像フォルダを選択", "")
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

    def on_folder_tree_clicked(self, index):
        path = self.file_system_model.filePath(index)
        if self.file_system_model.isDir(index):
            logger.info(f"フォルダがクリックされました: {path}")
            self.current_folder_path = path
            self.load_thumbnails_from_folder(path)
        else:
            logger.debug(f"ファイルがクリックされました: {path}")

    def load_thumbnails_from_folder(self, folder_path):
        if ImageQt is None: # Ensure ImageQt is available before loading
            self.statusBar.showMessage("ImageQtモジュールが見つかりません。処理を中止します。", 5000)
            logger.error("ImageQt module not found. Cannot load thumbnails.")
            return

        logger.info(f"{folder_path} からサムネイルを読み込みます。")
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
            self.size_slider.setEnabled(False) 
            self.folder_tree_view.setEnabled(False)
            self.recursive_toggle_button.setEnabled(False)
            self.deselect_all_button.setEnabled(False)
            self.select_all_button.setEnabled(False) # Disable during load
            self.positive_prompt_filter_edit.setEnabled(False)
            self.negative_prompt_filter_edit.setEnabled(False)
            self.generation_info_filter_edit.setEnabled(False)
            self.and_radio_button.setEnabled(False)
            self.or_radio_button.setEnabled(False)

            self.source_thumbnail_model.clear() # Clear the source model
            self.selected_file_paths.clear() # Clear selection list
            self.metadata_cache.clear() # Clear metadata cache as well
            # self.thumbnail_view.clearSelection() # Model clear should handle this

            self.thumbnail_view.setIconSize(QSize(self.current_thumbnail_size, self.current_thumbnail_size))
            self.thumbnail_view.setGridSize(QSize(self.current_thumbnail_size + 10, self.current_thumbnail_size + 10))

            placeholder_pixmap = QPixmap(self.current_thumbnail_size, self.current_thumbnail_size)
            placeholder_pixmap.fill(Qt.GlobalColor.transparent)
            placeholder_icon = QIcon(placeholder_pixmap)

            for f_path in image_files:
                item = QStandardItem()
                item.setIcon(placeholder_icon)
                item.setText(QDir().toNativeSeparators(f_path).split(QDir.separator())[-1])
                item.setEditable(False)
                item.setData(f_path, Qt.ItemDataRole.UserRole) # Store file path
                # Metadata will be added in update_thumbnail_item via METADATA_ROLE
                self.source_thumbnail_model.appendRow(item)

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

        self.thumbnail_loader_thread = ThumbnailLoaderThread(image_files, self.current_thumbnail_size)
        self.thumbnail_loader_thread.thumbnailLoaded.connect(self.update_thumbnail_item)
        self.thumbnail_loader_thread.progressUpdated.connect(self.update_progress_bar)
        self.thumbnail_loader_thread.finished.connect(self.on_thumbnail_loading_finished)
        if image_files:
            self.statusBar.showMessage(f"サムネイル読み込み中... 0/{len(image_files)}")
            self.thumbnail_loader_thread.start()
        else:
            self.statusBar.showMessage("フォルダに画像がありません", 5000)
            self.is_loading_thumbnails = False # Reset flag if no files
            self.size_slider.setEnabled(True)
            self.folder_tree_view.setEnabled(True)
            self.recursive_toggle_button.setEnabled(True)
            self.deselect_all_button.setEnabled(True)
            self.select_all_button.setEnabled(True) # Enable after load
            self.positive_prompt_filter_edit.setEnabled(True)
            self.negative_prompt_filter_edit.setEnabled(True)
            self.generation_info_filter_edit.setEnabled(True)


    def handle_slider_value_changed(self, value):
        preview_size = self.available_sizes[value]
        self.size_label.setText(f"サイズ: {preview_size}px")

    def handle_recursive_search_toggled(self, checked):
        self.recursive_search_enabled = checked
        self.recursive_toggle_button.setText(f"サブフォルダ検索: {'ON' if checked else 'OFF'}")
        logger.info(f"再帰検索設定変更: {'ON' if checked else 'OFF'}. 次回フォルダ読み込み時に適用されます。")

    def trigger_thumbnail_reload(self):
        if self.is_loading_thumbnails:
            logger.info("現在サムネイル読み込み中のため、サイズ変更はスキップされました。")
            current_value_index = self.available_sizes.index(self.current_thumbnail_size)
            if self.size_slider.value() != current_value_index:
                self.size_slider.setValue(current_value_index)
                self.size_label.setText(f"サイズ: {self.current_thumbnail_size}px")
            return

        slider_selected_index = self.size_slider.value()
        new_selected_size = self.available_sizes[slider_selected_index]

        if new_selected_size != self.current_thumbnail_size:
            self.current_thumbnail_size = new_selected_size
            if self.current_folder_path:
                logger.info(f"サムネイルサイズ変更適用: {self.current_thumbnail_size}px. 再読み込み開始...")
                self.load_thumbnails_from_folder(self.current_folder_path)
            else:
                logger.info("再読み込みするフォルダが選択されていません。")
        else:
            self.size_label.setText(f"サイズ: {self.current_thumbnail_size}px")
            logger.info("選択されたサイズは現在のサイズと同じため、再読み込みは行いません。")

    def update_progress_bar(self, processed_count, total_files):
        self.statusBar.showMessage(f"サムネイル読み込み中... {processed_count}/{total_files}")

    def update_thumbnail_item(self, file_path, q_image, metadata): # Added metadata parameter
        if ImageQt is None: return

        pixmap = None
        if q_image: # q_image can be None if loading failed in thread
            pixmap = QPixmap.fromImage(q_image)
        
        # Iterate over the source model to find the item
        for row in range(self.source_thumbnail_model.rowCount()):
            item = self.source_thumbnail_model.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == file_path:
                if pixmap:
                    # logger.debug(f"update_thumbnail_item for {file_path}: q_image isNull={q_image.isNull()}, q_image.size={q_image.size() if q_image else 'N/A'}")
                    # logger.debug(f"update_thumbnail_item for {file_path}: pixmap isNull={pixmap.isNull()}, pixmap.size={pixmap.size() if pixmap else 'N/A'}")
                    temp_icon = QIcon(pixmap)
                    # logger.debug(f"update_thumbnail_item for {file_path}: temp_icon isNull={temp_icon.isNull()}, availableSizes={temp_icon.availableSizes()}, actualSize for 128x128={temp_icon.actualSize(QSize(128,128)) if not temp_icon.isNull() else 'N/A'}")
                    # Attempt to keep a reference to the icon object by storing it in a custom role
                    # This might prevent the QIcon from being garbage collected if setIcon doesn't take ownership strongly enough.
                    # item.setData(temp_icon, Qt.ItemDataRole.UserRole + 100) # Custom role for icon reference - This was a debug step, removing.
                    item.setIcon(temp_icon)
                else:
                    logger.warning(f"update_thumbnail_item for {file_path}: pixmap is None (q_image was None or conversion failed). Icon not set.")
                
                # Store metadata in cache and item
                self.metadata_cache[file_path] = metadata
                item.setData(metadata, METADATA_ROLE) # Store metadata dict directly
                
                # # --- Added Debug Log ---
                # normalized_image_path_log = file_path.replace("\\", "/")
                # target_file_for_debug_log_raw = r"G:\test\00005-4187066497.jpg"
                # normalized_target_path_log = target_file_for_debug_log_raw.replace("\\", "/")
                # if normalized_image_path_log == normalized_target_path_log:
                    # logger.info(f"DEBUG_TARGET_MAIN_WINDOW_UPDATE: Metadata set for item {file_path}: {metadata}")
                # # --- End Debug Log ---
                break

    def on_thumbnail_loading_finished(self):
        logger.info("サムネイルの非同期読み込みが完了しました。")
        self.statusBar.showMessage("サムネイル読み込み完了", 5000)
        self.is_loading_thumbnails = False
        self.size_slider.setEnabled(True) 
        self.folder_tree_view.setEnabled(True)
        self.recursive_toggle_button.setEnabled(True)
        self.deselect_all_button.setEnabled(True)
        self.select_all_button.setEnabled(True)
        self.positive_prompt_filter_edit.setEnabled(True)
        self.negative_prompt_filter_edit.setEnabled(True)
        self.generation_info_filter_edit.setEnabled(True)
        self.and_radio_button.setEnabled(True)
        self.or_radio_button.setEnabled(True)

        if self.filter_proxy_model: # Apply initial filter if model exists
            self.apply_filters(preserve_selection=True) # Preserve selection after loading

        if self.thumbnail_loader_thread:
            self.thumbnail_loader_thread.deleteLater()
            self.thumbnail_loader_thread = None

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


    def select_all_thumbnails(self):
        # Operates on the view, which uses the (proxy) model
        if self.thumbnail_view.model() and self.thumbnail_view.model().rowCount() > 0:
            self.thumbnail_view.selectAll()
            logger.info("すべての表示中サムネイルを選択しました。")
        else:
            logger.info("選択対象のサムネイルがありません。")

    def deselect_all_thumbnails(self):
        self.thumbnail_view.clearSelection()
        logger.info("すべてのサムネイルの選択を解除しました。")

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

    def show_thumbnail_context_menu(self, position):
        proxy_index = self.thumbnail_view.indexAt(position)
        if not proxy_index.isValid():
            return

        source_index = self.filter_proxy_model.mapToSource(proxy_index)
        item = self.source_thumbnail_model.itemFromIndex(source_index)
        if not item:
            return

        file_path = item.data(Qt.ItemDataRole.UserRole)
        
        data_from_item = item.data(METADATA_ROLE)
        final_metadata_to_show = {} # Default to empty dict

        if isinstance(data_from_item, dict):
            final_metadata_to_show = data_from_item
            logger.debug(f"DEBUG_CTX_MENU: Metadata from item role for {file_path} is a dict: {final_metadata_to_show}")
        else:
            logger.debug(f"DEBUG_CTX_MENU: Metadata from item role for {file_path} is NOT a dict (Type: {type(data_from_item)}). Trying cache.")
            cached_metadata = self.metadata_cache.get(file_path)
            if isinstance(cached_metadata, dict):
                final_metadata_to_show = cached_metadata
                logger.debug(f"DEBUG_CTX_MENU: Metadata from cache for {file_path} is a dict: {final_metadata_to_show}")
            else:
                logger.warning(f"DEBUG_CTX_MENU: Metadata for {file_path} not found or not a dict in cache either. Type: {type(cached_metadata)}. Using empty dict.")
        
        # Ensure final_metadata_to_show is always a dict
        if not isinstance(final_metadata_to_show, dict):
            logger.error(f"DEBUG_CTX_MENU: CRITICAL - final_metadata_to_show is NOT a dict for {file_path}! Type: {type(final_metadata_to_show)}. Forcing empty dict.")
            final_metadata_to_show = {}

        # Log what is about to be passed to the dialog for the target file
        # # normalized_image_path_log_ctx = file_path.replace("\\", "/")
        # # target_file_for_debug_log_raw_ctx = r"G:\test\00005-4187066497.jpg"
        # # normalized_target_path_log_ctx = target_file_for_debug_log_raw_ctx.replace("\\", "/")
        # # if normalized_image_path_log_ctx == normalized_target_path_log_ctx:
             # # logger.info(f"DEBUG_TARGET_CTX_MENU: About to connect lambda with metadata for {file_path}: {final_metadata_to_show}")
        
        menu = QMenu(self)
        show_metadata_action = QAction("メタデータを表示", self)
        # Use default argument in lambda to capture the current value of final_metadata_to_show
        # Also pass file_path for logging within show_metadata_dialog_for_item
        show_metadata_action.triggered.connect(
            lambda checked=False, bound_metadata=final_metadata_to_show, fp=file_path: self.show_metadata_dialog_for_item(bound_metadata, fp)
        )
        menu.addAction(show_metadata_action)
        
        menu.exec(self.thumbnail_view.viewport().mapToGlobal(position))

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
            self.metadata_dialog_instance = ImageMetadataDialog(metadata_dict, self, item_file_path_for_debug) # Pass file path for logging
            self.metadata_dialog_instance.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            # Connect the finished signal to a slot that clears the instance variable
            self.metadata_dialog_instance.finished.connect(self._on_metadata_dialog_finished)
            self.metadata_dialog_instance.show()
        else:
            # If instance is not None, it means it's already open. Update and show.
            self.metadata_dialog_instance.update_metadata(metadata_dict, item_file_path_for_debug) # Pass file path for logging
            self.metadata_dialog_instance.show() # Ensure it's visible
        
        self.metadata_dialog_instance.raise_()
        self.metadata_dialog_instance.activateWindow()

    def _on_metadata_dialog_finished(self):
        # Slot to be called when the metadata dialog is closed.
        # Check if the sender is our dialog instance before nullifying.
        # This check is important if multiple dialogs could potentially connect to this slot.
        if self.sender() == self.metadata_dialog_instance:
            self.metadata_dialog_instance = None
            # logger.debug("Metadata dialog closed, instance reference cleared.")

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
        # self.statusBar.showMessage(f"処理中: {processed_count}/{total_count} ファイル...", 0) # ProgressDialog shows this
        if self.progress_dialog: # Check if the dialog still exists
            self.progress_dialog.setMaximum(total_count) # Ensure total is up-to-date
            self.progress_dialog.setValue(processed_count)
            # QProgressDialog's label text can be set, or it might auto-update based on its properties.
            # Explicitly setting it ensures our desired format.
            self.progress_dialog.setLabelText(f"処理中: {processed_count}/{total_count} ファイル...")
        else:
            logger.debug(f"Progress update ({processed_count}/{total_count}) received but progress_dialog is None.")


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
                 items_to_remove_from_model = []
                 for path_to_remove in successfully_moved_src_paths:
                     for row in range(self.source_thumbnail_model.rowCount()):
                         item = self.source_thumbnail_model.item(row)
                         if item and item.data(Qt.ItemDataRole.UserRole) == path_to_remove:
                             items_to_remove_from_model.append(item)
                             break # Found item for this path, move to next path
                 
                 # Remove items in reverse order of their rows to maintain index validity
                 items_to_remove_from_model.sort(key=lambda x: x.row(), reverse=True)
                 for item in items_to_remove_from_model:
                     self.source_thumbnail_model.removeRow(item.row())
                 
                 # Clear selected_file_paths as they have been processed (moved)
                 # Only clear those that were successfully moved.
                 # For simplicity, if an operation was started, we clear the whole list,
                 # assuming user will re-select if some failed.
                 # A more precise way would be to remove only successful paths from selected_file_paths.
                 self.selected_file_paths.clear()


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
                # Clear selection order data from items after successful copy
                for item in self.copy_selection_order: # Iterate before clearing
                    if item.data(SELECTION_ORDER_ROLE) is not None:
                        item.setData(None, SELECTION_ORDER_ROLE)
                        source_idx = self.source_thumbnail_model.indexFromItem(item)
                        proxy_idx = self.filter_proxy_model.mapFromSource(source_idx)
                        if proxy_idx.isValid():
                            self.thumbnail_view.update(proxy_idx) # Ensure item repaints
                self.copy_selection_order.clear()
                self.deselect_all_thumbnails() 
            elif not errors:
                self.statusBar.showMessage("コピーするファイルがありませんでした、または処理が完了しました。", 3000)
        
        # General cleanup for completed operations without errors,
        # but specific copy mode cleanup is now handled within its block.
        if status == 'completed' and not errors:
            if not self.is_copy_mode: # If not in copy mode (e.g. after a move)
                 self.deselect_all_thumbnails()
            # If it was a copy operation, selection and order list are already cleared above.
            # If it was a move operation, selected_file_paths is cleared if successful.
            # self.deselect_all_thumbnails() was called in copy block, ensure it's called for move too if needed.
            # The current logic for move already clears selected_file_paths and removes items from model.
            # A general deselect_all_thumbnails() here might be redundant or could be simplified.
            # For now, let's ensure it's called if not in copy mode.
            # If we are still in copy mode after a copy, deselect_all_thumbnails() will trigger
            # handle_thumbnail_selection_changed, which should correctly handle an empty selection.
            pass # The common cleanup logic below might be sufficient or need adjustment.

        # Final common deselection if operation was completed without error
        if status == 'completed' and not errors:
             self.deselect_all_thumbnails()
