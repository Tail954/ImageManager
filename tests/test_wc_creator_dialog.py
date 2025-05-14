import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.wc_creator_dialog import WCCreatorDialog, OutputDialog
from src.constants import WC_FORMAT_HASH_COMMENT, WC_FORMAT_BRACKET_COMMENT

class TestWCCreatorDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Qtアプリケーションのセットアップ
        cls.app = QApplication([])

    @classmethod
    def tearDownClass(cls):
        # Qtアプリケーションのクリーンアップ
        cls.app.quit()

    def setUp(self):
        # テスト用のモックデータ
        self.test_file_paths = [
            os.path.join(os.path.dirname(__file__), 'test_data/images/test1.jpg'),
            os.path.join(os.path.dirname(__file__), 'test_data/images/test2.jpg')
        ]
        self.test_metadata = [
            {'positive_prompt': 'line1\nline2\nline3'},
            {'positive_prompt': 'lineA\nlineB\nlineC'}
        ]

    def test_initialization(self):
        """ダイアログの初期化テスト"""
        dialog = WCCreatorDialog(
            selected_file_paths=self.test_file_paths,
            metadata_list=self.test_metadata,
            output_format=WC_FORMAT_HASH_COMMENT
        )
        
        self.assertEqual(dialog.windowTitle(), "ワイルドカード作成")
        self.assertFalse(dialog.prev_button.isEnabled()) # 初期状態では「前へ」は無効のはず
        self.assertTrue(dialog.next_button.isEnabled())
        self.assertEqual(dialog.image_index_label.text(), "1 / 2")

    def test_load_image_data(self):
        """画像データの読み込みテスト"""
        dialog = WCCreatorDialog(
            selected_file_paths=self.test_file_paths,
            metadata_list=self.test_metadata,
            output_format=WC_FORMAT_HASH_COMMENT
        )
        
        # 最初の画像をロード
        dialog.load_image_data(0)
        
        # プロンプト行が正しく読み込まれているか
        self.assertEqual(len(dialog.prompt_checkboxes), 3)
        self.assertEqual(len(dialog.prompt_line_edits), 3)
        self.assertEqual(dialog.prompt_line_edits[0].text(), "line1")
        self.assertEqual(dialog.prompt_line_edits[1].text(), "line2")
        self.assertEqual(dialog.prompt_line_edits[2].text(), "line3")

    def test_navigation(self):
        """画像ナビゲーションのテスト"""
        dialog = WCCreatorDialog(
            selected_file_paths=self.test_file_paths,
            metadata_list=self.test_metadata,
            output_format=WC_FORMAT_HASH_COMMENT
        )
        
        # 最初の画像をロード
        dialog.load_image_data(0)
        self.assertEqual(dialog.current_index, 0)
        
        # 次の画像へ移動
        dialog.show_next_image()
        self.assertEqual(dialog.current_index, 1)
        self.assertEqual(len(dialog.prompt_checkboxes), 3)
        self.assertEqual(dialog.prompt_line_edits[0].text(), "lineA")
        
        # 前の画像へ戻る
        dialog.show_previous_image()
        self.assertEqual(dialog.current_index, 0)

    def test_output_formatting(self):
        """出力フォーマットのテスト"""
        dialog = WCCreatorDialog(
            selected_file_paths=self.test_file_paths,
            metadata_list=self.test_metadata,
            output_format=WC_FORMAT_HASH_COMMENT
        )
        dialog.load_image_data(0)
        
        # コメントを設定
        dialog.comment_edit.setText("test comment")
        
        # ハッシュコメント形式のテスト
        dialog.output_format = WC_FORMAT_HASH_COMMENT
        expected_hash = "# test comment\nline1 line2 line3"
        self.assertEqual(dialog._get_formatted_text_for_current_image(False), expected_hash)
        
        # ブラケットコメント形式のテスト
        dialog.output_format = WC_FORMAT_BRACKET_COMMENT
        expected_bracket = "[test comment:100]line1 line2 line3"
        self.assertEqual(dialog._get_formatted_text_for_current_image(False), expected_bracket)

    @patch('PyQt6.QtWidgets.QApplication.clipboard')
    def test_copy_to_clipboard(self, mock_clipboard):
        """クリップボードへのコピーテスト"""
        mock_clipboard.return_value = MagicMock()
        
        dialog = WCCreatorDialog(
            selected_file_paths=self.test_file_paths,
            metadata_list=self.test_metadata,
            output_format=WC_FORMAT_HASH_COMMENT
        )
        dialog.load_image_data(0)
        
        # 最初の行を選択
        dialog.prompt_checkboxes[0].setChecked(True)
        
        # コピーを実行
        dialog._copy_current_to_clipboard()
        
        # クリップボードに正しい内容が設定されたか
        mock_clipboard.return_value.setText.assert_called_once_with("line1")

class TestOutputDialog(unittest.TestCase):
    def setUp(self):
        # テスト用のモックデータ
        self.test_file_paths = [
            os.path.join(os.path.dirname(__file__), 'test_data/images/test1.jpg'),
            os.path.join(os.path.dirname(__file__), 'test_data/images/test2.jpg')
        ]
        self.test_metadata = [
            {'positive_prompt': 'line1\nline2\nline3'},
            {'positive_prompt': 'lineA\nlineB\nlineC'}
        ]
        self.test_comments = {0: "comment1", 1: "comment2"}
        self.test_checkbox_states = {0: [True, False, True], 1: [False, True, False]}

    def test_output_generation(self):
        """出力ダイアログの生成テスト"""
        dialog = OutputDialog(
            selected_file_paths=self.test_file_paths,
            metadata_list=self.test_metadata,
            initial_comments=self.test_comments,
            initial_checkbox_states=self.test_checkbox_states,
            checked_only_mode=True,
            output_format=WC_FORMAT_HASH_COMMENT,
            parent=None
        )
        
        # ハッシュコメント形式の出力を検証
        expected_output = "# comment1\nline1 line3\n# comment2\nlineB"
        self.assertEqual(dialog._generate_final_output_text(), expected_output)
        
        # ブラケットコメント形式に変更して検証
        dialog.output_format = WC_FORMAT_BRACKET_COMMENT
        expected_output = "[comment1:100]line1 line3\n[comment2:100]lineB"
        self.assertEqual(dialog._generate_final_output_text(), expected_output)

if __name__ == '__main__':
    unittest.main()
