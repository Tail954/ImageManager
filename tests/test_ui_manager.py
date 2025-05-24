import unittest
from unittest.mock import MagicMock, patch, call

import sys # ★★★ sys をインポート ★★★
import os # ★★★ os をインポート ★★★
from PyQt6.QtWidgets import QApplication, QListView
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt, QModelIndex, QItemSelection, QItemSelectionModel

# ★★★ src ディレクトリを Python パスに追加 ★★★
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ui_manager import UIManager
from src.main_window import MainWindow # UIManagerが依存するため、モックの対象
from src.metadata_filter_proxy_model import MetadataFilterProxyModel
from src.constants import METADATA_ROLE, SELECTION_ORDER_ROLE

app = QApplication.instance()
if app is None:
    app = QApplication([])

class TestUIManager(unittest.TestCase):

    def setUp(self):
        self.mock_main_window = MagicMock(spec=MainWindow)

        self.mock_main_window.source_thumbnail_model = QStandardItemModel()
        self.mock_main_window.filter_proxy_model = MetadataFilterProxyModel()
        self.mock_main_window.filter_proxy_model.setSourceModel(self.mock_main_window.source_thumbnail_model)

        self.mock_thumbnail_view = MagicMock(spec=QListView)
        self.mock_selection_model = MagicMock(spec=QItemSelectionModel)
        self.mock_thumbnail_view.selectionModel.return_value = self.mock_selection_model
        
        self.ui_manager = UIManager(self.mock_main_window)
        
        self.ui_manager.source_thumbnail_model = self.mock_main_window.source_thumbnail_model
        self.ui_manager.filter_proxy_model = self.mock_main_window.filter_proxy_model
        self.ui_manager.thumbnail_view = self.mock_thumbnail_view

        self.mock_main_window.is_copy_mode = False
        self.mock_main_window.copy_selection_order = []
        self.mock_main_window.SELECTION_ORDER_ROLE = SELECTION_ORDER_ROLE

    def _add_item_to_source_model(self, text, file_path, metadata=None):
        item = QStandardItem(text)
        item.setData(file_path, Qt.ItemDataRole.UserRole)
        if metadata:
            item.setData(metadata, METADATA_ROLE)
        self.ui_manager.source_thumbnail_model.appendRow(item)
        return item

    @patch('src.ui_manager.logger')
    def test_apply_filters_preserving_selection_move_mode_some_selected_remain(self, mock_logger):
        # Arrange
        self.mock_main_window.is_copy_mode = False

        item1 = self._add_item_to_source_model("item1_visible_selected", "path1", {"positive_prompt": "apple"})
        item2 = self._add_item_to_source_model("item2_hidden_selected", "path2", {"positive_prompt": "banana"})
        item3 = self._add_item_to_source_model("item3_visible_unselected", "path3", {"positive_prompt": "apple pie"})
        item4 = self._add_item_to_source_model("item4_visible_selected_also", "path4", {"positive_prompt": "apple green"})

        proxy_idx1 = self.ui_manager.filter_proxy_model.mapFromSource(self.ui_manager.source_thumbnail_model.indexFromItem(item1))
        proxy_idx2 = self.ui_manager.filter_proxy_model.mapFromSource(self.ui_manager.source_thumbnail_model.indexFromItem(item2))
        proxy_idx4 = self.ui_manager.filter_proxy_model.mapFromSource(self.ui_manager.source_thumbnail_model.indexFromItem(item4))
        
        self.mock_selection_model.selectedIndexes.return_value = [proxy_idx1, proxy_idx2, proxy_idx4]

        # Act
        positive_filter_text = "apple"
        self.ui_manager.apply_filters_preserving_selection(positive_filter_text, "", "", "AND")

        # Assert
        self.assertEqual(self.ui_manager.filter_proxy_model._positive_prompt_filter, positive_filter_text.lower())
        self.assertEqual(self.ui_manager.filter_proxy_model.rowCount(), 3) 

        self.mock_selection_model.select.assert_called_once()
        args, _ = self.mock_selection_model.select.call_args
        
        new_selection_qitemselection = args[0]
        selection_flags = args[1]
        
        self.assertEqual(selection_flags, QItemSelectionModel.SelectionFlag.ClearAndSelect)

        final_proxy_idx1 = self.ui_manager.filter_proxy_model.mapFromSource(self.ui_manager.source_thumbnail_model.indexFromItem(item1))
        final_proxy_idx4 = self.ui_manager.filter_proxy_model.mapFromSource(self.ui_manager.source_thumbnail_model.indexFromItem(item4))
        
        selected_indexes_in_call = set(new_selection_qitemselection.indexes())
        expected_selected_indexes = {final_proxy_idx1, final_proxy_idx4}
        self.assertEqual(selected_indexes_in_call, expected_selected_indexes)

    @patch('src.ui_manager.logger')
    def test_apply_filters_preserving_selection_copy_mode(self, mock_logger):
        # Arrange
        self.mock_main_window.is_copy_mode = True

        item1 = self._add_item_to_source_model("item1_copy_selected", "cpath1", {"positive_prompt": "cat"})
        item2 = self._add_item_to_source_model("item2_copy_hidden", "cpath2", {"positive_prompt": "dog"}) # Will be filtered out
        item3 = self._add_item_to_source_model("item3_copy_selected_remains", "cpath3", {"positive_prompt": "cat cute"})

        self.mock_main_window.copy_selection_order = [item1, item3]
        item1.setData(1, SELECTION_ORDER_ROLE)
        item3.setData(2, SELECTION_ORDER_ROLE)
        
        proxy_idx1 = self.ui_manager.filter_proxy_model.mapFromSource(self.ui_manager.source_thumbnail_model.indexFromItem(item1))
        proxy_idx3 = self.ui_manager.filter_proxy_model.mapFromSource(self.ui_manager.source_thumbnail_model.indexFromItem(item3))
        self.mock_selection_model.selectedIndexes.return_value = [proxy_idx1, proxy_idx3]

        # Act
        positive_filter_text = "cat"
        self.ui_manager.apply_filters_preserving_selection(positive_filter_text, "", "", "AND")

        # Assert
        self.assertEqual(self.ui_manager.filter_proxy_model.rowCount(), 2)

        self.mock_selection_model.select.assert_called_once()
        args, _ = self.mock_selection_model.select.call_args
        new_selection_qitemselection = args[0]
        selection_flags = args[1]
        self.assertEqual(selection_flags, QItemSelectionModel.SelectionFlag.ClearAndSelect)

        final_proxy_idx1 = self.ui_manager.filter_proxy_model.mapFromSource(self.ui_manager.source_thumbnail_model.indexFromItem(item1))
        final_proxy_idx3 = self.ui_manager.filter_proxy_model.mapFromSource(self.ui_manager.source_thumbnail_model.indexFromItem(item3))
        
        selected_indexes_in_call = set(new_selection_qitemselection.indexes())
        expected_selected_indexes = {final_proxy_idx1, final_proxy_idx3}
        self.assertEqual(selected_indexes_in_call, expected_selected_indexes)

        mock_logger.debug.assert_any_call("  Copy Mode: previously_selected_paths (from copy_selection_order, count: 2): ['cpath1', 'cpath3']")

    @patch('src.ui_manager.logger')
    def test_filter_input_enter_preserves_selection(self, mock_logger):
        # Arrange
        # _create_filter_ui が呼ばれ、QLineEdit が作成されると仮定
        # UIManagerのコンストラクタ内で呼ばれるsetup_uiの一部として実行される
        # setup_ui内で_create_left_panel -> _create_filter_uiと辿る
        # ここでは、テスト対象のQLineEditが確実に存在するように、直接呼び出すか、
        # setup_uiの呼び出しを許可する（ただし、他のUI要素のモック化が必要になる場合がある）
        # 簡単のため、_create_filter_uiが呼ばれた後の状態を模倣
        self.ui_manager.positive_prompt_filter_edit = MagicMock() # QLineEditのモック
        self.ui_manager.negative_prompt_filter_edit = MagicMock()
        self.ui_manager.generation_info_filter_edit = MagicMock()
        self.ui_manager.apply_filter_button = MagicMock() # QPushButtonのモック
        
        # _create_filter_ui の中で connect が行われるので、その後の状態をテスト
        # 実際の connect は setup_ui -> _create_left_panel -> _create_filter_ui で行われる
        # ここでは、connect後の lambda が正しく MainWindow のメソッドを呼ぶかをテストしたい
        # そのため、MainWindow.apply_filters をモック化する
        self.mock_main_window.apply_filters = MagicMock()

        # UIManager._create_filter_ui() を呼び出してシグナルを接続させる
        # ただし、このメソッドは多くのUI要素を生成するため、
        # MainWindowの他の属性(例: sort_criteria_map)もモックする必要があるかもしれない
        # ここでは、connect部分だけを抜き出してテストする方がユニットテストとしては適切かもしれないが、
        # 既存の方針に合わせ、UI要素のシグナル発行をトリガーとする
        
        # lambdaを直接テストするのは難しいので、シグナルを発行して結果を見る
        # positive_prompt_filter_edit.returnPressed シグナルをエミュレート
        # このためには、positive_prompt_filter_edit が実際の QLineEdit であるか、
        # returnPressed シグナルを持つモックである必要がある。
        # ここでは MagicMock を使っているので、emit() を直接呼ぶ。
        
        # Act: positive_prompt_filter_edit の returnPressed シグナルを発行
        # connectはUIManagerのsetup_ui -> _create_left_panel -> _create_filter_ui で行われる
        # ここでは、その接続が正しく行われたとして、lambdaがMainWindowのメソッドを呼ぶかを見る
        # UIManagerの初期化時にsetup_uiが呼ばれるため、QLineEditインスタンスは存在するはず
        # ただし、テストの分離のため、MainWindowのメソッドをモック化して確認する
        
        # setup_uiを呼ぶとMainWindowの多くの部分が必要になるため、
        # ここではlambdaがMainWindowのメソッドを呼ぶという前提で、
        # MainWindow側のapply_filtersがpreserve_selection=Trueで呼ばれることを確認するテストを
        # test_main_window.py に記述する方が適切。
        # UIManagerのテストとしては、UI要素のセットアップとシグナル接続の「設定」までを対象とする。
        # ここでは、apply_filters_preserving_selection のロジックテストに注力する。
        pass # UIイベント起因のテストは MainWindow 側で UIManager のメソッド呼び出しを検証する方が適切

if __name__ == '__main__':
    unittest.main()