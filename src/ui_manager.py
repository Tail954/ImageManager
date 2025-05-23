# src/ui_manager.py
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeView,
    QSplitter, QFrame, QLineEdit, QRadioButton, QButtonGroup, QListView,
    QAbstractItemView
)
from PyQt6.QtGui import QFileSystemModel, QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt, QSize, QDir, QItemSelection, QItemSelectionModel, QModelIndex

from .thumbnail_list_view import ToggleSelectionListView
from .thumbnail_delegate import ThumbnailDelegate
from .metadata_filter_proxy_model import MetadataFilterProxyModel
from .constants import SELECTION_ORDER_ROLE # SELECTION_ORDER_ROLE をインポート

logger = logging.getLogger(__name__)

class UIManager:
    def __init__(self, main_window):
        self.mw = main_window # MainWindowへの参照

        # UI要素への参照を保持
        self.folder_select_button = None
        self.select_all_button = None
        self.deselect_all_button = None
        self.recursive_toggle_button = None
        self.sort_button_group = None
        self.sort_filename_asc_button = None
        self.sort_filename_desc_button = None
        self.sort_date_asc_button = None
        self.sort_date_desc_button = None
        self.sort_load_order_button = None # ★★★ 追加: 読み込み順ソートボタン ★★★
        self.and_radio_button = None
        self.or_radio_button = None
        self.search_mode_button_group = None
        self.positive_prompt_filter_edit = None
        self.negative_prompt_filter_edit = None
        self.generation_info_filter_edit = None
        self.apply_filter_button = None
        self.move_files_button = None
        self.copy_mode_button = None
        self.copy_files_button = None
        self.folder_tree_view = None
        self.file_system_model = None
        self.thumbnail_view = None
        self.thumbnail_delegate = None
        self.source_thumbnail_model = None
        self.filter_proxy_model = None
        self.left_panel_widget_ref = None # 左パネルへの参照を保持
        self.left_panel_overlay_widget = None # 左パネル専用オーバーレイ
        self.splitter = None # スプリッターへの参照を追加

    def setup_ui(self):
        # Menu Bar (MainWindow側で _create_menu_bar を呼び出す)
        self.mw._create_menu_bar()

        # Status bar
        self.mw.statusBar = self.mw.statusBar()

        # Central widget
        central_widget = QWidget()
        self.mw.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)

        # Splitter for resizable panels
        self.splitter = QSplitter(Qt.Orientation.Horizontal) # self.splitter に代入

        # Left panel (参照を保持)
        self.left_panel_widget_ref = self._create_left_panel()
        # --- ★ 左パネルの最大幅を設定 ---
        # この値はUIの見た目に応じて調整してください
        self.left_panel_widget_ref.setMaximumWidth(350) 
        self.splitter.addWidget(self.left_panel_widget_ref)

        # 左パネル用オーバーレイウィジェットの作成
        self.left_panel_overlay_widget = QWidget(self.left_panel_widget_ref) # 親を左パネルに
        self.left_panel_overlay_widget.setObjectName("leftPanelOverlayWidget")
        self.left_panel_overlay_widget.setStyleSheet("QWidget#leftPanelOverlayWidget { background-color: rgba(0, 0, 0, 70); }")
        self.left_panel_overlay_widget.hide() # 初期状態は非表示
        # サイズと位置は set_ui_locked で調整

        # ファイル操作ボタンの初期状態設定 (コピーモードに応じて)
        self.set_file_op_buttons_enabled_ui(True)

        # Right panel (Thumbnail view)
        right_panel = self._create_right_panel()
        self.splitter.addWidget(right_panel)

        self.splitter.setSizes([300, 900]) # 初期サイズ
        main_layout.addWidget(self.splitter)
    def _create_left_panel(self):
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.folder_select_button = QPushButton("フォルダを選択...")
        self.folder_select_button.clicked.connect(self.mw.select_folder)
        left_layout.addWidget(self.folder_select_button)

        selection_button_layout = QHBoxLayout()
        self.select_all_button = QPushButton("全選択")
        self.select_all_button.clicked.connect(self.mw.select_all_thumbnails)
        selection_button_layout.addWidget(self.select_all_button)

        self.deselect_all_button = QPushButton("全選択解除")
        self.deselect_all_button.clicked.connect(self.mw.deselect_all_thumbnails)
        selection_button_layout.addWidget(self.deselect_all_button)

        self.recursive_toggle_button = QPushButton("サブフォルダ検索: ON")
        self.recursive_toggle_button.setCheckable(True)
        self.recursive_toggle_button.setChecked(self.mw.recursive_search_enabled)
        self.recursive_toggle_button.toggled.connect(self.mw.handle_recursive_search_toggled)
        left_layout.addWidget(self.recursive_toggle_button)

        sort_options_group_box = self._create_sort_options_ui()
        left_layout.addWidget(sort_options_group_box)

        filter_group_box = self._create_filter_ui()
        left_layout.addWidget(filter_group_box)

        file_op_group_box = self._create_file_operations_ui(selection_button_layout)
        left_layout.addWidget(file_op_group_box)

        self.folder_tree_view = QTreeView()
        self.folder_tree_view.setHeaderHidden(True)
        self.file_system_model = QFileSystemModel()
        self.file_system_model.setNameFilters(["*.png", "*.jpg", "*.jpeg", "*.webp"])
        self.file_system_model.setNameFilterDisables(False)
        self.folder_tree_view.setModel(self.file_system_model)
        for i in range(1, self.file_system_model.columnCount()):
            self.folder_tree_view.hideColumn(i)
        left_layout.addWidget(self.folder_tree_view)
        self.folder_tree_view.clicked.connect(self.mw.on_folder_tree_clicked)

        return left_panel

    def _create_sort_options_ui(self):
        sort_options_group_box = QFrame()
        sort_options_group_box.setFrameShape(QFrame.Shape.StyledPanel)
        sort_options_layout = QVBoxLayout(sort_options_group_box)
        sort_options_layout.setContentsMargins(5,5,5,5)
        sort_options_layout.addWidget(QLabel("ソート:"))

        self.sort_button_group = QButtonGroup(self.mw)
        self.sort_button_group.setExclusive(True)

        buttons_map = {
            0: ("ファイル名 昇順", "sort_filename_asc_button"),
            1: ("ファイル名 降順", "sort_filename_desc_button"),
            2: ("更新日時 昇順", "sort_date_asc_button"),
            3: ("更新日時 降順", "sort_date_desc_button"),
            4: ("読み込み順", "sort_load_order_button"), # ★★★ 追加 ★★★
        }
        
        row1_layout = QHBoxLayout()
        setattr(self, buttons_map[0][1], QPushButton(self.mw.sort_criteria_map[0]["caption"]))
        getattr(self, buttons_map[0][1]).setCheckable(True)
        self.sort_button_group.addButton(getattr(self, buttons_map[0][1]), 0)
        row1_layout.addWidget(getattr(self, buttons_map[0][1]))

        setattr(self, buttons_map[1][1], QPushButton(self.mw.sort_criteria_map[1]["caption"]))
        getattr(self, buttons_map[1][1]).setCheckable(True)
        self.sort_button_group.addButton(getattr(self, buttons_map[1][1]), 1)
        row1_layout.addWidget(getattr(self, buttons_map[1][1]))
        sort_options_layout.addLayout(row1_layout)

        row2_layout = QHBoxLayout()
        setattr(self, buttons_map[2][1], QPushButton(self.mw.sort_criteria_map[2]["caption"]))
        getattr(self, buttons_map[2][1]).setCheckable(True)
        self.sort_button_group.addButton(getattr(self, buttons_map[2][1]), 2)
        row2_layout.addWidget(getattr(self, buttons_map[2][1]))

        setattr(self, buttons_map[3][1], QPushButton(self.mw.sort_criteria_map[3]["caption"]))
        getattr(self, buttons_map[3][1]).setCheckable(True)
        self.sort_button_group.addButton(getattr(self, buttons_map[3][1]), 3)
        row2_layout.addWidget(getattr(self, buttons_map[3][1]))
        sort_options_layout.addLayout(row2_layout)

        # ★★★ 追加: 読み込み順ボタンを新しい行に追加 ★★★
        row3_layout = QHBoxLayout()
        setattr(self, buttons_map[4][1], QPushButton(self.mw.sort_criteria_map[4]["caption"]))
        getattr(self, buttons_map[4][1]).setCheckable(True)
        self.sort_button_group.addButton(getattr(self, buttons_map[4][1]), 4)
        row3_layout.addWidget(getattr(self, buttons_map[4][1]))
        sort_options_layout.addLayout(row3_layout)
        self.sort_button_group.idClicked.connect(self.mw._apply_sort_from_toggle_button)
        return sort_options_group_box

    def _create_filter_ui(self):
        filter_group_box = QFrame()
        filter_group_box.setFrameShape(QFrame.Shape.StyledPanel)
        filter_layout = QVBoxLayout(filter_group_box)
        filter_layout.setContentsMargins(5,5,5,5)
        filter_layout.addWidget(QLabel("フィルター (カンマ区切りで複数ワード):"))

        search_mode_layout = QHBoxLayout()
        search_mode_layout.addWidget(QLabel("検索条件:"))
        self.and_radio_button = QRadioButton("AND検索"); self.and_radio_button.setChecked(True)
        self.or_radio_button = QRadioButton("OR検索")
        search_mode_layout.addWidget(self.and_radio_button); search_mode_layout.addWidget(self.or_radio_button)
        self.search_mode_button_group = QButtonGroup(self.mw)
        self.search_mode_button_group.addButton(self.and_radio_button); self.search_mode_button_group.addButton(self.or_radio_button)
        filter_layout.addLayout(search_mode_layout)

        self.positive_prompt_filter_edit = QLineEdit(placeholderText="Positive Prompt を含む...")
        self.positive_prompt_filter_edit.returnPressed.connect(lambda: self.mw.apply_filters(preserve_selection=True))
        filter_layout.addWidget(self.positive_prompt_filter_edit)

        self.negative_prompt_filter_edit = QLineEdit(placeholderText="Negative Prompt を含む...")
        self.negative_prompt_filter_edit.returnPressed.connect(lambda: self.mw.apply_filters(preserve_selection=True))
        filter_layout.addWidget(self.negative_prompt_filter_edit)

        self.generation_info_filter_edit = QLineEdit(placeholderText="Generation Info を含む...")
        self.generation_info_filter_edit.returnPressed.connect(lambda: self.mw.apply_filters(preserve_selection=True))
        filter_layout.addWidget(self.generation_info_filter_edit)

        self.apply_filter_button = QPushButton("フィルタ適用")
        self.apply_filter_button.clicked.connect(lambda: self.mw.apply_filters(preserve_selection=True))
        filter_layout.addWidget(self.apply_filter_button)
        return filter_group_box

    def _create_file_operations_ui(self, selection_button_layout):
        file_op_group_box = QFrame()
        file_op_group_box.setFrameShape(QFrame.Shape.StyledPanel)
        file_op_layout = QVBoxLayout(file_op_group_box)
        file_op_layout.setContentsMargins(5,5,5,5)
        file_op_layout.addWidget(QLabel("ファイル操作:"))
        file_op_layout.addLayout(selection_button_layout)

        self.move_files_button = QPushButton("ファイルを移動")
        self.move_files_button.clicked.connect(self.mw.file_operation_manager._handle_move_files_button_clicked)
        file_op_layout.addWidget(self.move_files_button)

        self.copy_mode_button = QPushButton("Copy Mode: OFF")
        self.copy_mode_button.setCheckable(True)
        self.copy_mode_button.toggled.connect(self.mw.file_operation_manager._handle_copy_mode_toggled)
        file_op_layout.addWidget(self.copy_mode_button)

        self.copy_files_button = QPushButton("ファイルをコピー")
        self.copy_files_button.clicked.connect(self.mw.file_operation_manager._handle_copy_files_button_clicked)
        self.copy_files_button.setEnabled(False)
        file_op_layout.addWidget(self.copy_files_button)
        return file_op_group_box

    def _create_right_panel(self):
        self.thumbnail_view = ToggleSelectionListView()
        self.thumbnail_view.setViewMode(ToggleSelectionListView.ViewMode.IconMode)
        self.thumbnail_view.setResizeMode(ToggleSelectionListView.ResizeMode.Adjust)
        self.thumbnail_view.setMovement(ToggleSelectionListView.Movement.Static)
        self.thumbnail_view.setSpacing(10)
        self.thumbnail_view.setIconSize(QSize(self.mw.current_thumbnail_size, self.mw.current_thumbnail_size))
        self.thumbnail_view.setGridSize(QSize(self.mw.current_thumbnail_size + 10, self.mw.current_thumbnail_size + 10))
        self.thumbnail_view.setUniformItemSizes(True)
        self.thumbnail_view.setLayoutMode(QListView.LayoutMode.Batched)
        self.thumbnail_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.thumbnail_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.thumbnail_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumbnail_view.customContextMenuRequested.connect(self.mw._show_thumbnail_context_menu)
        self.thumbnail_view.item_double_clicked.connect(self.mw.dialog_manager.open_full_image_dialog)

        self.thumbnail_delegate = ThumbnailDelegate(self.thumbnail_view)
        self.thumbnail_view.setItemDelegate(self.thumbnail_delegate)
        self.thumbnail_view.setStyleSheet("QListView::item:selected {border: 3px solid orange;} QListView::item {border: none;}")

        self.source_thumbnail_model = QStandardItemModel(self.mw)
        self.filter_proxy_model = MetadataFilterProxyModel(self.mw)
        self.filter_proxy_model.setSourceModel(self.source_thumbnail_model)
        self.thumbnail_view.setModel(self.filter_proxy_model)
        self.thumbnail_view.selectionModel().selectionChanged.connect(self.mw.handle_thumbnail_selection_changed)
        return self.thumbnail_view

    def update_recursive_button_text(self, checked):
        if self.recursive_toggle_button:
            self.recursive_toggle_button.setText(f"サブフォルダ検索: {'ON' if checked else 'OFF'}")

    def update_copy_mode_button_text(self, checked):
        if self.copy_mode_button:
            self.copy_mode_button.setText(f"Copy Mode: {'ON' if checked else 'OFF'}")

    def set_sort_buttons_enabled(self, enabled: bool):
        """ソート関連のボタン群の有効/無効を切り替える。"""
        if self.sort_button_group:
            for button in self.sort_button_group.buttons():
                button.setEnabled(enabled)
        # logger.debug(f"Sort buttons enabled state set to: {enabled}")

    def set_ui_locked(self, locked: bool):
        """指定された状態に基づいて左パネルUIをオーバーレイでロック/アンロックする。
        サムネイル読み込みなど、比較的時間がかかる操作に使用する。
        """
        if self.left_panel_overlay_widget and self.left_panel_widget_ref:
            if locked:
                # left_panel_overlay_widget を left_panel_widget_ref のサイズに合わせ、最前面に表示
                self.left_panel_overlay_widget.setGeometry(self.left_panel_widget_ref.rect())
                self.left_panel_overlay_widget.raise_()
                self.left_panel_overlay_widget.show()
            else:
                self.left_panel_overlay_widget.hide()
        logger.debug(f"Left Panel UI Lock state set to: {locked}")

    def set_file_op_buttons_enabled_ui(self, enabled):
        """ファイル操作に関連するボタン（移動、コピー、コピーモード切替）の有効/無効を切り替える。
        左パネル全体のロック（オーバーレイ）とは独立して制御される。
        """
        if self.move_files_button: self.move_files_button.setEnabled(enabled and not self.mw.is_copy_mode)
        if self.copy_files_button: self.copy_files_button.setEnabled(enabled and self.mw.is_copy_mode)
        if self.copy_mode_button: self.copy_mode_button.setEnabled(enabled)
        logger.debug(f"File operation buttons enabled state set to: {enabled} (considering copy mode: {self.mw.is_copy_mode})")

    def set_thumbnail_loading_ui_state(self, loading: bool):
        """サムネイル読み込み中のUI状態を設定する。
        左パネル全体をオーバーレイでロック/アンロックし、ファイル操作ボタンも無効化/有効化する。
        """
        self.set_ui_locked(loading)
        # サムネイル読み込み中はファイル操作ボタンも無効化するのが自然
        self.set_file_op_buttons_enabled_ui(not loading)

    def update_thumbnail_view_sizes(self):
        if self.thumbnail_view:
            self.thumbnail_view.setIconSize(QSize(self.mw.current_thumbnail_size, self.mw.current_thumbnail_size))
            self.thumbnail_view.setGridSize(QSize(self.mw.current_thumbnail_size + 10, self.mw.current_thumbnail_size + 10))

    def apply_filters_preserving_selection(self, positive_text, negative_text, generation_text, search_mode):
        """
        フィルタを適用し、可能な限り現在の選択状態を維持します。
        """
        logger.debug(f"UIManager.apply_filters_preserving_selection called. Filters: P='{positive_text}', N='{negative_text}', G='{generation_text}', Mode='{search_mode}'")
        main_window = self.mw # MainWindow への参照
        selection_model = self.thumbnail_view.selectionModel()

        if not selection_model:
            logger.warning("apply_filters_preserving_selection: Thumbnail view selection model not available.")
            return

        # 1. 現在の選択状態を保存 (ファイルパスのセットとして)
        #    コピーモードの場合は、QStandardItem の参照も保持して、後で順序を復元できるようにする。
        previously_selected_paths = set()
        # (item_ref, original_ui_order_number) のタプルをリストで保持
        previously_selected_copy_items_info = []

        current_selected_proxy_indexes = selection_model.selectedIndexes()

        logger.debug(f"  Current selected proxy indexes count: {len(current_selected_proxy_indexes)}")
        if main_window.is_copy_mode:
            # main_window.copy_selection_order (QStandardItemのリスト) を信頼する
            for i, item_ref in enumerate(main_window.copy_selection_order):
                path = item_ref.data(Qt.ItemDataRole.UserRole)
                if path:
                    previously_selected_paths.add(path)
                    # SELECTION_ORDER_ROLE は1から始まるUI上の番号
                    order_role_val = item_ref.data(SELECTION_ORDER_ROLE)
                    previously_selected_copy_items_info.append((item_ref, order_role_val if order_role_val is not None else i + 1))
            logger.debug(f"  Copy Mode: previously_selected_paths (from copy_selection_order, count: {len(previously_selected_paths)}): {sorted(list(previously_selected_paths))[:5]}")
        else:
            for proxy_idx in current_selected_proxy_indexes:
                if proxy_idx.column() == 0: # 最初の列のインデックスのみ処理
                    source_idx = self.filter_proxy_model.mapToSource(proxy_idx)
                    item = self.source_thumbnail_model.itemFromIndex(source_idx)
                    if item:
                        path = item.data(Qt.ItemDataRole.UserRole)
                        if path:
                            previously_selected_paths.add(path)
            logger.debug(f"  Move Mode: previously_selected_paths (from selectionModel, count: {len(previously_selected_paths)}): {list(previously_selected_paths)[:5]}")
        
        # logger.debug(f"UIManager: Preserving selection for {len(previously_selected_paths)} paths.") # Redundant with above

        # 2. フィルタをプロキシモデルに設定 & 適用
        logger.debug("  Setting filter parameters on proxy model and calling invalidateFilter...")
        self.filter_proxy_model.set_search_mode(search_mode)
        self.filter_proxy_model.set_positive_prompt_filter(positive_text)
        self.filter_proxy_model.set_negative_prompt_filter(negative_text)
        self.filter_proxy_model.set_generation_info_filter(generation_text)
        self.filter_proxy_model.invalidateFilter() # これによりビューが更新される
        logger.debug(f"  invalidateFilter called. Proxy model row count after filter: {self.filter_proxy_model.rowCount()}")

        # 3. 選択を復元
        new_selection_to_apply_on_view = QItemSelection()
        
        # フィルタ後に表示されるアイテムで、かつ以前選択されていたアイテムを収集
        # ソースモデルをイテレートする
        for row in range(self.source_thumbnail_model.rowCount()):
            source_item = self.source_thumbnail_model.item(row)
            if not source_item: continue

            file_path = source_item.data(Qt.ItemDataRole.UserRole)
            if file_path in previously_selected_paths: # 以前選択されていたパスか
                source_index = self.source_thumbnail_model.indexFromItem(source_item)
                proxy_index = self.filter_proxy_model.mapFromSource(source_index)
                if proxy_index.isValid(): # フィルタ後も表示されているか
                    # logger.debug(f"    Restoring selection for path: {file_path}, proxy_index: {proxy_index.row()}")
                    new_selection_to_apply_on_view.select(proxy_index, proxy_index)
        
        logger.debug(f"  Constructed new_selection_to_apply_on_view with {len(new_selection_to_apply_on_view.indexes())} proxy indexes.")

        # 4. ビューの選択を更新
        #    QItemSelectionModel.ClearAndSelect を使用すると、
        #    既存の選択をクリアし、新しい選択を適用し、selectionChanged シグナルが発行される。
        #    MainWindow.handle_thumbnail_selection_changed がこのシグナルを受けて、
        #    selected_file_paths や copy_selection_order (コピーモード時) を適切に更新する。
        logger.debug("  Calling selection_model.select with ClearAndSelect flag.")
        # selectionChangedシグナルが発火するように、ブロックせずに実行
        selection_model.select(new_selection_to_apply_on_view, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        
        # main_window._update_status_bar_info() は handle_thumbnail_selection_changed の中で呼ばれるので、
        # ここでは直接呼び出さない。
        logger.debug(f"UIManager.apply_filters_preserving_selection finished. Selection restoration command issued for {len(new_selection_to_apply_on_view.indexes())} items in view.")