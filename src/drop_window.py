# src/drop_window.py
import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QUrl  # QUrl を明示的にインポート
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QDragMoveEvent, QScreen # QScreenもインポート

from .constants import IMAGE_EXTENSIONS # Import from constants

logger = logging.getLogger(__name__)

class DropWindow(QWidget):
    """
    画像ファイルのドラッグ＆ドロップを受け付け、
    メインウィンドウ経由でメタデータを表示するウィンドウ。
    """
    def __init__(self, dialog_manager): # ★引数を dialog_manager に変更
        """
        コンストラクタ

        Args:
            dialog_manager (DialogManager): DialogManager のインスタンス参照
                                            show_metadata_for_dropped_file メソッドを持つことを期待。
        """
        super().__init__()
        if not hasattr(dialog_manager, 'show_metadata_for_dropped_file'):
            logger.error("dialog_manager に show_metadata_for_dropped_file メソッドが存在しません。")
            # raise AttributeError("dialog_manager に show_metadata_for_dropped_file メソッドが存在しません。")
        self.dialog_manager = dialog_manager # ★dialog_manager を保持
        self.initUI()
        self.setAcceptDrops(True)

    def initUI(self):
        """UIの初期化"""
        self.setWindowTitle("画像ドロップ")
        self.setFixedSize(230, 170) # 少しだけサイズを調整

        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.label = QLabel("ここに画像ファイルを\nドロップしてください")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.hide) # ウィンドウを非表示にする
        layout.addWidget(self.close_button)

        self.setLayout(layout)

    def move_to_bottom_right(self):
        """ウィンドウを画面の右下に移動する"""
        try:
            primary_screen = QApplication.primaryScreen()
            if primary_screen:
                screen_geometry = primary_screen.availableGeometry()
                # ウィンドウ自身のサイズを取得
                # self.geometry() はウィンドウが表示されていないと正しい値を返さないことがあるため、
                # self.sizeHint() や setFixedSize で設定した値を使う方が確実な場合がある。
                # ここでは setFixedSize を使用しているので、self.width() と self.height() で問題ない。
                window_width = self.width()
                window_height = self.height()

                if window_width == 0 or window_height == 0: # まだサイズが確定していない場合を考慮
                    # initUIで設定した固定サイズを使用
                    fixed_size = self.size() # setFixedSize 後のサイズ
                    window_width = fixed_size.width()
                    window_height = fixed_size.height()


                margin = 15
                target_x = screen_geometry.x() + screen_geometry.width() - window_width - margin
                target_y = screen_geometry.y() + screen_geometry.height() - window_height - margin
                self.move(target_x, target_y)
            else:
                logger.warning("プライマリスクリーンが見つかりませんでした。ウィンドウ位置を調整できません。")
        except Exception as e:
            logger.error(f"画面右下への移動中にエラーが発生しました: {e}", exc_info=True)

    def _is_valid_image_file(self, file_path: str) -> bool:
        """指定されたパスが有効な画像ファイルかを確認するヘルパーメソッド"""
        if not file_path or not isinstance(file_path, str):
            return False
        if os.path.isfile(file_path):
            _, ext = os.path.splitext(file_path)
            if ext.lower() in IMAGE_EXTENSIONS:
                return True
        return False

    def dragEnterEvent(self, event: QDragEnterEvent):
        """ファイルがウィンドウ上にドラッグされたときのイベント"""
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            # 複数のURLがあっても最初のURLのみをチェック
            url = mime_data.urls()[0]
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if self._is_valid_image_file(file_path):
                    event.acceptProposedAction()
                    self.label.setText("ドロップしてメタデータを表示...")
                    return
        event.ignore()
        self.label.setText("ここに画像ファイルを\nドロップしてください") # リセット

    def dragMoveEvent(self, event: QDragMoveEvent):
        """ファイルがウィンドウ上でドラッグ移動中のイベント"""
        # dragEnterEvent と同様のロジックでイベントを受け入れるか判断
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            url = mime_data.urls()[0]
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if self._is_valid_image_file(file_path):
                    event.acceptProposedAction()
                    return
        event.ignore()


    def dragLeaveEvent(self, event): # event の型ヒントは QDragLeaveEvent だが、PyQt6では汎用的に QEvent
        """ドラッグがウィンドウから離れたときのイベント"""
        self.label.setText("ここに画像ファイルを\nドロップしてください")
        event.accept()

    def dropEvent(self, event: QDropEvent):
        """ファイルがウィンドウ上にドロップされたときのイベント"""
        mime_data = event.mimeData()
        original_text = "ここに画像ファイルを\nドロップしてください"
        success_text = "メタデータを処理中です..." # 即時表示ではなく処理中を示す
        failure_text_generic = "メタデータ表示に失敗しました。"
        failure_text_not_image = "画像ファイルではありません。"
        failure_text_not_local = "ローカルファイルではありません。"
        failure_text_no_urls = "無効なデータです。"
        current_label_text = original_text

        try:
            if mime_data.hasUrls():
                url = mime_data.urls()[0] # 最初のファイルのみを対象とする仕様
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if self._is_valid_image_file(file_path):
                        logger.info(f"画像ファイルがドロップされました: {file_path}")
                        self.label.setText(success_text) # 処理中であることをユーザーにフィードバック
                        QApplication.processEvents() # ラベルの更新を即時反映

                        # DialogManagerのメソッドを呼び出してメタデータ表示を依頼
                        self.dialog_manager.show_metadata_for_dropped_file(file_path) # ★呼び出し先を変更
                        # MainWindow側の処理結果によってラベルを変えるのが理想だが、
                        # DropWindow側では成功したと仮定してメッセージを出すか、
                        # MainWindowからコールバック等で結果を受け取る必要がある。
                        # ここでは呼び出し成功＝処理開始とみなし、一定時間後に元に戻す。
                        QTimer.singleShot(2500, lambda: self.label.setText(original_text))
                        event.acceptProposedAction()
                        return # 処理成功
                    else:
                        logger.warning(f"ドロップされたファイルは有効な画像ではありません: {file_path}")
                        current_label_text = failure_text_not_image
                else:
                    logger.warning(f"ドロップされたURLはローカルファイルではありません: {url.toString()}")
                    current_label_text = failure_text_not_local
            else:
                logger.warning("ドロップされたデータにURLが含まれていませんでした。")
                current_label_text = failure_text_no_urls
        except Exception as e:
            logger.exception("dropEventでのメタデータ表示処理中に予期せぬエラーが発生しました。")
            current_label_text = failure_text_generic
        finally:
            # 成功時は上でreturnしているので、ここに来るのは失敗ケースか、
            # 将来的に成功時もここに到達するようなロジック変更があった場合。
            if current_label_text != original_text and self.label.text() != success_text : # まだメッセージが更新されていなければ更新
                 self.label.setText(current_label_text)
                 QTimer.singleShot(3500, lambda: self.label.setText(original_text)) # エラーメッセージは少し長めに表示
            elif self.label.text() != success_text: # 何らかの理由で処理中にラベルが戻ってしまった場合
                self.label.setText(original_text)

        event.ignore() # ここに到達した場合は何らかの理由で処理が完了しなかった

    def closeEvent(self, event): # event の型ヒントは QCloseEvent
        """ウィンドウが閉じられるときのイベント（実際には非表示になる）"""
        self.hide()  # ウィンドウを非表示にする
        event.accept() # closeイベント自体は受け入れる

    def showEvent(self, event): # event の型ヒントは QShowEvent
        """ウィンドウが表示される直前のイベント"""
        super().showEvent(event) # 親クラスのshowEventを呼び出す
        self.move_to_bottom_right() # 表示されるたびに右下に移動
        self.label.setText("ここに画像ファイルを\nドロップしてください") # 表示時にラベルをリセット

    # showメソッドのオーバーライドは不要、showEventで対応。
    # def show(self):
    #     """ウィンドウを表示する際に、画面右下に配置する"""
    #     super().show()
    #     # self.move_to_bottom_right() # showEventに移動
    #     # self.label.setText("ここに画像ファイルを\nドロップしてください") # showEventに移動