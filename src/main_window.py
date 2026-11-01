"""Main window wiring for navigation, controllers, and UI actions."""

import logging
import os
from dataclasses import dataclass

import send2trash
from PyQt6.QtCore import QByteArray, QDir, QDirIterator, Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QResizeEvent
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMenu, QMessageBox, QTreeView

from .thumbnail_controller import ThumbnailController
from .selection_controller import SelectionController
from .settings_store import SettingsStore
from .favorite_folders import FavoriteFolders, normalize_folder_path
from .folder_cleanup import find_empty_subfolders, is_dir_empty_recursive
from .file_operations import FileOperations
from .dialog_manager import DialogManager
from .file_operation_manager import FileOperationManager
from .ui_manager import UIManager

from .constants import (
    PREVIEW_MODE_FIT,
    THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU, 
    DELETE_EMPTY_FOLDERS_ENABLED, 
    LAST_MOVE_DESTINATION_FOLDER, LAST_COPY_DESTINATION_FOLDER, # ファイル操作の最終宛先フォルダ
    INITIAL_SORT_ORDER_ON_FOLDER_SELECT, SORT_BY_LOAD_ORDER_ALWAYS, SORT_BY_LAST_SELECTED, # 初期ソート設定
    WC_COMMENT_OUTPUT_FORMAT, WC_FORMAT_HASH_COMMENT,
    MAIN_WINDOW_GEOMETRY, METADATA_DIALOG_GEOMETRY, # ジオメトリ定数をインポート
    DOUBLE_CLICK_ACTION, DOUBLE_CLICK_ACTION_VIEWER,
    FAVORITE_FOLDERS
)

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class NavigationResult:
    status: str
    message: str = ""

