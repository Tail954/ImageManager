import unittest # unittest を使用するように変更
import os # os をインポート
import time # time をインポート
from PyQt6.QtWidgets import QApplication # QApplication をインポート
from PyQt6.QtCore import Qt, QModelIndex, QVariant # QModelIndex, QVariant をインポート
from PyQt6.QtGui import QStandardItemModel, QStandardItem # QStandardItemModel, QStandardItem をインポート

# Ensure src directory is in Python path for imports
import sys # sys をインポート
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.metadata_filter_proxy_model import MetadataFilterProxyModel
from src.metadata_filter_proxy_model import METADATA_ROLE # METADATA_ROLE を metadata_filter_proxy_model からインポート

app = None
def setUpModule():
    global app
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

def tearDownModule():
    global app
    if app is not None:
        # app.quit() # QApplication.quit() はテスト全体を終了させてしまう可能性がある
        app = None

class TestMetadataFilterProxyModel(unittest.TestCase):
    def setUp(self):
        self.source_model = QStandardItemModel()
        self.proxy_model = MetadataFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)

        # テストデータ用のダミーファイルパスとメタデータ
        self.test_data_dir = os.path.join(os.path.dirname(__file__), "test_data", "proxy_model_sort")
        os.makedirs(self.test_data_dir, exist_ok=True)

        self.files_info = [
            {"name": "c_old.png", "timestamp_offset": 0, "positive": "apple banana", "negative": "orange", "generation": "steps 10"}, # oldest
            {"name": "a_new.jpg", "timestamp_offset": 10, "positive": "apple", "negative": "sky", "generation": "steps 20"},        # newest
            {"name": "b_mid.webp", "timestamp_offset": 5, "positive": "banana", "negative": "orange tree", "generation": "steps 15"} # middle
        ]

        # ダミーファイルを作成し、メタデータをアイテムに設定
        for i, info in enumerate(self.files_info):
            file_path = os.path.join(self.test_data_dir, info["name"])
            # ファイルを作成し、更新日時を設定 (ファイルが存在しない場合のみ)
            if not os.path.exists(file_path):
                with open(file_path, "w") as f:
                    f.write(f"dummy content for {info['name']}")

            # 更新日時を調整 (エポックタイムからの相対時間)
            # 実際のファイルシステム操作はテストの安定性に影響するため、メタデータに直接設定
            current_time = time.time()
            mock_timestamp = current_time + info["timestamp_offset"]

            # QStandardItemを作成し、データを設定
            item = QStandardItem(info["name"]) # 表示テキストはファイル名
            item.setData(file_path, Qt.ItemDataRole.UserRole) # ファイルパスをUserRoleに
            item.setData({
                'positive_prompt': info.get("positive", ""),
                'negative_prompt': info.get("negative", ""),
                'generation_info': info.get("generation", ""),
                'filename_for_sort': info["name"].lower(),
                'update_timestamp': mock_timestamp
            }, METADATA_ROLE)
            self.source_model.appendRow(item)

    def tearDown(self):
        # テスト後にダミーファイルを削除
        for info in self.files_info:
            file_path = os.path.join(self.test_data_dir, info["name"])
            if os.path.exists(file_path):
                os.remove(file_path)
        if os.path.exists(self.test_data_dir) and not os.listdir(self.test_data_dir):
            os.rmdir(self.test_data_dir)

    def get_proxy_item_texts(self):
        texts = []
        for i in range(self.proxy_model.rowCount()):
            proxy_index = self.proxy_model.index(i, 0)
            source_index = self.proxy_model.mapToSource(proxy_index)
            item = self.source_model.itemFromIndex(source_index)
            texts.append(item.text())
        return texts

    def test_initial_state_no_filter_no_sort(self):
        # 初期状態ではフィルタもソートもかかっていないはず
        # (ただし、QSortFilterProxyModelのデフォルトのソート挙動に注意)
        # ここでは、ソースモデルの順序が維持されることを期待 (明示的なソート前)
        expected_order = [info["name"] for info in self.files_info]
        self.assertEqual(self.get_proxy_item_texts(), expected_order)

    def test_sort_by_filename_asc(self):
        self.proxy_model.set_sort_key_type(0) # 0: Filename
        self.proxy_model.sort(0, Qt.SortOrder.AscendingOrder)
        expected_order = sorted([info["name"] for info in self.files_info])
        self.assertEqual(self.get_proxy_item_texts(), expected_order)

    def test_sort_by_filename_desc(self):
        self.proxy_model.set_sort_key_type(0) # 0: Filename
        self.proxy_model.sort(0, Qt.SortOrder.DescendingOrder)
        expected_order = sorted([info["name"] for info in self.files_info], reverse=True)
        self.assertEqual(self.get_proxy_item_texts(), expected_order)

    def test_sort_by_update_timestamp_asc(self):
        self.proxy_model.set_sort_key_type(1) # 1: Update Timestamp
        self.proxy_model.sort(0, Qt.SortOrder.AscendingOrder)
        # 更新日時で昇順ソート (古いものが先頭)
        expected_order = [info["name"] for info in sorted(self.files_info, key=lambda x: x["timestamp_offset"])]
        self.assertEqual(self.get_proxy_item_texts(), expected_order)

    def test_sort_by_update_timestamp_desc(self):
        self.proxy_model.set_sort_key_type(1) # 1: Update Timestamp
        self.proxy_model.sort(0, Qt.SortOrder.DescendingOrder)
        # 更新日時で降順ソート (新しいものが先頭)
        expected_order = [info["name"] for info in sorted(self.files_info, key=lambda x: x["timestamp_offset"], reverse=True)]
        self.assertEqual(self.get_proxy_item_texts(), expected_order)

    def test_sort_by_load_order(self):
        # 1. ソースモデルはsetUpで特定の順序でアイテムが追加されている
        #    self.files_info の順序が「読み込み順」となる

        # 2. 「読み込み順」ソートを設定
        self.proxy_model.set_sort_key_type(2) # 2 for load order

        # 3. 昇順ソートを実行
        self.proxy_model.sort(0, Qt.SortOrder.AscendingOrder)

        # 4. プロキシモデルのアイテム順序を確認
        #    期待する順序: self.files_info の "name" の順 (ソースモデルに追加した順)
        proxy_items_asc_texts = self.get_proxy_item_texts()
        expected_order_asc = [info["name"] for info in self.files_info]
        self.assertEqual(proxy_items_asc_texts, expected_order_asc)

        # 5. 降順ソートを実行
        self.proxy_model.sort(0, Qt.SortOrder.DescendingOrder)

        # 6. プロキシモデルのアイテム順序を確認
        #    期待する順序: self.files_info の "name" の逆順
        proxy_items_desc_texts = self.get_proxy_item_texts()
        expected_order_desc = [info["name"] for info in reversed(self.files_info)]
        self.assertEqual(proxy_items_desc_texts, expected_order_desc)

    def test_set_sort_key_type_does_not_auto_sort(self):
        # 初期状態 (ソースモデルの順序)
        initial_order = self.get_proxy_item_texts()

        # ソートキータイプを変更しても、sort()が呼ばれるまでは順序は変わらないはず
        self.proxy_model.set_sort_key_type(0) # ファイル名
        self.assertEqual(self.get_proxy_item_texts(), initial_order, "set_sort_key_type should not sort by itself")

        self.proxy_model.set_sort_key_type(1) # 更新日時
        self.assertEqual(self.get_proxy_item_texts(), initial_order, "set_sort_key_type should not sort by itself")

    def test_filter_inter_field_AND_intra_field_AND(self):
        """項目間AND、項目内ANDのテスト"""
        self.proxy_model.set_search_mode("AND")
        self.proxy_model.set_positive_prompt_filter("apple,banana") # Positive: apple AND banana
        self.proxy_model.set_negative_prompt_filter("orange")       # Negative: orange
        # Expected: c_old.png (positive: "apple banana", negative: "orange")
        self.assertEqual(len(self.get_proxy_item_texts()), 1)
        self.assertIn("c_old.png", self.get_proxy_item_texts())

    def test_filter_inter_field_AND_intra_field_OR(self):
        """項目間AND、項目内ORのテスト"""
        self.proxy_model.set_search_mode("OR")
        self.proxy_model.set_positive_prompt_filter("apple")    # Positive: apple
        self.proxy_model.set_negative_prompt_filter("orange")   # Negative: orange
        self.proxy_model.set_generation_info_filter("steps 10") # Generation: steps 10
        # Expected: c_old.png (positive: "apple banana", negative: "orange", generation: "steps 10")
        #   Positive "apple" -> True (c_old, a_new)
        #   Negative "orange" -> True (c_old, b_mid)
        #   Generation "steps 10" -> True (c_old)
        #   All True for c_old.png
        self.assertEqual(len(self.get_proxy_item_texts()), 1)
        self.assertIn("c_old.png", self.get_proxy_item_texts())

    def test_filter_inter_field_AND_intra_field_OR_no_match_due_to_inter_AND(self):
        """項目間AND、項目内ORだが、項目間AND条件でマッチしないケース"""
        self.proxy_model.set_search_mode("OR")
        self.proxy_model.set_positive_prompt_filter("apple")  # c_old.png, a_new.jpg
        self.proxy_model.set_negative_prompt_filter("sky")    # a_new.jpg
        self.proxy_model.set_generation_info_filter("steps 10") # c_old.png
        # Positive "apple" -> c_old, a_new
        # Negative "sky" -> a_new
        # Generation "steps 10" -> c_old
        # (apple OR sky OR steps 10) AND (apple OR sky OR steps 10) AND (apple OR sky OR steps 10)
        # Item c_old: P(T), N(F), G(T) -> AND -> False
        # Item a_new: P(T), N(T), G(F) -> AND -> False
        # Item b_mid: P(F), N(F), G(F) -> AND -> False
        # 期待: マッチなし
        self.assertEqual(len(self.get_proxy_item_texts()), 0)

    def test_filter_inter_field_AND_intra_field_OR_single_field_active(self):
        """項目間AND、項目内ORで、1つのフィルタ項目のみアクティブなケース"""
        self.proxy_model.set_search_mode("OR")
        self.proxy_model.set_positive_prompt_filter("banana") # c_old.png, b_mid.webp
        self.proxy_model.set_negative_prompt_filter("")
        self.proxy_model.set_generation_info_filter("")
        # Expected: c_old.png, b_mid.webp
        self.assertEqual(len(self.get_proxy_item_texts()), 2)
        self.assertIn("c_old.png", self.get_proxy_item_texts())
        self.assertIn("b_mid.webp", self.get_proxy_item_texts())

    def test_filter_inter_field_AND_all_fields_empty(self):
        """項目間ANDで、すべてのフィルタ項目が空のケース"""
        self.proxy_model.set_search_mode("AND") # モードは影響しないはず
        self.proxy_model.set_positive_prompt_filter("")
        self.proxy_model.set_negative_prompt_filter("")
        self.proxy_model.set_generation_info_filter("")
        # Expected: 全アイテム表示
        self.assertEqual(len(self.get_proxy_item_texts()), 3)

    def test_filter_clear(self):
        self.proxy_model.set_positive_prompt_filter("apple")
        self.assertNotEqual(len(self.get_proxy_item_texts()), len(self.files_info))

        self.proxy_model.set_positive_prompt_filter("") # クリア
        self.proxy_model.set_negative_prompt_filter("")
        self.proxy_model.set_generation_info_filter("")

        expected_order_after_clear = [info["name"] for info in self.files_info]
        self.assertEqual(self.get_proxy_item_texts(), expected_order_after_clear)

    def test_hidden_paths_filter(self):
        # 最初にすべてのアイテムが表示されていることを確認
        self.assertEqual(len(self.get_proxy_item_texts()), len(self.files_info))

        # 1つのアイテムを非表示にする
        path_to_hide = os.path.join(self.test_data_dir, self.files_info[0]["name"])
        self.proxy_model.set_hidden_paths({path_to_hide})
        self.proxy_model.invalidateFilter() # 明示的にフィルタを再適用
        self.assertEqual(len(self.get_proxy_item_texts()), len(self.files_info) - 1)
        self.assertNotIn(self.files_info[0]["name"], self.get_proxy_item_texts())

        # 非表示リストをクリア
        self.proxy_model.set_hidden_paths(set())
        self.proxy_model.invalidateFilter()
        self.assertEqual(len(self.get_proxy_item_texts()), len(self.files_info))

        # 存在しないパスを非表示にしても影響がないことを確認
        self.proxy_model.set_hidden_paths({"non_existent_file.png"})
        self.proxy_model.invalidateFilter() # 明示的にフィルタを再適用
        self.assertEqual(len(self.get_proxy_item_texts()), len(self.files_info))

if __name__ == '__main__':
    unittest.main()
