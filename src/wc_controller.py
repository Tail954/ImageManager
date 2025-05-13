import os
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

class WCController(QObject):
    """ワイルドカードコントローラークラス"""
    
    status_updated = pyqtSignal(str)  # ステータス更新シグナル
    
    def __init__(self):
        super().__init__()
        
    def load_image_data(self, file_path):
        """画像データを読み込む
        
        Args:
            file_path (str): 画像ファイルのパス
            
        Returns:
            bool: 読み込み成功可否
        """
        try:
            # QImageを明示的に呼び出す
            image = QImage()
            loaded = image.load(file_path)
            if not loaded or image.isNull():
                self.status_updated.emit(f"画像読み込み失敗: {os.path.basename(file_path)}")
                return False
            return True
        except Exception as e:
            self.status_updated.emit(f"画像読み込みエラー: {str(e)}")
            return False
            
    def update_status(self, message):
        """ステータスを更新
        
        Args:
            message (str): 表示するメッセージ
        """
        self.status_updated.emit(message)