class MainWindow(QMainWindow):
    # ----------------------------------------------------------------------
    # --------------------------------------------------------------------

    def __init__(self):
        super().__init__()
        self.settings_store = SettingsStore()
        self.thumbnail_controller = None
        self.selection_controller = None
        self._active_generation = 0
        self._closing = False
        # self.metadata_dialog_instance = None # DialogManagerが管理
        self.drop_window_instance = None # <--- ★追加: DropWindowのインスタンスを保持
        self.dialog_manager = DialogManager(self, self.settings_store)
        self.ui_manager = UIManager(self) # UIManagerのインスタンス化

        self.setWindowTitle("ImageManager")
        self.setGeometry(100, 100, 1200, 800)

        self.available_sizes = [96, 128, 200]
        self.current_thumbnail_size = self.available_sizes[1] # Default to 128
        self.current_folder_path = None # To store the currently selected folder path
        self.is_loading_thumbnails = False # Flag to indicate loading state
        self.recursive_search_enabled = True # Default to ON
        self.is_copy_mode = False # Flag for copy mode state, True if copy mode is active
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
            4: {"name": "読み込み順", "key_type": 2, "order": Qt.SortOrder.AscendingOrder, "caption": "読み込み順"},
        }
        self.current_sort_button_id = 0 # デフォルトは "ファイル名 ↑" (ID: 0)
        self.load_start_time = None # For load time measurement
        self.thumbnail_right_click_action = RIGHT_CLICK_ACTION_METADATA # Default value
        self.wc_creator_comment_format = WC_FORMAT_HASH_COMMENT # Default value
        self.delete_empty_folders_enabled = True # デフォルトは有効
        self.initial_folder_sort_setting = SORT_BY_LAST_SELECTED # ★★★ 追加: デフォルトは前回選択 ★★★
        self.last_move_destination_folder = None # ★★★ 追加: 最後に使用した移動先フォルダ ★★★
        self.last_copy_destination_folder = None # ★★★ 追加: 最後に使用したコピー先フォルダ ★★★

        self.file_operation_manager = FileOperationManager(self) # New instance
        self.file_operations = FileOperations(parent=self)

        # Load application-wide settings first
        self._load_app_settings()

    # --- ★★★ UIセットアップをUIManagerに委譲 ★★★ ---
        self.ui_manager.setup_ui()
        self.thumbnail_controller = ThumbnailController(self.ui_manager.source_thumbnail_model,
                                                        self.ui_manager.filter_proxy_model, self)
        self.selection_controller = SelectionController(self.thumbnail_controller,
                                                        self.ui_manager.filter_proxy_model,
                                                        self.ui_manager.thumbnail_view, self)
        self.ui_manager.bind_controllers(self.thumbnail_controller, self.selection_controller)
        self.dialog_manager.bind_controllers(self.thumbnail_controller, self.selection_controller)
        self.selection_controller.selectionChanged.connect(self._update_status_bar_info)
        self.thumbnail_controller.progressChanged.connect(self._thumbnail_progress)
        self.thumbnail_controller.completed.connect(self._thumbnail_completed)
        self.thumbnail_controller.idle.connect(self._maybe_finish_close)
        self.file_operations.idle.connect(self._file_operation_idle)
        self.file_operation_manager.bind_service()
        self.favorites = FavoriteFolders(self.settings_store.get(FAVORITE_FOLDERS),
                                         lambda paths: self.settings_store.save({FAVORITE_FOLDERS: paths}))
        self._connect_favorites()

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
        selected_items = len(self.selection_controller.selected_paths()) if self.selection_controller else 0
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
        if button_id not in self.sort_criteria_map:
            return
        self.current_sort_button_id = button_id
        if self.is_loading_thumbnails or self.selection_controller is None:
            return
        criteria = self.sort_criteria_map[button_id]
        self.selection_controller.apply_sort(criteria["key_type"], criteria["order"])
        self._update_status_bar_info()

    def is_image_selected(self, image_path):
        return bool(self.selection_controller and self.selection_controller.is_selected(image_path))

    def handle_toggle_view_selection(self, image_path):
        self.selection_controller.toggle(image_path)
        for dialog in (self.dialog_manager.full_image_dialog_instance,
                       self.dialog_manager.image_with_metadata_dialog_instance):
            if dialog and dialog.isVisible():
                dialog.update_selection_state(image_path)

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

        toggle_drop_window_action = QAction("&D＆Dウィンドウ", self) # '&'でショートカットキーヒント
        toggle_drop_window_action.setStatusTip("画像のメタデータを表示するためのドラッグ＆ドロップウィンドウを開きます")
        toggle_drop_window_action.triggered.connect(self.dialog_manager.toggle_drop_window) # DialogManager経由で呼び出し
        tool_menu.addAction(toggle_drop_window_action) # 「D&Dウィンドウ」をツールメニューの一番下に追加

        # 「タグパレット」アクション
        toggle_tag_palette_action = QAction("タグパレット (&T)", self) # '&T' でアクセスキー T
        toggle_tag_palette_action.setStatusTip("YAMLファイルから読み込んだタグを選択してクリップボードにコピーします")
        toggle_tag_palette_action.triggered.connect(self.dialog_manager.toggle_tag_palette)
        tool_menu.addAction(toggle_tag_palette_action)

    def _save_settings(self):
        changes = {
            "thumbnail_size": self.current_thumbnail_size,
            "image_preview_mode": self.image_preview_mode,
            THUMBNAIL_RIGHT_CLICK_ACTION: self.thumbnail_right_click_action,
            WC_COMMENT_OUTPUT_FORMAT: self.wc_creator_comment_format,
            "last_folder_path": self.current_folder_path,
            "recursive_search": self.recursive_search_enabled,
            DELETE_EMPTY_FOLDERS_ENABLED: self.delete_empty_folders_enabled,
            INITIAL_SORT_ORDER_ON_FOLDER_SELECT: self.initial_folder_sort_setting,
            "sort_button_id": self.current_sort_button_id,
            LAST_MOVE_DESTINATION_FOLDER: self.last_move_destination_folder,
            LAST_COPY_DESTINATION_FOLDER: self.last_copy_destination_folder,
            DOUBLE_CLICK_ACTION: self.double_click_action,
            MAIN_WINDOW_GEOMETRY: self.saveGeometry().toBase64().data().decode('utf-8'),
        }
        if isinstance(self.metadata_dialog_last_geometry, QByteArray):
            changes[METADATA_DIALOG_GEOMETRY] = self.metadata_dialog_last_geometry.toBase64().data().decode('utf-8')
        return self.settings_store.save(changes)

    def _read_app_settings_file(self):
        return self.settings_store.load()

    def _write_app_settings_file(self, settings_dict=None):
        return self.settings_store.save(settings_dict)

    def _load_app_settings(self):
        """アプリケーション全体の設定を読み込み、UI要素に反映する"""
        self.settings_store.load()

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
        self.current_sort_button_id = self.app_settings.get("sort_button_id", 4) # ★★★ デフォルトを「読み込み順」(ID:4) に変更 ★★★
        if hasattr(self, 'sort_button_group'): # UI要素が存在すれば更新
            button_to_check = self.sort_button_group.button(self.current_sort_button_id)
            if button_to_check:
                pass # _apply_initial_sort_from_settings でチェックされる (sort_button_groupはui_managerが持つ)
            else:
                logger.warning(f"保存されたソートボタンIDが無効: {self.current_sort_button_id}。0にリセットします。")
                self.current_sort_button_id = 4 # ★★★ リセット先も「読み込み順」(ID:4) に変更 ★★★
        logger.info(f"ソートボタンIDを読み込みました: {self.current_sort_button_id} ('{self.sort_criteria_map.get(self.current_sort_button_id, {}).get('name', 'N/A')}')")

        # ★★★ 追加: 空フォルダ削除設定 ★★★
        self.delete_empty_folders_enabled = self.app_settings.get(DELETE_EMPTY_FOLDERS_ENABLED, True)
        logger.info(f"空フォルダ削除設定を読み込みました: {'有効' if self.delete_empty_folders_enabled else '無効'}")

        # ★★★ 追加: フォルダ選択時の初期ソート設定 ★★★
        self.initial_folder_sort_setting = self.app_settings.get(INITIAL_SORT_ORDER_ON_FOLDER_SELECT, SORT_BY_LOAD_ORDER_ALWAYS) # ★★★ デフォルトを「常に読み込み順」に変更 ★★★
        logger.info(f"フォルダ選択時の初期ソート設定を読み込みました: {self.initial_folder_sort_setting}")

        # ★★★ 追加: ダブルクリック動作設定 ★★★
        self.double_click_action = self.app_settings.get(DOUBLE_CLICK_ACTION, DOUBLE_CLICK_ACTION_VIEWER)
        logger.info(f"ダブルクリック動作設定を読み込みました: {self.double_click_action}")

        # ★★★ ウィンドウジオメトリの読み込み (適用は __init__ の最後で行う) ★★★
        if main_geom_str := self.app_settings.get(MAIN_WINDOW_GEOMETRY):
            # self.restoreGeometry(QByteArray.fromBase64(main_geom_str.encode('utf-8'))) # ここでは適用しない
            logger.info(f"メインウィンドウのジオメトリを読み込みました。")
        if meta_geom_str := self.app_settings.get(METADATA_DIALOG_GEOMETRY):
            self.metadata_dialog_last_geometry = QByteArray.fromBase64(meta_geom_str.encode('utf-8'))
            logger.info(f"メタデータダイアログのジオメトリを読み込みました。")
        
        # ★★★ 追加: ファイル操作の最終宛先フォルダの読み込み ★★★
        if lmd_val := self.app_settings.get(LAST_MOVE_DESTINATION_FOLDER):
            if os.path.isdir(lmd_val):
                self.last_move_destination_folder = lmd_val
                logger.info(f"最終移動先フォルダパスを読み込みました: {self.last_move_destination_folder}")
            else:
                logger.warning(f"保存された最終移動先フォルダパスが無効または見つかりません: {lmd_val}")
        if lcd_val := self.app_settings.get(LAST_COPY_DESTINATION_FOLDER):
            if os.path.isdir(lcd_val):
                self.last_copy_destination_folder = lcd_val
                logger.info(f"最終コピー先フォルダパスを読み込みました: {self.last_copy_destination_folder}")
            else:
                logger.warning(f"保存された最終コピー先フォルダパスが無効または見つかりません: {lcd_val}")


    def select_folder(self):
        start = self.current_folder_path or self.initial_folder_dialog_path or ""
        path = QFileDialog.getExistingDirectory(self, "画像フォルダを選択", start)
        if path:
            self.request_folder_navigation(path, source="dialog")

    def update_folder_tree(self, folder_path):
        return self.request_folder_navigation(folder_path, source="refresh", force_reload=True)

    def on_folder_tree_clicked(self, index):
        path = self.ui_manager.file_system_model.filePath(index)
        if self.ui_manager.file_system_model.isDir(index):
            self.request_folder_navigation(path, source="tree")

    def load_thumbnails_from_folder(self, folder_path):
        return self.request_folder_navigation(folder_path, source="refresh", force_reload=True)

    def handle_recursive_search_toggled(self, checked):
        self.recursive_search_enabled = checked
        self.ui_manager.update_recursive_button_text(checked) # ★★★ UIManager経由 ★★★
        logger.info(f"再帰検索設定変更: {'ON' if checked else 'OFF'}. 次回フォルダ読み込み時に適用されます。")

    def apply_thumbnail_size_change(self, new_size):
        if self.is_loading_thumbnails or new_size not in self.available_sizes or new_size == self.current_thumbnail_size:
            return False
        previous = self.current_thumbnail_size
        self.current_thumbnail_size = new_size
        self.ui_manager.update_thumbnail_view_sizes()
        if self.current_folder_path:
            result = self.request_folder_navigation(self.current_folder_path, source="refresh", force_reload=True)
            if result.status != "accepted":
                self.current_thumbnail_size = previous
                self.ui_manager.update_thumbnail_view_sizes()
                return False
        return True

    def update_progress_bar(self, processed_count, total_files):
        self.statusBar.showMessage(f"サムネイル読み込み中... {processed_count}/{total_files}")

    def update_thumbnail_item(self, item, q_image, metadata):
        # Legacy call site: the controller owns normal worker result application.
        if item is not None:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                self.thumbnail_controller.cache_metadata(path, metadata)

    def on_thumbnail_loading_finished(self):
        self._thumbnail_completed(self._active_generation)

    def handle_thumbnail_selection_changed(self, selected, deselected):
        if self.selection_controller is not None:
            self.selection_controller.sync_from_view()

    def select_all_thumbnails(self):
        self.selection_controller.select_all()

    def deselect_all_thumbnails(self):
        self.selection_controller.clear()

    def apply_filters(self, preserve_selection=False):
        if self.is_loading_thumbnails:
            return
        ui = self.ui_manager
        self.selection_controller.apply_filters(
            ui.positive_prompt_filter_edit.text(), ui.negative_prompt_filter_edit.text(),
            ui.generation_info_filter_edit.text(),
            "AND" if ui.and_radio_button.isChecked() else "OR", preserve_selection)
        self._update_status_bar_info()

    def _process_file_op_completion(self, result):
        self.file_operation_manager.apply_result(result)

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
                pass  # Navigation performs one fresh enumeration after this dialog.
        else:
             logger.info(f"'{parent_folder_path_for_context}' 内の空のサブフォルダのゴミ箱への移動はキャンセルされました。")

    def _find_empty_subfolders(self, parent_dir):
        return find_empty_subfolders(parent_dir)

    def _is_dir_empty_recursive(self, dir_path):
        return is_dir_empty_recursive(dir_path)

    def closeEvent(self, event: QCloseEvent):
        if not self._closing:
            self._closing = True
            self._save_settings()
            self.thumbnail_controller.shutdown()
            self.file_operations.stop_operation()
        if not self.thumbnail_controller.is_idle() or self.file_operations.is_busy():
            event.ignore()
            return
        if self.dialog_manager.drop_window_instance:
            self.dialog_manager.drop_window_instance.close()
        super().closeEvent(event)

    @property
    def app_settings(self):
        return self.settings_store.snapshot()

    @property
    def metadata_cache(self):
        return self.thumbnail_controller.metadata_cache if self.thumbnail_controller else {}

    @property
    def selected_file_paths(self):
        return list(self.selection_controller.selected_paths()) if self.selection_controller else []

    @property
    def copy_selection_order(self):
        return list(self.selection_controller.copy_paths()) if self.selection_controller else []

    def _update_operation_locks(self):
        busy = self.is_loading_thumbnails or self.file_operations.is_busy() or self._closing
        self.ui_manager.set_thumbnail_loading_ui_state(busy)

    def _thumbnail_progress(self, generation, processed, total):
        if generation == self._active_generation and not self._closing:
            self.update_progress_bar(processed, total)

    def _thumbnail_completed(self, generation):
        if generation != self._active_generation or self._closing:
            return
        self.is_loading_thumbnails = False
        self.apply_filters(preserve_selection=True)
        criteria = self.sort_criteria_map[self.current_sort_button_id]
        self.selection_controller.apply_sort(criteria['key_type'], criteria['order'])
        self._update_operation_locks()
        self.statusBar.showMessage("サムネイル読み込み完了", 5000)

    def _file_operation_idle(self):
        self._update_operation_locks()
        self._maybe_finish_close()

    def _maybe_finish_close(self):
        if self._closing and self.thumbnail_controller.is_idle() and not self.file_operations.is_busy():
            QTimer.singleShot(0, self.close)

    def _sync_folder_tree(self, folder_path):
        parent = QDir(folder_path)
        root_path = parent.path()
        if parent.cdUp():
            root_path = parent.path()
        model = self.ui_manager.file_system_model
        view = self.ui_manager.folder_tree_view
        model.setRootPath(root_path)
        view.setRootIndex(model.index(root_path))
        index = model.index(folder_path)
        if index.isValid():
            view.expand(index.parent())
            view.setCurrentIndex(index)
            view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)

    def request_folder_navigation(self, path: str, *, source: str, force_reload: bool = False) -> NavigationResult:
        if self._closing or self.file_operations.is_busy():
            return NavigationResult("busy", "ファイル操作または終了処理中です。")
        try:
            normalized, _ = normalize_folder_path(path)
        except ValueError as exc:
            return NavigationResult("invalid", str(exc))
        try:
            if not os.path.isdir(normalized):
                raise OSError("フォルダが見つかりません。")
            with os.scandir(normalized) as entries:
                next(entries, None)
            if not force_reload and self.current_folder_path and os.path.normcase(normalized) == os.path.normcase(self.current_folder_path):
                return NavigationResult("unchanged")
            if source == "dialog" and self.delete_empty_folders_enabled:
                self._try_delete_empty_subfolders(normalized)
            flags = (QDirIterator.IteratorFlag.Subdirectories if self.recursive_search_enabled
                     else QDirIterator.IteratorFlag.NoIteratorFlags)
            iterator = QDirIterator(normalized, ["*.png", "*.jpg", "*.jpeg", "*.webp"],
                                    QDir.Filter.Files | QDir.Filter.NoSymLinks, flags)
            files = []
            while iterator.hasNext():
                files.append(iterator.next())
            if not os.path.isdir(normalized):
                raise OSError("フォルダが見つかりません。")
        except (OSError, PermissionError) as exc:
            message = f"フォルダを開けません: {exc}"
            self.statusBar.showMessage(message, 5000)
            return NavigationResult("unavailable", message)
        if source == "dialog" and self.initial_folder_sort_setting == SORT_BY_LOAD_ORDER_ALWAYS:
            self.current_sort_button_id = 4
            self._apply_initial_sort_from_settings()
        self.selection_controller.clear()
        self.is_loading_thumbnails = True
        self.current_folder_path = normalized
        self.ui_manager.update_thumbnail_view_sizes()
        self._active_generation = self.thumbnail_controller.replace(files, self.current_thumbnail_size)
        if source != "tree":
            self._sync_folder_tree(normalized)
        self._refresh_favorites_panel()
        self._update_operation_locks()
        if self.thumbnail_controller.waiting_for_previous_load():
            self.statusBar.showMessage("前の読み込みの停止を待っています")
        elif files:
            self.statusBar.showMessage(f"サムネイル読み込み中... 0/{len(files)}")
        else:
            self.statusBar.showMessage("フォルダに画像がありません", 5000)
        return NavigationResult("accepted")

    def _connect_favorites(self):
        panel = self.ui_manager.favorites_panel
        panel.addRequested.connect(self._favorite_add)
        panel.activateRequested.connect(self._favorite_activate)
        panel.removeRequested.connect(self._favorite_remove)
        panel.copyPathRequested.connect(self._favorite_copy_path)
        panel.openInExplorerRequested.connect(self._favorite_open_explorer)
        panel.orderChanged.connect(self._favorite_reorder)
        self._refresh_favorites_panel()

    def _refresh_favorites_panel(self):
        panel = self.ui_manager.favorites_panel
        panel.set_entries(self.favorites.entries())
        key = None
        if self.current_folder_path:
            try:
                _, key = normalize_folder_path(self.current_folder_path)
            except ValueError:
                pass
        panel.set_current_key(key if key and self.favorites.get(key) else None)
        panel.set_can_add(bool(self.current_folder_path) and not self.favorites.get(key))

    def _favorite_feedback(self, result):
        self._refresh_favorites_panel()
        if result.message:
            self.statusBar.showMessage(result.message, 5000)

    def _favorite_add(self):
        self._favorite_feedback(self.favorites.add(self.current_folder_path))

    def _favorite_remove(self, key):
        self._favorite_feedback(self.favorites.remove(key))

    def _favorite_reorder(self, keys):
        self._favorite_feedback(self.favorites.reorder(keys))

    def _favorite_activate(self, key):
        entry = self.favorites.get(key)
        if entry is None:
            self.statusBar.showMessage("お気に入りが見つかりません。", 5000)
        else:
            result = self.request_folder_navigation(entry.path, source="favorite")
            if result.message:
                self.statusBar.showMessage(result.message, 5000)
        self._refresh_favorites_panel()

    def _favorite_copy_path(self, key):
        entry = self.favorites.get(key)
        if entry:
            QApplication.clipboard().setText(entry.path)

    def _favorite_open_explorer(self, key):
        entry = self.favorites.get(key)
        if not entry:
            return
        try:
            if not os.path.isdir(entry.path):
                raise OSError("フォルダが見つかりません。")
            with os.scandir(entry.path) as entries:
                next(entries, None)
            os.startfile(entry.path)
        except OSError as exc:
            self.statusBar.showMessage(f"Explorerで開けません: {exc}", 5000)

    def resizeEvent(self, event: QResizeEvent):
        """Keep the default left panel width limit during window resize."""
        super().resizeEvent(event)
        if self.ui_manager.left_panel_widget_ref:
            self.ui_manager.left_panel_widget_ref.setMaximumWidth(350)

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
