# src/wc_creator_dialog.py (output_format 対応・完全版)
import os
from PyQt6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSplitter, QLabel,
    QTextEdit, QCheckBox, QScrollArea, QWidget, QLineEdit,
    QFileDialog, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage
import logging

# src.constantsから定数をインポート
from src.constants import (
    WC_COMMENT_OUTPUT_FORMAT, # 設定キーは実際にはMainWindow側で使う
    WC_FORMAT_HASH_COMMENT,
    WC_FORMAT_BRACKET_COMMENT
)

logger = logging.getLogger(__name__)

class WCCreatorDialog(QDialog):
    def __init__(self, selected_file_paths, metadata_list, output_format, parent=None): # output_format を受け取る
        super().__init__(parent)
        self.setWindowTitle("ワイルドカード作成")
        self.setGeometry(100, 100, 900, 600)

        if not selected_file_paths or not metadata_list or len(selected_file_paths) != len(metadata_list):
            self.selected_file_paths = []
            self.metadata_list = []
        else:
            self.selected_file_paths = selected_file_paths
            self.metadata_list = metadata_list

        self.output_format = output_format # MainWindowから渡された形式を使用

        self.current_index = 0
        self.comment_cache = {}
        self.checkbox_state_cache = {}
        self.prompt_checkboxes = []
        self.prompt_line_edits = []

        self.initUI()
        if self.selected_file_paths:
            self.load_image_data(self.current_index)
        else:
            self._update_navigation_buttons()

    def initUI(self):
        # (UI定義は前回の調整済みバージョンと同じなので詳細は省略)
        main_layout = QHBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        left_panel = QWidget(); left_layout = QVBoxLayout(left_panel)
        self.image_label = QLabel("ここにサムネイル画像"); self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.image_label.setMinimumSize(250, 250); self.image_label.setStyleSheet("border: 1px solid gray;")
        left_layout.addWidget(self.image_label)
        nav_layout = QHBoxLayout(); self.prev_button = QPushButton("← 前へ"); self.prev_button.clicked.connect(self.show_previous_image); nav_layout.addWidget(self.prev_button)
        self.image_index_label = QLabel("0 / 0"); self.image_index_label.setAlignment(Qt.AlignmentFlag.AlignCenter); nav_layout.addWidget(self.image_index_label)
        self.next_button = QPushButton("次へ →"); self.next_button.clicked.connect(self.show_next_image); nav_layout.addWidget(self.next_button)
        left_layout.addLayout(nav_layout)
        self.splitter.addWidget(left_panel)
        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel)
        top_controls_layout = QHBoxLayout(); self.toggle_all_button = QPushButton("全て選択/解除"); self.toggle_all_button.setToolTip("表示中のプロンプト行のチェックを全てオン/オフします。"); self.toggle_all_button.clicked.connect(self._toggle_all_current_checkboxes); top_controls_layout.addWidget(self.toggle_all_button)
        top_controls_layout.addWidget(QLabel("コメント:")); self.comment_edit = QLineEdit(); self.comment_edit.setPlaceholderText("この画像へのコメントを入力 (任意)"); top_controls_layout.addWidget(self.comment_edit)
        right_layout.addLayout(top_controls_layout)
        self.scroll_area = QScrollArea(); self.scroll_area.setWidgetResizable(True); self.scroll_widget_content = QWidget(); self.prompt_lines_layout = QVBoxLayout(self.scroll_widget_content); self.prompt_lines_layout.setAlignment(Qt.AlignmentFlag.AlignTop); self.scroll_area.setWidget(self.scroll_widget_content)
        right_layout.addWidget(self.scroll_area)
        bottom_buttons_layout = QHBoxLayout(); self.output_checked_button = QPushButton("選択行をプレビュー"); self.output_checked_button.clicked.connect(lambda: self._show_output_preview_dialog(checked_only=True)); bottom_buttons_layout.addWidget(self.output_checked_button)
        self.output_all_button = QPushButton("全行をプレビュー"); self.output_all_button.clicked.connect(lambda: self._show_output_preview_dialog(checked_only=False)); bottom_buttons_layout.addWidget(self.output_all_button)
        self.clipboard_button = QPushButton("クリップボードへコピー"); self.clipboard_button.setToolTip("現在の画像のコメントと選択されたプロンプト行をクリップボードにコピーします。"); self.clipboard_button.clicked.connect(self._copy_current_to_clipboard); bottom_buttons_layout.addWidget(self.clipboard_button)
        right_layout.addLayout(bottom_buttons_layout)
        self.splitter.addWidget(right_panel); self.splitter.setSizes([300, 600])
        main_layout.addWidget(self.splitter); self.setLayout(main_layout)

    def _update_navigation_buttons(self): # 変更なし
        enable_buttons = bool(self.selected_file_paths)
        self.prev_button.setEnabled(enable_buttons and self.current_index > 0)
        self.next_button.setEnabled(enable_buttons and self.current_index < len(self.selected_file_paths) - 1)
        self.image_index_label.setText(f"{self.current_index + 1 if enable_buttons else 0} / {len(self.selected_file_paths) if enable_buttons else 0}")
        for btn in [self.toggle_all_button, self.output_checked_button, self.output_all_button, self.clipboard_button]: btn.setEnabled(enable_buttons)

    def _clear_prompt_lines_layout(self): # 変更なし
        while self.prompt_lines_layout.count():
            child = self.prompt_lines_layout.takeAt(0)
            if widget := child.widget(): widget.deleteLater()
            elif layout := child.layout():
                while layout.count():
                    if item_widget := layout.takeAt(0).widget(): item_widget.deleteLater()
                layout.deleteLater()
        self.prompt_checkboxes.clear(); self.prompt_line_edits.clear()

    def load_image_data(self, index): # 変更なし
        if not self.selected_file_paths or not (0 <= index < len(self.selected_file_paths)):
            self._clear_prompt_lines_layout(); self.image_label.setText("画像なし"); self.comment_edit.clear(); self._update_navigation_buttons(); return
        self.current_index = index
        file_path, metadata = self.selected_file_paths[index], self.metadata_list[index]
        try:
            qimage = QImage(file_path)
            if not qimage.isNull(): self.image_label.setPixmap(QPixmap.fromImage(qimage).scaled(self.image_label.minimumWidth() - 10, self.image_label.minimumHeight() - 10, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else: self.image_label.setText(f"画像読込失敗:\n{os.path.basename(file_path)}")
        except Exception as e: self.image_label.setText(f"画像表示エラー:\n{os.path.basename(file_path)}"); logger.error(f"サムネイル表示エラー ({file_path}): {e}", exc_info=True)
        self._update_navigation_buttons(); self.comment_edit.setText(self.comment_cache.get(index, ""))
        self._clear_prompt_lines_layout()
        positive_prompt = metadata.get('positive_prompt', '')
        if not isinstance(positive_prompt, str): positive_prompt = ""
        prompt_lines = positive_prompt.split('\n')
        cached_states = self.checkbox_state_cache.get(index)
        for i, line_text in enumerate(prompt_lines):
            line_widget = QWidget(); line_layout = QHBoxLayout(line_widget); line_layout.setContentsMargins(0,0,0,0)
            cb = QCheckBox(); cb.setChecked(cached_states[i] if cached_states and i < len(cached_states) else False)
            line_layout.addWidget(cb); self.prompt_checkboxes.append(cb)
            le = QLineEdit(line_text.strip()); le.setReadOnly(True); le.setStyleSheet("background-color: #f0f0f0;")
            line_layout.addWidget(le); self.prompt_line_edits.append(le)
            self.prompt_lines_layout.addWidget(line_widget)

    def _cache_current_view_state(self): # 変更なし
        if not self.selected_file_paths or not (0 <= self.current_index < len(self.selected_file_paths)): return
        self.comment_cache[self.current_index] = self.comment_edit.text()
        if self.prompt_checkboxes: self.checkbox_state_cache[self.current_index] = [cb.isChecked() for cb in self.prompt_checkboxes]

    def show_previous_image(self): # 変更なし
        if self.current_index > 0: self._cache_current_view_state(); self.load_image_data(self.current_index - 1)

    def show_next_image(self): # 変更なし
        if self.current_index < len(self.selected_file_paths) - 1: self._cache_current_view_state(); self.load_image_data(self.current_index + 1)

    def _toggle_all_current_checkboxes(self): # 変更なし
        if not self.prompt_checkboxes: return
        new_state = not all(cb.isChecked() for cb in self.prompt_checkboxes)
        for cb in self.prompt_checkboxes: cb.setChecked(new_state)
        self.checkbox_state_cache[self.current_index] = [cb.isChecked() for cb in self.prompt_checkboxes]

    def _get_formatted_text_for_current_image(self, checked_only=True):
        if not self.selected_file_paths or not (0 <= self.current_index < len(self.selected_file_paths)): return ""
        comment = self.comment_edit.text().strip()
        lines = [le.text().strip() for i, le in enumerate(self.prompt_line_edits) if not checked_only or (i < len(self.prompt_checkboxes) and self.prompt_checkboxes[i].isChecked())]
        combined_prompt = " ".join(filter(None, lines))
        # ★★★ 修正: output_format を使用 ★★★
        if self.output_format == WC_FORMAT_HASH_COMMENT:
            return f"# {comment}\n{combined_prompt}" if comment else combined_prompt
        elif self.output_format == WC_FORMAT_BRACKET_COMMENT:
            return f"[{comment}:100]{combined_prompt}" if comment else combined_prompt
        return combined_prompt # デフォルトまたは不明なフォーマット

    def _copy_current_to_clipboard(self): # ★★★ 修正: 成功時メッセージ削除 ★★★
        self._cache_current_view_state()
        output_text = self._get_formatted_text_for_current_image(checked_only=True)
        if output_text:
            try:
                QApplication.clipboard().setText(output_text)
                logger.info("選択されたプロンプトがクリップボードにコピーされました。")
            except Exception as e:
                logger.error(f"クリップボードへのコピー中にエラー: {e}", exc_info=True)
                QMessageBox.warning(self, "コピー失敗", f"クリップボードへのコピー中にエラーが発生しました:\n{str(e)}")
        else:
            QMessageBox.warning(self, "コピー対象なし", "クリップボードにコピーするプロンプトがありません。")

    def _show_output_preview_dialog(self, checked_only=True): # output_format を渡す
        self._cache_current_view_state()
        if not self.selected_file_paths: QMessageBox.warning(self, "エラー", "処理対象の画像がありません。"); return
        output_dialog = OutputDialog(
            selected_file_paths=self.selected_file_paths,
            metadata_list=self.metadata_list,
            initial_comments=self.comment_cache.copy(),
            initial_checkbox_states=self.checkbox_state_cache.copy(),
            checked_only_mode=checked_only,
            output_format=self.output_format, # ★★★ output_format を渡す ★★★
            parent=self
        )
        output_dialog.exec()

class OutputDialog(QDialog):
    # コンストラクタで output_format を受け取るように変更
    def __init__(self, selected_file_paths, metadata_list,
                 initial_comments, initial_checkbox_states,
                 checked_only_mode, output_format, parent=None): # output_format を追加
        super().__init__(parent)
        self.setWindowTitle("ワイルドカード出力プレビュー") # 前回のUI調整を維持
        self.setGeometry(150, 150, 1000, 700)
        self.selected_file_paths = selected_file_paths
        self.metadata_list = metadata_list
        self.initial_comments = initial_comments
        self.initial_checkbox_states = initial_checkbox_states
        self.checked_only_mode = checked_only_mode
        self.output_format = output_format # ★★★ 受け取った output_format を保持 ★★★
        self.item_widgets_list = []
        self.initUI()
        self.populate_output_preview()

    def initUI(self): # 前回のUI調整（検索・置換エリア縦積み）を維持
        main_layout = QVBoxLayout(self)
        replace_gb = QWidget(); replace_outer_layout = QHBoxLayout(replace_gb)
        replace_fields_layout = QVBoxLayout(); self.search_edit = QLineEdit(placeholderText="検索する文字列（タグを削除する場合、必要に応じてカンマも検索文字列に含めてください。）"); replace_fields_layout.addWidget(self.search_edit)
        self.replace_edit = QLineEdit(placeholderText="置換後の文字列"); replace_fields_layout.addWidget(self.replace_edit)
        replace_outer_layout.addLayout(replace_fields_layout)
        self.replace_button = QPushButton("一括置換"); self.replace_button.clicked.connect(self._perform_replace_all); replace_outer_layout.addWidget(self.replace_button)
        main_layout.addWidget(replace_gb)
        self.scroll_area = QScrollArea(); self.scroll_area.setWidgetResizable(True); self.scroll_widget_content = QWidget(); self.preview_items_layout = QVBoxLayout(self.scroll_widget_content); self.preview_items_layout.setAlignment(Qt.AlignmentFlag.AlignTop); self.scroll_area.setWidget(self.scroll_widget_content)
        main_layout.addWidget(self.scroll_area)
        self.save_button = QPushButton("ファイルへ出力"); self.save_button.clicked.connect(self._save_to_file)
        main_layout.addWidget(self.save_button); self.setLayout(main_layout)

    def populate_output_preview(self): # 変更なし
        self.item_widgets_list.clear()
        for i, file_path in enumerate(self.selected_file_paths):
            metadata, comment, cb_states = self.metadata_list[i], self.initial_comments.get(i, ""), self.initial_checkbox_states.get(i)
            item_widget = QWidget(); item_layout = QHBoxLayout(item_widget); item_layout.setContentsMargins(5,5,5,5)
            thumb_lbl = QLabel(); thumb_lbl.setFixedSize(100, 100); thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); thumb_lbl.setStyleSheet("border: 1px solid lightgray;")
            try:
                qimg = QImage(file_path)
                if not qimg.isNull(): thumb_lbl.setPixmap(QPixmap.fromImage(qimg).scaled(96,96,Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                else: thumb_lbl.setText("読込失敗")
            except Exception: thumb_lbl.setText("表示エラー")
            item_layout.addWidget(thumb_lbl)
            text_data_widget = QWidget(); text_data_layout = QVBoxLayout(text_data_widget)
            text_data_layout.addWidget(QLabel(f"<b>{os.path.basename(file_path)}</b>"))
            comment_edit = QLineEdit(comment); text_data_layout.addWidget(QLabel("コメント:")); text_data_layout.addWidget(comment_edit)
            prompt_edit = QTextEdit(); prompt_edit.setAcceptRichText(False); prompt_edit.setMinimumHeight(60)
            positive_prompt = metadata.get('positive_prompt', '')
            if not isinstance(positive_prompt, str): positive_prompt = ""
            lines_raw = positive_prompt.split('\n')
            selected_lines = []
            if self.checked_only_mode:
                if cb_states: selected_lines.extend(lines_raw[j].strip() for j, line in enumerate(lines_raw) if j < len(cb_states) and cb_states[j])
            else: selected_lines.extend(line.strip() for line in lines_raw)
            prompt_edit.setPlainText(" ".join(filter(None, selected_lines)))
            text_data_layout.addWidget(QLabel("プロンプト:")); text_data_layout.addWidget(prompt_edit)
            item_layout.addWidget(text_data_widget, 1); self.preview_items_layout.addWidget(item_widget)
            self.item_widgets_list.append({'comment_edit': comment_edit, 'prompt_edit': prompt_edit})

    def _perform_replace_all(self): # 変更なし
        search, replace = self.search_edit.text(), self.replace_edit.text()
        if not search: QMessageBox.information(self, "情報", "検索文字列未入力"); return
        count = 0
        for widgets in self.item_widgets_list:
            if (c_orig := widgets['comment_edit'].text()) != (c_new := c_orig.replace(search, replace)): widgets['comment_edit'].setText(c_new); count+=1
            if (p_orig := widgets['prompt_edit'].toPlainText()) != (p_new := p_orig.replace(search, replace)): widgets['prompt_edit'].setPlainText(p_new); count+=1
        QMessageBox.information(self, "置換完了", f"処理完了。" + (f" 約{count}箇所置換。" if count > 0 else ""))

    def _generate_final_output_text(self): # ★★★ 修正: output_format を使用 ★★★
        output_lines = []
        for item_widgets in self.item_widgets_list:
            comment = item_widgets['comment_edit'].text().strip()
            prompt_text = item_widgets['prompt_edit'].toPlainText().strip()

            if self.output_format == WC_FORMAT_HASH_COMMENT:
                if comment: output_lines.append(f"# {comment}")
                if prompt_text: output_lines.append(prompt_text)
            elif self.output_format == WC_FORMAT_BRACKET_COMMENT:
                if comment and prompt_text: output_lines.append(f"[{comment}:100]{prompt_text}")
                elif prompt_text: output_lines.append(prompt_text)
            # 他のフォーマットがあればここに追加
        return "\n".join(output_lines)

    def _save_to_file(self): # 変更なし
        text_to_save = self._generate_final_output_text()
        if not text_to_save.strip(): QMessageBox.warning(self, "出力エラー", "出力内容なし"); return
        default_fn = f"{os.path.splitext(os.path.basename(self.selected_file_paths[0]))[0]}_prompts.txt" if self.selected_file_paths else "wc_output.txt"
        if file_path := QFileDialog.getSaveFileName(self, "名前を付けて保存", default_fn, "Text Files (*.txt);;All Files (*)")[0]:
            try:
                with open(file_path, 'w', encoding='utf-8') as f: f.write(text_to_save)
                QMessageBox.information(self, "保存完了", f"保存先:\n{file_path}")
            except Exception as e: logger.error(f"WC出力保存失敗: {e}", exc_info=True); QMessageBox.critical(self, "保存エラー", f"エラー:\n{str(e)}")