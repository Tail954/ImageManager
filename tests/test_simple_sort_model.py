import sys
from PyQt6.QtCore import QSortFilterProxyModel, Qt, QModelIndex
from PyQt6.QtGui import QStandardItemModel, QStandardItem # QStandardItemModelとQStandardItemをQtGuiからインポート
from PyQt6.QtWidgets import QApplication, QListView, QVBoxLayout, QWidget, QPushButton

# シンプルなテスト用のカスタムプロキシモデル
class SimpleSortProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sort_order = Qt.SortOrder.AscendingOrder
        self.setDynamicSortFilter(False) # 明示的にFalseに設定
        # self.setSortRole(Qt.ItemDataRole.DisplayRole) # 必要に応じてソートロールを設定

    def set_custom_sort_order(self, order: Qt.SortOrder):
        print(f"SimpleSortProxyModel.set_custom_sort_order: Setting internal order to {order}")
        self._sort_order = order
        
        current_sort_column = self.sortColumn()
        if current_sort_column == -1: # まだソート列が設定されていない場合
            current_sort_column = 0
        
        # sort() を直接呼び出す
        # この時、SimpleSortProxyModelのsortメソッドはオーバーライドしないでおくか、
        # オーバーライドする場合は super().sort() を適切に呼び、
        # beginResetModel/endResetModel を発行する
        print(f"SimpleSortProxyModel.set_custom_sort_order: Calling self.sort({current_sort_column}, order_to_use={self._sort_order})")
        self.sort(current_sort_column, self._sort_order) # order引数には更新された_sort_orderを渡す

    def lessThan(self, source_left: QModelIndex, source_right: QModelIndex) -> bool:
        left_data = self.sourceModel().data(source_left)
        right_data = self.sourceModel().data(source_right)
        
        print(f"SimpleSortProxyModel.lessThan: Comparing '{left_data}' and '{right_data}' with order {self._sort_order}")

        if self._sort_order == Qt.SortOrder.AscendingOrder:
            result = left_data < right_data
        else:
            result = left_data > right_data
        print(f"SimpleSortProxyModel.lessThan: Result = {result}")
        return result

    # class SimpleSortProxyModel の sort メソッドのオーバーライドは一旦コメントアウトするか削除して、
    # QSortFilterProxyModel のデフォルトの sort 処理に任せてみる。
    # def sort(self, column: int, order: Qt.SortOrder) -> None:
    #     print(f"SimpleSortProxyModel.sort() OVERRIDE called. Column: {column}, Order from argument: {order}, Internal order: {self._sort_order}")
    #     # 内部のソート順を優先する
    #     actual_order_to_use = self._sort_order
    #     print(f"SimpleSortProxyModel.sort() OVERRIDE: Emitting beginResetModel. Sorting with column {column} and order {actual_order_to_use}")
    #     self.beginResetModel()
    #     super().sort(column, actual_order_to_use) # 内部のソート順を使用
    #     self.endResetModel()
    #     print(f"SimpleSortProxyModel.sort() OVERRIDE: Emitted endResetModel. Proxy sortColumn: {self.sortColumn()}, sortOrder: {self.sortOrder()}")


# テスト用のシンプルなアプリケーション
class TestApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.layout = QVBoxLayout(self)

        # ソースモデルの作成
        self.source_model = QStandardItemModel()
        items = ["Charlie", "Alpha", "Bravo", "Delta"]
        for item_text in items:
            self.source_model.appendRow(QStandardItem(item_text))

        # プロキシモデルの作成と設定
        self.proxy_model = SimpleSortProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        # 初期ソート（昇順）
        # self.proxy_model.sort(0, Qt.SortOrder.AscendingOrder) # 初期ソートは invalidateSort または sort で行う

        # リストビューの作成
        self.list_view = QListView()
        self.list_view.setModel(self.proxy_model)
        self.layout.addWidget(self.list_view)

        # ソート切り替えボタン
        self.asc_button = QPushButton("Sort Ascending")
        self.asc_button.clicked.connect(self.sort_ascending)
        self.layout.addWidget(self.asc_button)

        self.desc_button = QPushButton("Sort Descending")
        self.desc_button.clicked.connect(self.sort_descending)
        self.layout.addWidget(self.desc_button)
        
        self.initial_sort_button = QPushButton("Initial Sort (Proxy Asc)")
        self.initial_sort_button.clicked.connect(self.initial_sort)
        self.layout.addWidget(self.initial_sort_button)

        self.setWindowTitle('Simple Sort Test')
        self.setGeometry(300, 300, 300, 200)
        self.show()

        # 初期表示のために一度ソートを適用
        print("Applying initial sort (Ascending by default in proxy's _sort_order)")
        self.proxy_model.set_custom_sort_order(Qt.SortOrder.AscendingOrder) # これで invalidateSort() が呼ばれる

    def sort_ascending(self):
        print("--- Sort Ascending Clicked ---")
        self.proxy_model.set_custom_sort_order(Qt.SortOrder.AscendingOrder)
        # self.proxy_model.sort(0, Qt.SortOrder.AscendingOrder) # sortを直接呼ぶ場合

    def sort_descending(self):
        print("--- Sort Descending Clicked ---")
        self.proxy_model.set_custom_sort_order(Qt.SortOrder.DescendingOrder)
        # self.proxy_model.sort(0, Qt.SortOrder.DescendingOrder) # sortを直接呼ぶ場合
        
    def initial_sort(self):
        print("--- Initial Sort Button Clicked (Proxy Asc) ---")
        # プロキシモデルの内部状態に基づいてソートをトリガー
        # QSortFilterProxyModelのsortメソッドは、ビューやユーザー操作から呼び出されることを想定している
        # プログラム的にソートを更新する場合、invalidateSort()が推奨されることが多い
        # または、setSortOrder/setSortColumnの後にsort(column)を呼ぶ
        # ここでは、カスタムプロキシのset_custom_sort_order経由でinvalidateSortを呼ぶ
        self.proxy_model.set_custom_sort_order(Qt.SortOrder.AscendingOrder)


def main():
    app = QApplication(sys.argv)
    ex = TestApp()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
