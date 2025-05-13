# src/dialog_manager.py
import logging
import os
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QApplication, QDialog

from .settings_dialog import SettingsDialog
from .full_image_dialog import FullImageDialog
from .image_metadata_dialog import ImageMetadataDialog
from .wc_creator_dialog import WCCreatorDialog
from .drop_window import DropWindow
from .constants import (
    APP_SETTINGS_FILE, THUMBNAIL_RIGHT_CLICK_ACTION,
    WC_COMMENT_OUTPUT_FORMAT, METADATA_ROLE, Qt as ConstantsQt # Renamed Qt from constants to avoid clash
)
# Qt from QtCore is used for Qt.ItemDataRole etc.
# ConstantsQt might be used if constants.py defines its own Qt related values, but likely not needed here.

logger = logging.getLogger(__name__)

class DialogManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.settings_dialog_instance = None
        self.full_image_dialog_instance = None
        self.metadata_dialog_instance = None
        self.drop_window_instance = None
        self.wc_creator_dialog_instance = None # モーダルなので毎回生成・破棄

    def open_settings_dialog(self):
        """設定ダイアログを開き、変更を適用する。"""
        if self.settings_dialog_instance is None:
            self.settings_dialog_instance = SettingsDialog(
                current_thumbnail_size=self.main_window.current_thumbnail_size,
                available_thumbnail_sizes=self.main_window.available_sizes,
                current_preview_mode=self.main_window.image_preview_mode,
                current_right_click_action=self.main_window.thumbnail_right_click_action,
                current_wc_comment_format=self.main_window.wc_creator_comment_format,
                parent=self.main_window
            )

        if self.settings_dialog_instance.exec(): # OKボタンが押された場合
            new_preview_mode = self.settings_dialog_instance.get_selected_preview_mode()
            if self.main_window.image_preview_mode != new_preview_mode:
                self.main_window.image_preview_mode = new_preview_mode
                logger.info(f"画像表示モードが変更されました: {self.main_window.image_preview_mode}")

            new_right_click_action = self.settings_dialog_instance.get_selected_right_click_action()
            if self.main_window.thumbnail_right_click_action != new_right_click_action:
                self.main_window.thumbnail_right_click_action = new_right_click_action
                logger.info(f"サムネイル右クリック時の動作が変更されました: {self.main_window.thumbnail_right_click_action}")

            new_wc_comment_format = self.settings_dialog_instance.get_selected_wc_comment_format()
            if self.main_window.wc_creator_comment_format != new_wc_comment_format:
                self.main_window.wc_creator_comment_format = new_wc_comment_format
                logger.info(f"WC Creator コメント形式が変更されました: {self.main_window.wc_creator_comment_format}")

            new_size = self.settings_dialog_instance.get_selected_thumbnail_size()
            reply_ok_for_size_change = True # Assume OK if no confirmation needed or confirmed
            if self.main_window.current_thumbnail_size != new_size:
                if self.main_window.is_loading_thumbnails:
                    QMessageBox.warning(self.main_window, "注意", "サムネイル読み込み中です。完了後に再度お試しください。")
                    reply_ok_for_size_change = False
                else:
                    reply = QMessageBox.question(self.main_window, "サムネイルサイズ変更の確認",
                                                 f"サムネイルサイズを {new_size}px に変更しますか？\n表示中の全サムネイルが再生成されます。\n画像の枚数によっては時間がかかる場合があります。",
                                                 QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                                                 QMessageBox.StandardButton.Cancel)
                    if reply == QMessageBox.StandardButton.Ok:
                        if self.main_window.apply_thumbnail_size_change(new_size):
                            logger.info(f"サムネイルサイズが {new_size}px に変更されました。")
                            # MainWindowのcurrent_thumbnail_sizeはこの時点で更新されているはず
                        else: # apply_thumbnail_size_change が False を返した場合 (例: 読み込み中だったなど)
                            reply_ok_for_size_change = False
                    else: # User cancelled
                        reply_ok_for_size_change = False
            
            # 設定をファイルに保存
            self.main_window.app_settings["image_preview_mode"] = self.main_window.image_preview_mode
            # サムネイルサイズは、実際に適用された(または適用しようとした)新しいサイズを保存
            if self.main_window.current_thumbnail_size != new_size and reply_ok_for_size_change:
                 self.main_window.app_settings["thumbnail_size"] = new_size
            else: # サイズ変更なし、またはキャンセル/失敗した場合は現在の値を保存
                 self.main_window.app_settings["thumbnail_size"] = self.main_window.current_thumbnail_size

            self.main_window.app_settings[THUMBNAIL_RIGHT_CLICK_ACTION] = self.main_window.thumbnail_right_click_action
            self.main_window.app_settings[WC_COMMENT_OUTPUT_FORMAT] = self.main_window.wc_creator_comment_format
            self.main_window._write_app_settings_file()
        self.settings_dialog_instance = None


    def open_full_image_dialog(self, proxy_index):
        """サムネイルのダブルクリックに応じてFullImageDialogを開くまたは更新する。"""
        if not proxy_index.isValid(): return
        source_index = self.main_window.filter_proxy_model.mapToSource(proxy_index)
        item = self.main_window.source_thumbnail_model.itemFromIndex(source_index)
        if not item: return
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path: return

        logger.info(f"FullImageDialog表示要求: {file_path}")

        visible_image_paths = []
        for row in range(self.main_window.filter_proxy_model.rowCount()):
            proxy_idx_loop = self.main_window.filter_proxy_model.index(row, 0)
            source_idx_loop = self.main_window.filter_proxy_model.mapToSource(proxy_idx_loop)
            item_loop = self.main_window.source_thumbnail_model.itemFromIndex(source_idx_loop)
            if item_loop:
                visible_image_paths.append(item_loop.data(Qt.ItemDataRole.UserRole))

        current_idx_in_visible_list = -1
        if file_path in visible_image_paths:
            current_idx_in_visible_list = visible_image_paths.index(file_path)
        else:
             logger.error(f"ダブルクリックされたファイルパス {file_path} が表示中のアイテムリストに見つかりません。")
             return

        try:
            if self.full_image_dialog_instance is None:
                logger.debug(f"FullImageDialogの新規インスタンスを作成します。モード: {self.main_window.image_preview_mode}")
                self.full_image_dialog_instance = FullImageDialog(
                    visible_image_paths, current_idx_in_visible_list,
                    preview_mode=self.main_window.image_preview_mode, parent=self.main_window
                )
                self.full_image_dialog_instance.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                self.full_image_dialog_instance.finished.connect(self._on_full_image_dialog_finished)
                self.full_image_dialog_instance.show()
            else:
                logger.debug(f"既存のFullImageDialogインスタンスを更新します。モード: {self.main_window.image_preview_mode}")
                self.full_image_dialog_instance.update_image(visible_image_paths, current_idx_in_visible_list)
        except Exception as e:
            logger.error(f"画像ダイアログの表示・更新中にエラー ({file_path}): {e}", exc_info=True)
            QMessageBox.critical(self.main_window, "画像表示エラー", f"画像ダイアログの表示・更新中にエラーが発生しました:\n{e}")
            if self.full_image_dialog_instance:
                self.full_image_dialog_instance.close()
                self.full_image_dialog_instance = None

    def _on_full_image_dialog_finished(self):
        """FullImageDialogが閉じたときの処理。"""
        # finishedシグナルはQDialogインスタンス自身をsenderとして送出しないため、
        # self.sender()ではなく、インスタンス変数を直接比較・クリアする
        if self.full_image_dialog_instance: # インスタンスが存在する場合のみ
            logger.debug("FullImageDialogが閉じられました。インスタンス参照をクリアします。")
            self.full_image_dialog_instance = None


    def open_metadata_dialog(self, proxy_index):
        """指定されたインデックスのアイテムのメタデータダイアログを開く。"""
        if not proxy_index.isValid():
            logger.debug("open_metadata_dialog: 無効なプロキシインデックスを受け取りました。")
            return
        source_index = self.main_window.filter_proxy_model.mapToSource(proxy_index)
        item = self.main_window.source_thumbnail_model.itemFromIndex(source_index)
        if not item:
            logger.debug(f"open_metadata_dialog: ソースインデックス {source_index.row()},{source_index.column()} からアイテムを取得できませんでした。")
            return
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path:
            logger.warning(f"open_metadata_dialog: プロキシインデックス {proxy_index.row()},{proxy_index.column()} のアイテムにファイルパスが関連付けられていません。")
            return

        data_from_item = item.data(METADATA_ROLE)
        final_metadata_to_show = {}
        if isinstance(data_from_item, dict):
            final_metadata_to_show = data_from_item
        else:
            cached_metadata = self.main_window.metadata_cache.get(file_path)
            if isinstance(cached_metadata, dict):
                final_metadata_to_show = cached_metadata
            else:
                logger.warning(f"メタデータ {file_path} がキャッシュに見つからないか、辞書型ではありません。タイプ: {type(cached_metadata)}。空の辞書を使用します。")
        if not isinstance(final_metadata_to_show, dict):
            logger.error(f"致命的 - final_metadata_to_show が辞書型ではありません {file_path}! タイプ: {type(final_metadata_to_show)}。空の辞書に強制します。")
            final_metadata_to_show = {}

        self._show_specific_metadata_dialog(final_metadata_to_show, file_path)

    def _show_specific_metadata_dialog(self, metadata_dict, item_file_path_for_debug=None):
        """実際にImageMetadataDialogを表示または更新する内部メソッド。"""
        if self.metadata_dialog_instance is None:
            self.metadata_dialog_instance = ImageMetadataDialog(metadata_dict, self.main_window, item_file_path_for_debug)
            self.metadata_dialog_instance.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self.metadata_dialog_instance.finished.connect(self._on_metadata_dialog_finished)
            if self.main_window.metadata_dialog_last_geometry:
                 try:
                     screen_rect = QApplication.primaryScreen().availableGeometry()
                     if screen_rect.intersects(self.main_window.metadata_dialog_last_geometry):
                         self.metadata_dialog_instance.setGeometry(self.main_window.metadata_dialog_last_geometry)
                 except Exception: logger.warning("スクリーンジオメトリを取得できませんでした。最後のダイアログジオメトリをチェックなしで復元します。")
            self.metadata_dialog_instance.show()
        else:
            self.metadata_dialog_instance.update_metadata(metadata_dict, item_file_path_for_debug)
            if not self.metadata_dialog_instance.isVisible(): self.metadata_dialog_instance.show()
        self.metadata_dialog_instance.raise_()
        self.metadata_dialog_instance.activateWindow()

    def _on_metadata_dialog_finished(self, result):
        # finishedシグナルはQDialogインスタンス自身をsenderとして送出しないため、
        # self.sender()ではなく、インスタンス変数を直接比較・クリアする
        if self.metadata_dialog_instance: # インスタンスが存在する場合のみ
             # sender_dialog = self.main_window.sender() # これは不要
             # if sender_dialog == self.metadata_dialog_instance: # これも不要
            if isinstance(self.metadata_dialog_instance, QDialog): # 型チェックは念のため
                 self.main_window.metadata_dialog_last_geometry = self.metadata_dialog_instance.geometry()
                 logger.debug(f"メタデータダイアログが閉じられました。ジオメトリを保存しました: {self.main_window.metadata_dialog_last_geometry}")
            self.metadata_dialog_instance = None


    def toggle_drop_window(self):
        """ドラッグアンドドロップウィンドウの表示/非表示を切り替える。"""
        if self.drop_window_instance is None:
            logger.info("DropWindowのインスタンスを初めて作成します。")
            self.drop_window_instance = DropWindow(dialog_manager=self)

        if self.drop_window_instance.isVisible():
            logger.debug("DropWindowを非表示にします。")
            self.drop_window_instance.hide()
        else:
            logger.debug("DropWindowを表示します。")
            self.drop_window_instance.show()

    def show_metadata_for_dropped_file(self, file_path: str):
        """DropWindowから呼び出され、指定されたファイルのメタデータを表示する。"""
        logger.info(f"DropWindowからファイル '{file_path}' のメタデータ表示要求。")
        if not os.path.isfile(file_path):
            logger.warning(f"指定されたパス '{file_path}' はファイルではありません。メタデータを表示できません。")
            QMessageBox.warning(self.main_window, "エラー", f"指定されたパスはファイルではありません:\n{file_path}")
            return

        metadata_to_show = self.main_window.metadata_cache.get(file_path)

        if metadata_to_show is None:
            logger.info(f"メタデータキャッシュにないため、 '{file_path}' から抽出します。")
            from .metadata_utils import extract_image_metadata
            metadata_to_show = extract_image_metadata(file_path)
            self.main_window.metadata_cache[file_path] = metadata_to_show
            logger.debug(f"ファイル '{file_path}' からメタデータを抽出し、キャッシュしました。")
        else:
            logger.debug(f"ファイル '{file_path}' のメタデータをキャッシュから使用します。")

        if not isinstance(metadata_to_show, dict):
             logger.error(f"表示すべきメタデータが辞書型ではありません (型: {type(metadata_to_show)})。ファイル: {file_path}")
             metadata_to_show = {"Error": f"内部エラー: メタデータ形式不正。"}

        self._show_specific_metadata_dialog(metadata_to_show, item_file_path_for_debug=file_path)

    def open_wc_creator_dialog(self):
        """ワイルドカード作成ダイアログを開く。"""
        logger.info("ワイルドカード作成ツールを起動します。")

        selected_proxy_indexes = self.main_window.thumbnail_view.selectionModel().selectedIndexes()
        if not selected_proxy_indexes:
            QMessageBox.information(self.main_window, "情報", "作成対象の画像をサムネイル一覧から選択してください。")
            return

        selected_files_for_wc = []
        metadata_for_wc = []
        processed_paths = set()

        for proxy_idx in selected_proxy_indexes:
            if proxy_idx.column() == 0:
                source_idx = self.main_window.filter_proxy_model.mapToSource(proxy_idx)
                item = self.main_window.source_thumbnail_model.itemFromIndex(source_idx)
                if item:
                    file_path = item.data(Qt.ItemDataRole.UserRole)
                    if file_path and file_path not in processed_paths:
                        metadata = item.data(METADATA_ROLE)
                        if not isinstance(metadata, dict):
                            metadata = self.main_window.metadata_cache.get(file_path)
                        if not isinstance(metadata, dict):
                            logger.warning(f"WC Creator用メタデータ: {file_path} のキャッシュが見つからないため、再抽出します。")
                            from .metadata_utils import extract_image_metadata
                            metadata = extract_image_metadata(file_path)
                            self.main_window.metadata_cache[file_path] = metadata
                        
                        if isinstance(metadata, dict):
                            selected_files_for_wc.append(file_path)
                            metadata_for_wc.append(metadata)
                            processed_paths.add(file_path)
                        else:
                            logger.error(f"WC Creator: {file_path} のメタデータ取得に失敗しました。スキップします。")

        if not selected_files_for_wc:
            QMessageBox.warning(self.main_window, "エラー", "有効な画像データが見つかりませんでした。")
            return

        logger.info(f"{len(selected_files_for_wc)} 個の画像をWC Creatorに渡します。")
        wc_dialog = WCCreatorDialog(selected_files_for_wc, metadata_for_wc, self.main_window.wc_creator_comment_format, self.main_window)
        wc_dialog.exec()
        logger.info("プロンプト整形ツールを閉じました。")
