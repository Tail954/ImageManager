# src/main_window.py
# (DropWindow 連携機能を統合した完全版)

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeView, QSplitter, QFrame, QFileDialog, QSlider, QListView, QDialog,
     QAbstractItemView, QLineEdit, QMenu, QRadioButton, QButtonGroup, QMessageBox, QProgressDialog, QComboBox, QStyledItemDelegate
)
from PyQt6.QtGui import QFileSystemModel, QPixmap, QIcon, QStandardItemModel, QStandardItem, QAction, QCloseEvent
from PyQt6.QtCore import Qt, QDir, QSize, QTimer, QVariant, QSortFilterProxyModel, QDirIterator, QModelIndex, QItemSelection, QByteArray # <--- ★QWIDGETSIZE_MAX のインポートを削除
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
from .ui_manager import UIManager # ★★★ UIManagerをインポート ★★★

from .constants import (
    APP_SETTINGS_FILE,
    METADATA_ROLE, SELECTION_ORDER_ROLE, PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM,
    THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU, 
    DELETE_EMPTY_FOLDERS_ENABLED,
    INITIAL_SORT_ORDER_ON_FOLDER_SELECT, SORT_BY_LOAD_ORDER_ALWAYS, SORT_BY_LAST_SELECTED, # ★★★ 初期ソート設定 ★★★
    WC_COMMENT_OUTPUT_FORMAT, WC_FORMAT_HASH_COMMENT, WC_FORMAT_BRACKET_COMMENT,
    MAIN_WINDOW_GEOMETRY, METADATA_DIALOG_GEOMETRY # ★★★ ジオメトリ定数をインポート ★★★
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
        self.ui_manager = UIManager(self) # ★★★ UIManagerのインスタンス化 ★★★

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
        self.initial_folder_dialog_path = None # For storing path from settings
        self.metadata_dialog_last_geometry = None # DialogManagerがMainWindowのこの属性を参照・更新する
        # self.full_image_dialog_instance = None # DialogManagerが管理する
        self.image_preview_mode = PREVIEW_MODE_FIT # Default, will be overwritten by _load_app_settings
        # self.current_sort_key_index = 0 # 0: Filename, 1: Update Date # 廃止
        # self.current_sort_order = Qt.SortOrder.AscendingOrder # Qt.SortOrder.AscendingOrder or Qt.SortOrder.DescendingOrder # 廃止
        self.sort_criteria_map = { # トグルボタンIDとソートロジックのマッピング
            0: {"name": "ファイル名 昇順", "key_type": 0, "order": Qt.SortOrder.AscendingOrder, "caption": "ファイル名 昇順"},
            1: {"name": "ファイル名 降順", "key_type": 0, "order": Qt.SortOrder.DescendingOrder, "caption": "ファイル名 降順"},
            2: {"name": "更新日時 昇順", "key_type": 1, "order": Qt.SortOrder.AscendingOrder, "caption": "更新日時 昇順"},
            3: {"name": "更新日時 降順", "key_type": 1, "order": Qt.SortOrder.DescendingOrder, "caption": "更新日時 降順"},
            4: {"name": "読み込み順", "key_type": 2, "order": Qt.SortOrder.AscendingOrder, "caption": "読み込み順"}, # ★★★ 追加 ★★★
        }
        self.current_sort_button_id = 0 # デフォルトは "ファイル名 ↑" (ID: 0)
        self.load_start_time = None # For load time measurement
        self.thumbnail_right_click_action = RIGHT_CLICK_ACTION_METADATA # Default value
        self.wc_creator_comment_format = WC_FORMAT_HASH_COMMENT
        self.delete_empty_folders_enabled = True # デフォルトは有効
        self.initial_folder_sort_setting = SORT_BY_LAST_SELECTED # ★★★ 追加: デフォルトは前回選択 ★★★

        self.file_operation_manager = FileOperationManager(self) # New instance
        self.file_operations = FileOperations(parent=self, file_op_manager=self.file_operation_manager) # Pass manager

        # Load application-wide settings first
        self._load_app_settings()

        # --- ★★★ UIセットアップをUIManagerに委譲 ★★★ ---
        self.ui_manager.setup_ui()

        # 設定からウィンドウジオメトリを復元 (UIセットアップ後、show()の前が望ましい)
        if self.app_settings.get(MAIN_WINDOW_GEOMETRY):
            geom_byte_array = QByteArray.fromBase64(self.app_settings[MAIN_WINDOW_GEOMETRY].encode('utf-8'))
            self.restoreGeometry(geom_byte_array)

        # スプリッターのシグナルを接続 (UIセットアップ後)
        if self.ui_manager.splitter: # UIManager で splitter が self.splitter として保持されている前提
            self.ui_manager.splitter.splitterMoved.connect(self.handle_splitter_moved)
            logger.debug("Splitter signal connected for dynamic left panel width.")

        # self._load_settings() # Load UI specific settings after all UI elements are initialized <=self._load_app_settings()に統合
        self._apply_initial_sort_from_settings() # Apply initial sort based on loaded or default settings
        self._update_status_bar_info() # Initial status bar update


    def _update_status_bar_info(self):
        if not hasattr(self, 'statusBar') or not self.statusBar:
            return
        total_items = 0
        if self.ui_manager.filter_proxy_model: # ★★★ UIManager経由 ★★★
            total_items = self.ui_manager.filter_proxy_model.rowCount() # ★★★ UIManager経由 ★★★
        selected_items = 0
        if self.ui_manager.thumbnail_view and self.ui_manager.thumbnail_view.selectionModel(): # ★★★ UIManager経由 ★★★
            selected_items = len(self.ui_manager.thumbnail_view.selectionModel().selectedIndexes()) # ★★★ UIManager経由 ★★★
        self.statusBar.showMessage(f"表示アイテム数: {total_items} / 選択アイテム数: {selected_items}")

    def _apply_initial_sort_from_settings(self):
        """アプリケーション起動時に設定からソートを適用する"""
        # このメソッドはUIの初期状態を設定する役割。
        # setChecked(True) が _apply_sort_from_toggle_button をトリガーするが、
        # _apply_sort_from_toggle_button 側で読み込み中やモデル空の状態をハンドルする。
        button_to_check = self.ui_manager.sort_button_group.button(self.current_sort_button_id) # ★★★ UIManager経由 ★★★
        if button_to_check:
            button_to_check.setChecked(True) # これにより _apply_sort_from_toggle_button がトリガーされる
            logger.info(f"初期ソートUI状態をボタンID {self.current_sort_button_id} に設定しました。実際のソートはデータ読み込み後です。")
        else: # フォールバック
            logger.warning(f"初期ソートボタンID {self.current_sort_button_id} が無効です。デフォルトのファイル名昇順を適用します。")
            self.current_sort_button_id = 0 # ID 0 (ファイル名 ↑) にリセット
            if default_button := self.ui_manager.sort_button_group.button(0): # UIManager経由
                default_button.setChecked(True)

    def _apply_sort_from_toggle_button(self, button_id: int):
        """トグルボタンのクリックに基づいてソートを実行する"""
        if not self.ui_manager.filter_proxy_model or not self.ui_manager.source_thumbnail_model: # ★★★ UIManager経由 ★★★
            logger.warning("_apply_sort_from_toggle_button: Models not ready.")
            return

        self.current_sort_button_id = button_id # 現在のソート状態を更新

        if self.is_loading_thumbnails:
            logger.info(f"ソートボタン {button_id} がクリックされましたが、サムネイル読み込み中です。設定のみ更新し、ソートは読み込み完了後に行われます。")
            return

        if self.ui_manager.source_thumbnail_model.rowCount() == 0 and not self.is_loading_thumbnails:
            logger.info("_apply_sort_from_toggle_button: Source model is empty and not loading. Sort will have no effect.")
            # ステータスバー更新は行っても良い
            self._update_status_bar_info()
            return

        self.current_sort_button_id = button_id # 現在のソート状態を更新
        selected_criteria = self.sort_criteria_map.get(self.current_sort_button_id)

        if not selected_criteria:
            logger.warning(f"Invalid sort button ID: {self.current_sort_button_id}")
            return

        key_type = selected_criteria["key_type"]
        sort_order = selected_criteria["order"]
        
        logger.info(f"Applying sort. Button ID: {button_id}, Criteria: '{selected_criteria['name']}', Key Type: {key_type}, Order: {sort_order}")
        
        # --- ソート処理中にUIをロック ---
        self.ui_manager.set_sort_buttons_enabled(False) # ソートボタン群のみを無効化
        QApplication.processEvents() # ボタンの無効化状態を即時反映

        try:
            self.ui_manager.filter_proxy_model.set_sort_key_type(key_type) # ★★★ UIManager経由 ★★★
            # QSortFilterProxyModel.sort() を呼び出すと、lessThan が使用される
            # 列インデックスは0で固定 (lessThan内で実際のキータイプを見るため)
            self.ui_manager.filter_proxy_model.sort(0, sort_order) # ★★★ UIManager経由 ★★★
        finally:
            # --- ソート処理完了後、UIロックを解除 ---
            self.ui_manager.set_sort_buttons_enabled(True) # ソートボタン群を再度有効化
        self._update_status_bar_info()

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
        # self.app_settings["sort_criteria_index"] = self.current_sort_criteria_index # 廃止 (コンボボックス用)
        self.app_settings[DELETE_EMPTY_FOLDERS_ENABLED] = self.delete_empty_folders_enabled # ★★★ 追加 ★★★
        self.app_settings[INITIAL_SORT_ORDER_ON_FOLDER_SELECT] = self.initial_folder_sort_setting # ★★★ 追加 ★★★
        self.app_settings["sort_button_id"] = self.current_sort_button_id # 新しいトグルボタンUI用

        # ★★★ ウィンドウジオメトリの保存 ★★★
        self.app_settings[MAIN_WINDOW_GEOMETRY] = self.saveGeometry().toBase64().data().decode('utf-8')
        if self.metadata_dialog_last_geometry and isinstance(self.metadata_dialog_last_geometry, QByteArray):
            self.app_settings[METADATA_DIALOG_GEOMETRY] = self.metadata_dialog_last_geometry.toBase64().data().decode('utf-8')
        elif METADATA_DIALOG_GEOMETRY in self.app_settings: # 以前の値があるが、現在は無効なら削除
            del self.app_settings[METADATA_DIALOG_GEOMETRY]


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
                DELETE_EMPTY_FOLDERS_ENABLED: self.delete_empty_folders_enabled, # ★★★ 追加 ★★★
                INITIAL_SORT_ORDER_ON_FOLDER_SELECT: self.initial_folder_sort_setting, # ★★★ 追加 ★★★
                "recursive_search": self.recursive_search_enabled,
                # "sort_criteria_index": self.current_sort_criteria_index, # 廃止
                "sort_button_id": self.current_sort_button_id, # 新しいトグルボタンUI用
                MAIN_WINDOW_GEOMETRY: self.saveGeometry().toBase64().data().decode('utf-8'),
            }
            if self.metadata_dialog_last_geometry and isinstance(self.metadata_dialog_last_geometry, QByteArray):
                settings_dict[METADATA_DIALOG_GEOMETRY] = self.metadata_dialog_last_geometry.toBase64().data().decode('utf-8')
            elif METADATA_DIALOG_GEOMETRY in settings_dict:
                del settings_dict[METADATA_DIALOG_GEOMETRY]

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
                self.initial_folder_dialog_path = lp_val
                logger.info(f"前回終了時のフォルダパスを読み込みました: {self.initial_folder_dialog_path}")
            else:
                logger.warning(f"保存されたフォルダパスが無効または見つかりません: {lp_val}")

        # 再帰検索設定
        self.recursive_search_enabled = self.app_settings.get("recursive_search", True)
        if self.ui_manager.recursive_toggle_button: # ★★★ UIManager経由 ★★★
            self.ui_manager.recursive_toggle_button.setChecked(self.recursive_search_enabled)
            self.ui_manager.update_recursive_button_text(self.recursive_search_enabled) # ★★★ UIManager経由 ★★★
        logger.info(f"再帰検索設定を読み込みました: {'ON' if self.recursive_search_enabled else 'OFF'}")

        # ソート設定
        self.current_sort_button_id = self.app_settings.get("sort_button_id", 0) # デフォルトはID 0 (ファイル名 ↑)
        if hasattr(self, 'sort_button_group'): # UI要素が存在すれば更新
            button_to_check = self.sort_button_group.button(self.current_sort_button_id)
            if button_to_check:
                pass # _apply_initial_sort_from_settings でチェックされる (sort_button_groupはui_managerが持つ)
            else:
                logger.warning(f"保存されたソートボタンIDが無効: {self.current_sort_button_id}。0にリセットします。")
                self.current_sort_button_id = 0
        logger.info(f"ソートボタンIDを読み込みました: {self.current_sort_button_id} ('{self.sort_criteria_map.get(self.current_sort_button_id, {}).get('name', 'N/A')}')")

        # ★★★ 追加: 空フォルダ削除設定 ★★★
        self.delete_empty_folders_enabled = self.app_settings.get(DELETE_EMPTY_FOLDERS_ENABLED, True)
        logger.info(f"空フォルダ削除設定を読み込みました: {'有効' if self.delete_empty_folders_enabled else '無効'}")

        # ★★★ 追加: フォルダ選択時の初期ソート設定 ★★★
        self.initial_folder_sort_setting = self.app_settings.get(INITIAL_SORT_ORDER_ON_FOLDER_SELECT, SORT_BY_LAST_SELECTED)
        logger.info(f"フォルダ選択時の初期ソート設定を読み込みました: {self.initial_folder_sort_setting}")

        # ★★★ ウィンドウジオメトリの読み込み (適用は __init__ の最後で行う) ★★★
        if main_geom_str := self.app_settings.get(MAIN_WINDOW_GEOMETRY):
            # self.restoreGeometry(QByteArray.fromBase64(main_geom_str.encode('utf-8'))) # ここでは適用しない
            logger.info(f"メインウィンドウのジオメトリを読み込みました。")
        if meta_geom_str := self.app_settings.get(METADATA_DIALOG_GEOMETRY):
            self.metadata_dialog_last_geometry = QByteArray.fromBase64(meta_geom_str.encode('utf-8'))
            logger.info(f"メタデータダイアログのジオメトリを読み込みました。")


    def select_folder(self):
        start_dir = ""
        if self.current_folder_path and os.path.isdir(self.current_folder_path):
            start_dir = self.current_folder_path
        elif self.initial_folder_dialog_path and os.path.isdir(self.initial_folder_dialog_path):
            start_dir = self.initial_folder_dialog_path
        folder_path = QFileDialog.getExistingDirectory(self, "画像フォルダを選択", start_dir)

        if folder_path:
            logger.info(f"選択されたフォルダ: {folder_path}")

            # ★★★ フォルダ選択時の初期ソート設定を適用 ★★★
            if self.initial_folder_sort_setting == SORT_BY_LOAD_ORDER_ALWAYS:
                self.current_sort_button_id = 4 # 「読み込み順」のID
                logger.info(f"フォルダ選択時の初期ソート設定により、ソートを「読み込み順」(ID: {self.current_sort_button_id}) に設定します。")
            else: # SORT_BY_LAST_SELECTED (またはデフォルト)
                # current_sort_button_id は変更せず、前回終了時の値を維持 (既に _load_app_settings で読み込まれている)
                logger.info(f"フォルダ選択時の初期ソート設定により、ソートを前回選択された順 (ID: {self.current_sort_button_id}) に設定します。")
            # 現在の current_sort_button_id に基づいてUIボタンを更新
            self._apply_initial_sort_from_settings()

            # ★★★ 設定に基づいて空フォルダ削除処理を実行 ★★★
            if self.delete_empty_folders_enabled and os.path.isdir(folder_path):
                self._try_delete_empty_subfolders(folder_path) 
            self.update_folder_tree(folder_path)

    def update_folder_tree(self, folder_path):
        self.current_folder_path = folder_path
        parent_dir = QDir(folder_path)
        root_display_path = folder_path
        if parent_dir.cdUp():
            root_display_path = parent_dir.path() # QDir.path() returns the path as a string
        logger.debug(f"ユーザー選択フォルダ: {folder_path}")
        logger.debug(f"ツリー表示ルート: {root_display_path}")
        self.ui_manager.file_system_model.setRootPath(root_display_path) # ★★★ UIManager経由 ★★★
        root_index = self.ui_manager.file_system_model.index(root_display_path) # ★★★ UIManager経由 ★★★
        self.ui_manager.folder_tree_view.setRootIndex(root_index) # ★★★ UIManager経由 ★★★
        selected_folder_index = self.ui_manager.file_system_model.index(folder_path) # ★★★ UIManager経由 ★★★
        if selected_folder_index.isValid():
            self.ui_manager.folder_tree_view.expand(selected_folder_index.parent()) # ★★★ UIManager経由 ★★★
            self.ui_manager.folder_tree_view.setCurrentIndex(selected_folder_index) # ★★★ UIManager経由 ★★★
            self.ui_manager.folder_tree_view.scrollTo(selected_folder_index, QTreeView.ScrollHint.PositionAtCenter) # ★★★ UIManager経由 ★★★
        logger.info(f"フォルダツリーを更新しました。表示ルート: {root_display_path}, 選択中: {folder_path}")
        self.load_thumbnails_from_folder(folder_path)

    def on_folder_tree_clicked(self, index):
        path = self.ui_manager.file_system_model.filePath(index) # ★★★ UIManager経由 ★★★
        if self.ui_manager.file_system_model.isDir(index): # ★★★ UIManager経由 ★★★
            logger.info(f"フォルダがクリックされました: {path}")
            self.current_folder_path = path
            # ★★★ フォルダツリークリック時は空フォルダ削除を実行しない ★★★
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
            # (この処理は既存のまま)
            if self.thumbnail_loader_thread and self.thumbnail_loader_thread.isRunning():
                logger.info("既存のサムネイル読み込みスレッドを停止します...")
                try:
                    self.thumbnail_loader_thread.thumbnailLoaded.disconnect(self.update_thumbnail_item)
                    self.thumbnail_loader_thread.progressUpdated.disconnect(self.update_progress_bar)
                    self.thumbnail_loader_thread.finished.disconnect(self.on_thumbnail_loading_finished)
                    logger.debug("既存スレッドのシグナル接続を解除しました。")
                except TypeError: 
                    logger.debug("既存スレッドのシグナル接続解除中にエラー発生、または既に解除済み。")
                except Exception as e:
                    logger.error(f"既存スレッドのシグナル接続解除中に予期せぬエラー: {e}", exc_info=True)

                self.thumbnail_loader_thread.stop() 
                if not self.thumbnail_loader_thread.wait(7000): 
                    logger.warning("既存スレッドの終了待機がタイムアウトしました。")
                else:
                    logger.info("既存スレッドが正常に終了しました。")
                self.thumbnail_loader_thread.deleteLater() 
                self.thumbnail_loader_thread = None 

            # ★★★ 新しいフォルダを読み込む前に、コピーモードの選択状態をクリア ★★★
            if self.is_copy_mode:
                logger.info("フォルダ変更のため、コピーモードの選択情報をクリアします。")
                selection_model = self.ui_manager.thumbnail_view.selectionModel() # ★★★ UIManager経由 ★★★
                if selection_model: # シグナルを一時的に切断
                    try: selection_model.selectionChanged.disconnect(self.handle_thumbnail_selection_changed)
                    except TypeError: pass # 接続されていなかった場合
                for item_in_order in list(self.copy_selection_order): 
                    if item_in_order.model() == self.ui_manager.source_thumbnail_model: # ★★★ UIManager経由 ★★★
                        item_in_order.setData(None, SELECTION_ORDER_ROLE)
                self.copy_selection_order.clear()
                if selection_model: # シグナルを再接続
                    selection_model.selectionChanged.connect(self.handle_thumbnail_selection_changed)
                self.deselect_all_thumbnails() # ビューの選択もクリア
            # ★★★ コピーモードクリア処理ここまで ★★★

            search_flags = QDirIterator.IteratorFlag.Subdirectories if self.recursive_search_enabled else QDirIterator.IteratorFlag.NoIteratorFlags
            iterator = QDirIterator(folder_path,
                                    ["*.png", "*.jpg", "*.jpeg", "*.webp"],
                                    QDir.Filter.Files | QDir.Filter.NoSymLinks,
                                    search_flags)
            while iterator.hasNext():
                image_files.append(iterator.next())
            logger.info(f"見つかった画像ファイル (再帰検索{'含む' if self.recursive_search_enabled else '含まない'}): {len(image_files)}個")
            
            # ★★★ UI状態変更をUIManagerに委譲 ★★★
            self.ui_manager.set_thumbnail_loading_ui_state(True)
            self.is_loading_thumbnails = True

            # モデルをクリアする前に、本当に古いスレッドがいないことを確認
            QApplication.processEvents() # 保留中のイベントを処理

            self.ui_manager.source_thumbnail_model.clear() # ★★★ UIManager経由 ★★★
            # 新しいフォルダを読み込む際に、非表示リストをクリアしProxyModelに通知
            self._hidden_moved_file_paths.clear() # MainWindow's list of paths to hide
            self.ui_manager.filter_proxy_model.set_hidden_paths(self._hidden_moved_file_paths) # ★★★ UIManager経由 ★★★
            logger.debug("source_thumbnail_model をクリアしました。")
            self.selected_file_paths.clear()
            self.metadata_cache.clear() # メタデータキャッシュもクリア
            self.ui_manager.update_thumbnail_view_sizes() # ★★★ UIManager経由 ★★★
            placeholder_pixmap = QPixmap(self.current_thumbnail_size, self.current_thumbnail_size)
            placeholder_pixmap.fill(Qt.GlobalColor.transparent)
            placeholder_icon = QIcon(placeholder_pixmap)
            for f_path in image_files:
                item = QStandardItem()
                item.setIcon(placeholder_icon)
                item.setText(QDir().toNativeSeparators(f_path).split(QDir.separator())[-1])
                item.setEditable(False)
                item.setData(f_path, Qt.ItemDataRole.UserRole)
                self.ui_manager.source_thumbnail_model.appendRow(item) # ★★★ UIManager経由 ★★★
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
            # ★★★ UI状態変更をUIManagerに委譲 ★★★
            self.ui_manager.set_thumbnail_loading_ui_state(False)
            self.is_loading_thumbnails = False
            self.on_thumbnail_loading_finished() # UI状態をリセットするために呼ぶ

    def handle_recursive_search_toggled(self, checked):
        self.recursive_search_enabled = checked
        self.ui_manager.update_recursive_button_text(checked) # ★★★ UIManager経由 ★★★
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
                self.ui_manager.update_thumbnail_view_sizes() # ★★★ UIManager経由 ★★★
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
            # logger.debug(f"update_thumbnail_item: Received metadata for item '{item.text()}': {metadata}")

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
            # logger.debug(f"update_thumbnail_item: Setting METADATA_ROLE for '{file_path}' with: {metadata}")
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

        if self.ui_manager.filter_proxy_model: # ★★★ UIManager経由でアクセス ★★★
            # フィルタを先に適用
            self.apply_filters(preserve_selection=True)

            # フィルタ適用後、現在のソート設定でソートを実行
            logger.info(f"サムネイル読み込み完了。現在のソート設定 (ボタンID: {self.current_sort_button_id}) をモデルに適用します。")
            # is_loading_thumbnails フラグが False になった状態でソートを実行
            # _apply_sort_from_toggle_button は is_loading_thumbnails をチェックするので、
            # フラグを先に倒してから呼び出す。

        # is_loading_thumbnails フラグとUIロックを解除
        self.is_loading_thumbnails = False 
        self.ui_manager.set_thumbnail_loading_ui_state(False) # ★★★ UI状態変更をUIManagerに委譲 ★★★

        # ソートを実行 (is_loading_thumbnails が False になった後)
        if self.ui_manager.filter_proxy_model:
            # ★★★ 「読み込み順」が選択されている場合は、明示的なソート処理をスキップ ★★★
            load_order_sort_id = -1
            for btn_id, criteria in self.sort_criteria_map.items():
                if criteria.get("key_type") == 2: # key_type 2 が「読み込み順」
                    load_order_sort_id = btn_id
                    break
            
            if self.current_sort_button_id == load_order_sort_id:
                logger.info(f"サムネイル読み込み完了。現在のソートは「読み込み順」(ID: {self.current_sort_button_id}) のため、明示的なソートはスキップします。")
                # 「読み込み順」の場合、ソースモデルに追加された順序が維持されるため、
                # filter_proxy_model.sort() を呼び出す必要はありません。
                # フィルタリングは既に apply_filters で行われています。
            else:
                logger.info(f"サムネイル読み込み完了。現在のソート設定 (ボタンID: {self.current_sort_button_id}) をモデルに適用します。")
                self._apply_sort_from_toggle_button(self.current_sort_button_id)

        self._update_status_bar_info()
        self.statusBar.showMessage("サムネイル読み込み完了", 5000)

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
            for proxy_idx in self.ui_manager.thumbnail_view.selectionModel().selectedIndexes(): # ★★★ UIManager経由 ★★★
                source_idx = self.ui_manager.filter_proxy_model.mapToSource(proxy_idx) # ★★★ UIManager経由 ★★★
                item = self.ui_manager.source_thumbnail_model.itemFromIndex(source_idx) # ★★★ UIManager経由 ★★★
                if item:
                    selected_items_now_list.append(item)
            removed_items = [item for item in self.copy_selection_order if item not in selected_items_now_list]
            for item_to_remove in removed_items:
                if item_to_remove in self.copy_selection_order:
                    self.copy_selection_order.remove(item_to_remove)
                item_to_remove.setData(None, SELECTION_ORDER_ROLE)
                source_idx = self.ui_manager.source_thumbnail_model.indexFromItem(item_to_remove) # ★★★ UIManager経由 ★★★
                proxy_idx = self.ui_manager.filter_proxy_model.mapFromSource(source_idx) # ★★★ UIManager経由 ★★★
                if proxy_idx.isValid():
                    self.ui_manager.thumbnail_view.update(proxy_idx) # ★★★ UIManager経由 ★★★
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
                source_idx = self.ui_manager.source_thumbnail_model.indexFromItem(item_to_update) # ★★★ UIManager経由 ★★★
                proxy_idx = self.ui_manager.filter_proxy_model.mapFromSource(source_idx) # ★★★ UIManager経由 ★★★
                if proxy_idx.isValid():
                    self.ui_manager.thumbnail_view.update(proxy_idx) # ★★★ UIManager経由 ★★★
            logger.debug(f"Copy mode selection order: {[item.data(Qt.ItemDataRole.UserRole) for item in self.copy_selection_order]}")
            self.selected_file_paths = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items_now_list]
        else:
             # --- Normal (Move) Mode Selection Logic ---
            self.selected_file_paths.clear()
            for proxy_index in self.ui_manager.thumbnail_view.selectionModel().selectedIndexes(): # ★★★ UIManager経由 ★★★
                source_index = self.ui_manager.filter_proxy_model.mapToSource(proxy_index) # ★★★ UIManager経由 ★★★
                item = self.ui_manager.source_thumbnail_model.itemFromIndex(source_index) # ★★★ UIManager経由 ★★★
                if item:
                    file_path = item.data(Qt.ItemDataRole.UserRole)
                    if file_path:
                        self.selected_file_paths.append(file_path)
            logger.debug(f"Move mode selection: {self.selected_file_paths}")
        self._update_status_bar_info()

    def select_all_thumbnails(self):
        if self.ui_manager.thumbnail_view.model() and self.ui_manager.thumbnail_view.model().rowCount() > 0: # ★★★ UIManager経由 ★★★
            self.ui_manager.thumbnail_view.selectAll() # ★★★ UIManager経由 ★★★
            logger.info("すべての表示中サムネイルを選択しました。")
        else:
            logger.info("選択対象のサムネイルがありません。")
        self._update_status_bar_info()

    def deselect_all_thumbnails(self):
        self.ui_manager.thumbnail_view.clearSelection() # ★★★ UIManager経由 ★★★
        logger.info("すべてのサムネイルの選択を解除しました。")
        self._update_status_bar_info()

    def apply_filters(self, preserve_selection=False):
        # logger.info(f"apply_filters: START - Preserve selection: {preserve_selection}") # 削除
        if not preserve_selection:
            # logger.info("apply_filters: Calling deselect_all_thumbnails...") # 削除
            self.deselect_all_thumbnails()
            # logger.info(f"apply_filters: deselect_all_thumbnails finished in ... seconds.") # 削除

        if self.ui_manager.filter_proxy_model: # ★★★ UIManager経由 ★★★
            search_mode = "AND" if self.ui_manager.and_radio_button.isChecked() else "OR" # ★★★ UIManager経由 ★★★
            # logger.info("apply_filters: Setting filter parameters...") # 削除
            self.ui_manager.filter_proxy_model.set_search_mode(search_mode) # ★★★ UIManager経由 ★★★
            self.ui_manager.filter_proxy_model.set_positive_prompt_filter(self.ui_manager.positive_prompt_filter_edit.text()) # ★★★ UIManager経由 ★★★
            self.ui_manager.filter_proxy_model.set_negative_prompt_filter(self.ui_manager.negative_prompt_filter_edit.text()) # ★★★ UIManager経由 ★★★
            self.ui_manager.filter_proxy_model.set_generation_info_filter(self.ui_manager.generation_info_filter_edit.text()) # ★★★ UIManager経由 ★★★
            # logger.info(f"apply_filters: Filter parameters set in ... seconds.") # 削除

            # フィルタ条件設定後、明示的にinvalidateを呼び出して再フィルタリングと再ソートを促す
            # logger.info("apply_filters: Calling filter_proxy_model.invalidateFilter()...") # 削除
            self.ui_manager.filter_proxy_model.invalidateFilter() # ★★★ UIManager経由 ★★★ invalidate() から invalidateFilter() に変更
            # logger.info(f"apply_filters: filter_proxy_model.invalidateFilter() finished in ... seconds.") # 削除
        else:
            logger.warning("Filter proxy model not yet initialized for apply_filters call.") # Warning level might be appropriate

        # logger.info("apply_filters: Calling _update_status_bar_info...") # 削除
        self._update_status_bar_info()
        # logger.info(f"apply_filters: _update_status_bar_info finished in ... seconds.") # 削除
        # logger.info(f"apply_filters: END - Total time: ... seconds.") # 削除

    # --- ★★★ START: DropWindow連携メソッド ★★★ ---
    # --- ★★★ END: DropWindow連携メソッド ★★★ ---

    def _open_wc_creator_dialog(self):
        logger.info("ワイルドカード作成ツールを起動します。")

        selected_proxy_indexes = self.ui_manager.thumbnail_view.selectionModel().selectedIndexes() # ★★★ UIManager経由 ★★★
        if not selected_proxy_indexes:
            QMessageBox.information(self, "情報", "作成対象の画像をサムネイル一覧から選択してください。")
            return

        selected_files_for_wc = []
        metadata_for_wc = []

        processed_paths = set() # 選択されたアイテムの重複処理を避ける
        
        for proxy_idx in selected_proxy_indexes:
            if proxy_idx.column() == 0:
                source_idx = self.ui_manager.filter_proxy_model.mapToSource(proxy_idx) # ★★★ UIManager経由 ★★★
                item = self.ui_manager.source_thumbnail_model.itemFromIndex(source_idx) # ★★★ UIManager経由 ★★★
                if item:
                    file_path = item.data(Qt.ItemDataRole.UserRole)
                    if file_path and file_path not in processed_paths:
                        metadata = item.data(METADATA_ROLE)
                        if not isinstance(metadata, dict):
                            metadata = self.metadata_cache.get(file_path)
                        if not isinstance(metadata, dict): # キャッシュにもなければ再抽出
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
        # logger.info(f"_process_file_op_completion: START - Result: {result}") # 削除
        status = result.get('status', 'unknown')
        operation_type = result.get('operation_type', 'unknown')
        if status == 'cancelled':
            self.statusBar.showMessage("ファイル操作がキャンセルされました。", 5000)
            # logger.info(f"_process_file_op_completion: END - Cancelled. Total time: ... seconds.") # 削除
            return
        errors = result.get('errors', [])
        successfully_moved_src_paths = result.get('successfully_moved_src_paths', []) # For move
        if operation_type == "move":
            moved_count = result.get('moved_count', 0)
            renamed_files = result.get('renamed_files', [])
            # logger.info(f"_process_file_op_completion: Processing 'move' operation. Moved: {moved_count}, Renamed: {len(renamed_files)}, Errors: {len(errors)}") # 削除
            if moved_count > 0 and successfully_moved_src_paths:
                 # logger.info(f"_process_file_op_completion: Creating path_to_item_map...") # 削除
                 path_to_item_map = {}
                 for row in range(self.ui_manager.source_thumbnail_model.rowCount()): # ★★★ UIManager経由 ★★★
                     item = self.ui_manager.source_thumbnail_model.item(row) # ★★★ UIManager経由 ★★★
                     if item:
                         item_path = item.data(Qt.ItemDataRole.UserRole)
                         if item_path:
                             path_to_item_map[item_path] = item
                 # logger.info(f"_process_file_op_completion: path_to_item_map created in ... seconds. Size: {len(path_to_item_map)}") # 削除
                 # logger.info(f"_process_file_op_completion: Collecting and sorting items_to_remove_from_model...") # 削除
                 items_to_remove_from_model = []
                 for path_to_remove in successfully_moved_src_paths:
                     item_to_remove = path_to_item_map.get(path_to_remove)
                     if item_to_remove:
                         items_to_remove_from_model.append(item_to_remove)
                     else:
                         logger.warning(f"_process_file_op_completion: Moved path {path_to_remove} not found in source model's path_to_item_map for removal.")
                 items_to_remove_from_model.sort(key=lambda x: x.row() if x and x.model() == self.ui_manager.source_thumbnail_model else -1, reverse=True) # ★★★ UIManager経由 ★★★
                 # logger.info(f"_process_file_op_completion: items_to_remove_from_model collected and sorted in ... seconds. Count: {len(items_to_remove_from_model)}") # 削除
                 # --- 選択変更シグナルを一時的にブロック ---
                 # logger.info(f"_process_file_op_completion: Disconnecting selectionChanged signal...") # 削除
                 try:
                     self.ui_manager.thumbnail_view.selectionModel().selectionChanged.disconnect(self.handle_thumbnail_selection_changed) # ★★★ UIManager経由 ★★★
                     # logger.info(f"_process_file_op_completion: selectionChanged signal disconnected in ... seconds.") # 削除
                 except TypeError:
                     logger.warning("selectionChanged signal was not connected, cannot disconnect.")
                 # --- シグナルブロック終わり ---
                 # 削除対象の行番号リストを作成 (降順になっているはず)
                 rows_to_delete_indices = []
                 for item_to_remove_instance in items_to_remove_from_model:
                     if item_to_remove_instance and item_to_remove_instance.model() == self.ui_manager.source_thumbnail_model: # ★★★ UIManager経由 ★★★
                         rows_to_delete_indices.append(item_to_remove_instance.row())
                     elif item_to_remove_instance:
                         logger.warning(f"_process_file_op_completion: Item for path {item_to_remove_instance.data(Qt.ItemDataRole.UserRole)} is no longer in the expected model or is invalid, skipping removal.")
                 # logger.info(f"_process_file_op_completion: Disabling thumbnail_view updates...") # 削除
                 self.ui_manager.thumbnail_view.setUpdatesEnabled(False) # ★ ビューの更新を一時的に無効化 ★★★ UIManager経由 ★★★
                 # logger.info(f"_process_file_op_completion: thumbnail_view updates disabled in ... seconds.") # 削除
                 if rows_to_delete_indices:
                     # logger.info(f"_process_file_op_completion: Starting item removal loop for {len(rows_to_delete_indices)} rows. Source model rowCount before: {self.ui_manager.source_thumbnail_model.rowCount()}, Proxy model rowCount: {self.ui_manager.filter_proxy_model.rowCount()}") # 削除
                     num_removed_successfully = 0

                     # --- モデルの大幅な変更を通知 ---
                     # logger.info("_process_file_op_completion: Emitting layoutAboutToBeChanged.") # 削除
                     self.ui_manager.source_thumbnail_model.layoutAboutToBeChanged.emit()
                     # ---------------------------------

                     for row_num in rows_to_delete_indices:
                         # logger.debug(f"_process_file_op_completion: Removing row {row_num}...")
                         # start_time_remove_row = time.time()
                         # QModelIndex() は親がないトップレベルアイテムを示す
                         # self.ui_manager.source_thumbnail_model.beginRemoveRows(QModelIndex(), row_num, row_num) # ★ 変更: layoutAboutToBeChanged/layoutChanged を使うためコメントアウト
                         removed = self.ui_manager.source_thumbnail_model.removeRow(row_num) # ★★★ UIManager経由 ★★★
                         # self.ui_manager.source_thumbnail_model.endRemoveRows() # ★ 変更: layoutAboutToBeChanged/layoutChanged を使うためコメントアウト
                         if removed:
                             num_removed_successfully +=1
                             # logger.debug(f"_process_file_op_completion: Successfully removed row {row_num} from source model in {time.time() - start_time_remove_row:.4f} seconds.")
                         else:
                             logger.warning(f"_process_file_op_completion: Failed to remove row {row_num} from source model.")
                     # --- モデルの変更完了を通知 ---
                     # logger.info("_process_file_op_completion: Emitting layoutChanged.") # 削除
                     self.ui_manager.source_thumbnail_model.layoutChanged.emit()
                     # -----------------------------
                     # logger.info(f"_process_file_op_completion: Item removal loop finished in ... seconds. Successfully removed: {num_removed_successfully} items.") # 削除
                     # logger.info(f"_process_file_op_completion: Source model rowCount after removal: {self.ui_manager.source_thumbnail_model.rowCount()}, Proxy model rowCount: {self.ui_manager.filter_proxy_model.rowCount()}") # 削除
                 # --- 選択変更シグナルを再接続し、手動でハンドラを呼び出す ---
                 # logger.info(f"_process_file_op_completion: Reconnecting selectionChanged signal...") # 削除
                 self.ui_manager.thumbnail_view.selectionModel().selectionChanged.connect(self.handle_thumbnail_selection_changed) # ★★★ UIManager経由 ★★★
                 # logger.info(f"_process_file_op_completion: selectionChanged signal reconnected in ... seconds.") # 削除
                 # logger.info(f"_process_file_op_completion: Calling handle_thumbnail_selection_changed manually...") # 削除
                 # モデル変更後に選択状態が自動的に更新されるが、ハンドラは呼ばれない可能性があるため手動で呼ぶ
                 self.handle_thumbnail_selection_changed(QItemSelection(), QItemSelection()) # 空の選択変更としてハンドラをトリガー
                 self.selected_file_paths.clear()
                 # logger.info(f"_process_file_op_completion: handle_thumbnail_selection_changed finished in ... seconds.") # 削除
                 # ★★★ ファイル移動後、フィルタを再適用してビューを更新 ★★★
                 # logger.info(f"_process_file_op_completion: Processing UI events before enabling updates...") # 削除
                 QApplication.processEvents() # UIイベント処理を挟む
                 # logger.info(f"_process_file_op_completion: Enabling thumbnail_view updates...") # 削除
                 self.ui_manager.thumbnail_view.setUpdatesEnabled(True) # ★ ビューの更新を有効化 ★★★ UIManager経由 ★★★
                 # logger.info(f"_process_file_op_completion: thumbnail_view updates enabled in ... seconds.") # 削除
                 # logger.info(f"_process_file_op_completion: Calling apply_filters...") # 削除
                 # apply_filters の前に True に戻すか、後にするかは挙動を見て調整
                 self.apply_filters(preserve_selection=True) # preserve_selection=True で現在の選択を維持しようと試みる (実際にはクリアされるが)
                 # logger.info(f"_process_file_op_completion: apply_filters finished in ... seconds.") # 削除
                 self._update_status_bar_info() # _update_status_bar_info() は handle_thumbnail_selection_changed 内でも呼ばれるが、ここでも呼ぶ
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
            # logger.info(f"_process_file_op_completion: Processing 'copy' operation. Result: {result}") # 削除
            copied_count = result.get('copied_count', 0)
            if errors:
                QMessageBox.warning(self, "コピーエラー", "以下のエラーが発生しました:\n" + "\n".join(errors))
            if copied_count > 0:
                self.statusBar.showMessage(f"{copied_count}個のファイルをコピーしました。", 5000)
            elif not errors:
                self.statusBar.showMessage("コピーするファイルがありませんでした、または処理が完了しました。", 3000)
        if status == 'completed' and not errors:
            # logger.info(f"_process_file_op_completion: Operation '{operation_type}' completed without errors. Deselecting thumbnails.") # 削除
            self.deselect_all_thumbnails()
            if operation_type == "copy":
                for item_in_order in self.copy_selection_order:
                    if item_in_order.data(SELECTION_ORDER_ROLE) is not None:
                        item_in_order.setData(None, SELECTION_ORDER_ROLE)
                        source_idx = self.ui_manager.source_thumbnail_model.indexFromItem(item_in_order) # ★★★ UIManager経由 ★★★
                        proxy_idx = self.ui_manager.filter_proxy_model.mapFromSource(source_idx) # ★★★ UIManager経由 ★★★
                        if proxy_idx.isValid():
                            self.ui_manager.thumbnail_view.update(proxy_idx) # ★★★ UIManager経由 ★★★
                self.copy_selection_order.clear()
            # ★★★ ファイル移動完了後の自動的な空フォルダ削除処理を削除 ★★★
        # logger.info(f"_process_file_op_completion: END - Total time: ... seconds.") # 削除

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
                        self.ui_manager.file_system_model.setRootPath("") # ★★★ UIManager経由 ★★★
                        self.ui_manager.source_thumbnail_model.clear() # ★★★ UIManager経由 ★★★
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

    def resizeEvent(self, event: QCloseEvent): # QResizeEvent の方が適切ですが、既存の型ヒントを維持します
        """ウィンドウリサイズ時に左パネルのオーバーレイウィジェットのサイズを調整し、
        左パネルの最大幅を固定値に設定する。
        """
        super().resizeEvent(event)

        # --- 左パネルの最大幅をウィンドウリサイズ時に350pxに設定 ---
        if self.ui_manager.left_panel_widget_ref:
            self.ui_manager.left_panel_widget_ref.setMaximumWidth(350)
            # logger.debug("Window resized, left panel max width set to 350.") # 頻繁に出力されるためコメントアウト

        # 左パネルのオーバーレイウィジェットが有効（表示中）であれば、
        # 左パネルの現在のサイズに合わせてオーバーレイのサイズも更新する
        if hasattr(self.ui_manager, 'left_panel_overlay_widget') and \
           self.ui_manager.left_panel_overlay_widget and self.ui_manager.left_panel_widget_ref and \
           self.ui_manager.left_panel_overlay_widget.isVisible():
            self.ui_manager.left_panel_overlay_widget.setGeometry(self.ui_manager.left_panel_widget_ref.rect())

    def handle_splitter_moved(self, pos: int, index: int):
        """スプリッターがユーザーによってドラッグされたときに呼び出され、左パネルの最大幅制限を解除する。"""
        if self.ui_manager.left_panel_widget_ref:
            # QWIDGETSIZE_MAX の代わりに大きな整数値を設定
            self.ui_manager.left_panel_widget_ref.setMaximumWidth(16777215) # 実質無制限
            logger.debug(f"Splitter moved by user. Left panel max width unrestricted. Pos: {pos}, Index: {index}")

    def _show_thumbnail_context_menu(self, pos):
        proxy_index = self.ui_manager.thumbnail_view.indexAt(pos) # ★★★ UIManager経由 ★★★
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
            menu.exec(self.ui_manager.thumbnail_view.viewport().mapToGlobal(pos)) # ★★★ UIManager経由 ★★★
        else:
            logger.warning(f"不明なサムネイル右クリック動作設定: {self.thumbnail_right_click_action}")
            self.dialog_manager.open_metadata_dialog(proxy_index) # DialogManager経由で呼び出し

    def _open_file_location_for_item(self, proxy_index):
        if not proxy_index.isValid():
            logger.warning("ファイルの場所を開く操作が、無効なインデックスで呼び出されました。")
            return
        source_index = self.ui_manager.filter_proxy_model.mapToSource(proxy_index) # ★★★ UIManager経由 ★★★
        item = self.ui_manager.source_thumbnail_model.itemFromIndex(source_index) # ★★★ UIManager経由 ★★★
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