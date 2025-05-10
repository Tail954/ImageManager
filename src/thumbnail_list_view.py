from PyQt6.QtWidgets import QListView, QAbstractItemView
from PyQt6.QtCore import Qt, QItemSelectionModel, pyqtSignal, QModelIndex

class ToggleSelectionListView(QListView):
    # Signal to request metadata display for a given index
    metadata_requested = pyqtSignal(QModelIndex)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.setDragEnabled(False) # アイテム自体のドラッグを無効化
        # SelectItems ensures that selection is based on items, not rows or columns.
        # This is usually the default for IconMode but explicitly setting it can be clearer.
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.pos())
            if index.isValid(): # アイテム上でのクリック
                selection_model = self.selectionModel()
                # QItemSelectionModel.Toggle フラグは、指定されたインデックスの選択状態を反転させる
                # 他のインデックスの選択状態には影響を与えない
                selection_model.select(index, QItemSelectionModel.SelectionFlag.Toggle)
                event.accept() 
                return
            else: # アイテム外（何もないところ）でのクリック
                # 何もしないことで、現在の選択状態を維持する
                event.accept()
                return
        elif event.button() == Qt.MouseButton.RightButton:
            index = self.indexAt(event.pos())
            if index.isValid():
                self.metadata_requested.emit(index)
                event.accept()
                return
        
        # Other mouse buttons are handled by the parent class
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 左ボタンが押された状態でのマウス移動（ドラッグ）の場合、
        # デフォルトのラバーバンド選択などを抑制するためにイベントを消費して何もしない。
        if event.buttons() & Qt.MouseButton.LeftButton:
            # ビューポート内でドラッグが開始された場合のみを対象とするか、
            # より単純に左ボタン押下中の移動はすべて無視するか。
            # ここでは、左ボタン押下中の移動は選択に影響させないようにする。
            event.accept()
            return
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        # QWheelEvent.angleDelta().y() は通常、1ステップあたり120の倍数（15度 * 8）
        # 正の値はユーザーから離れる方向（通常は下にスクロール）、負の値はユーザーに向かう方向（通常は上にスクロール）
        angle = event.angleDelta().y()
        
        # スクロールするピクセル数を決定（この値は調整が必要な場合があります）
        # angleDelta() は1/8度単位なので、8で割ると度数に近い値になる
        # ここでは、1度の回転で約3ピクセルスクロールするように調整（例）
        # マイナスをかけて方向を調整（angleDelta().y()が正なら下にスクロールしたいので、スクロールバーの値は増える）
        pixels_to_scroll = - (angle / 8) * 3 

        scrollbar = self.verticalScrollBar()
        if scrollbar:
            new_value = scrollbar.value() + int(pixels_to_scroll)
            scrollbar.setValue(new_value)
            event.accept() # イベントを処理したことを通知
        else:
            # スクロールバーがない場合は、デフォルトの処理に任せる
            super().wheelEvent(event)

    # selectionChangedシグナルは通常通りMainWindowで処理できる
