# src/settings_dialog.py (WC Creator 設定追加・完全版)
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QRadioButton, QDialogButtonBox, QCheckBox,
    QSlider, QLabel, QHBoxLayout, QWidget, QSizePolicy, QComboBox, QButtonGroup
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPainter, QColor, QPen
from src.constants import (
    PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM, # Import preview modes
    RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU,
    WC_FORMAT_HASH_COMMENT, WC_FORMAT_BRACKET_COMMENT,
    SORT_BY_LOAD_ORDER_ALWAYS,           # 常に読み込み順
    SORT_BY_LAST_SELECTED,                # 前回選択されたソート順
    DOUBLE_CLICK_ACTION_VIEWER,
    DOUBLE_CLICK_ACTION_VIEWER_METADATA
) 

logger = logging.getLogger(__name__)

class ThumbnailSizePreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._size = 96
        self.max_preview_width = 3 * 96 + 2 * 5
        self.preview_height = 200
        self.setMinimumSize(self.max_preview_width + 40, self.preview_height + 40)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    def set_size(self, size):
        self._size = size
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect_size = self._size
        num_rects = 1
        spacing = 5
        if rect_size == 96: num_rects = 3
        elif rect_size == 128: num_rects = 2
        total_rects_width = (num_rects * rect_size) + ((num_rects - 1) * spacing)
        start_x = (self.width() - total_rects_width) / 2
        y = (self.height() - rect_size - 30) / 2
        painter.setPen(QPen(QColor("gray"), 1))
        painter.setBrush(QColor("lightgray"))
        current_x = start_x
        for _ in range(num_rects):
            painter.drawRect(int(current_x), int(y), rect_size, rect_size)
            current_x += rect_size + spacing
        painter.setPen(QColor("black"))
        text = f"{self._size} x {self._size} px"
        text_y_offset = y + rect_size + 5
        text_rect = self.rect().adjusted(0, int(text_y_offset), 0, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text)
    def sizeHint(self):
        return QSize(self.max_preview_width + 40, self.preview_height + 40)
    def minimumSizeHint(self):
        return self.sizeHint()

class SettingsDialog(QDialog):
    def __init__(self, current_thumbnail_size, available_thumbnail_sizes,
                 current_preview_mode, current_right_click_action,
                 current_wc_comment_format,
                 current_initial_folder_sort_setting, # 初期ソート設定
                 current_delete_empty_folders_setting,
                 current_double_click_action, # ★★★ 追加: ダブルクリック動作設定 ★★★
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setMinimumWidth(450)

        self.initial_thumbnail_size = current_thumbnail_size
        self.available_thumbnail_sizes = available_thumbnail_sizes
        self.current_selected_thumbnail_size = current_thumbnail_size
        self.initial_right_click_action = current_right_click_action
        self.initial_wc_comment_format = current_wc_comment_format # 初期値を保持
        self.initial_folder_sort_setting = current_initial_folder_sort_setting
        self.initial_delete_empty_folders_setting = current_delete_empty_folders_setting
        self.initial_double_click_action = current_double_click_action # ★★★ 追加 ★★★

        self.initial_preview_mode = current_preview_mode

        main_layout = QVBoxLayout(self)

        # --- Thumbnail Size Group ---
        thumbnail_size_group = QGroupBox("サムネイルサイズ")
        thumbnail_size_layout = QVBoxLayout()
        slider_layout = QHBoxLayout()
        self.thumbnail_size_label = QLabel()
        slider_layout.addWidget(self.thumbnail_size_label)
        self.thumbnail_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.thumbnail_size_slider.setMinimum(0)
        self.thumbnail_size_slider.setMaximum(len(self.available_thumbnail_sizes) - 1)
        try: initial_slider_value = self.available_thumbnail_sizes.index(self.initial_thumbnail_size)
        except ValueError:
            initial_slider_value = 0
            self.initial_thumbnail_size = self.available_thumbnail_sizes[0]
            self.current_selected_thumbnail_size = self.initial_thumbnail_size
        self.thumbnail_size_slider.setValue(initial_slider_value)
        self.thumbnail_size_slider.setTickInterval(1)
        self.thumbnail_size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider_layout.addWidget(self.thumbnail_size_slider)
        thumbnail_size_layout.addLayout(slider_layout)
        self.thumbnail_preview_widget = ThumbnailSizePreviewWidget(self)
        thumbnail_size_layout.addWidget(self.thumbnail_preview_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        thumbnail_size_group.setLayout(thumbnail_size_layout)
        main_layout.addWidget(thumbnail_size_group)
        self.thumbnail_size_slider.valueChanged.connect(self._update_thumbnail_size_preview)
        self._update_thumbnail_size_preview(self.thumbnail_size_slider.value())

        # --- Initial Folder Sort Group ---
        initial_sort_group = QGroupBox("フォルダ選択時の初期ソート")
        initial_sort_layout = QVBoxLayout()
        self.sort_load_order_radio = QRadioButton("常に「読み込み順」でソート")
        self.sort_last_selected_radio = QRadioButton("前回選択したソート順を維持")
        self.initial_sort_button_group = QButtonGroup(self)
        self.initial_sort_button_group.addButton(self.sort_load_order_radio, 0) # ID 0 for load order
        self.initial_sort_button_group.addButton(self.sort_last_selected_radio, 1) # ID 1 for last selected
        if self.initial_folder_sort_setting == SORT_BY_LOAD_ORDER_ALWAYS:
            self.sort_load_order_radio.setChecked(True)
        else: # Default to last selected or if the value is SORT_BY_LAST_SELECTED
            self.sort_last_selected_radio.setChecked(True)
        initial_sort_layout.addWidget(self.sort_load_order_radio); initial_sort_layout.addWidget(self.sort_last_selected_radio)
        initial_sort_group.setLayout(initial_sort_layout); main_layout.addWidget(initial_sort_group)

        # --- Image Preview Mode Group ---
        preview_mode_group = QGroupBox("画像表示ダイアログ")
        preview_mode_layout = QVBoxLayout()
        self.fit_mode_radio = QRadioButton("ダイアログサイズに合わせて表示（フィット表示）")
        self.original_zoom_mode_radio = QRadioButton("原寸で表示（Ctrl+ホイールでズーム、ドラッグでスクロール）")
        preview_mode_layout.addWidget(self.fit_mode_radio)
        preview_mode_layout.addWidget(self.original_zoom_mode_radio)
        preview_mode_group.setLayout(preview_mode_layout)
        main_layout.addWidget(preview_mode_group)
        if self.initial_preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM: self.original_zoom_mode_radio.setChecked(True)
        else: self.fit_mode_radio.setChecked(True)

        # --- Double Click Action Group ---
        double_click_group = QGroupBox("サムネイルダブルクリック時の動作")
        double_click_layout = QVBoxLayout()
        self.viewer_only_radio = QRadioButton("画像ビューアのみ表示 (従来)")
        self.viewer_metadata_radio = QRadioButton("画像ビューアとメタデータを並べて表示")
        self.double_click_group_button_group = QButtonGroup(self) # 名前重複回避のため変更
        self.double_click_group_button_group.addButton(self.viewer_only_radio)
        self.double_click_group_button_group.addButton(self.viewer_metadata_radio)
        
        if self.initial_double_click_action == DOUBLE_CLICK_ACTION_VIEWER_METADATA:
            self.viewer_metadata_radio.setChecked(True)
        else:
            self.viewer_only_radio.setChecked(True)
            
        double_click_layout.addWidget(self.viewer_only_radio)
        double_click_layout.addWidget(self.viewer_metadata_radio)
        double_click_group.setLayout(double_click_layout)
        main_layout.addWidget(double_click_group)

        # --- Thumbnail Right-Click Action Group ---
        right_click_action_group = QGroupBox("サムネイル右クリック時の動作")
        right_click_action_layout = QVBoxLayout()
        self.metadata_action_radio = QRadioButton("メタデータを表示")
        self.menu_action_radio = QRadioButton("メニューを表示 (メタデータ/場所を開く)")
        self.right_click_action_button_group = QButtonGroup(self)
        self.right_click_action_button_group.addButton(self.metadata_action_radio)
        self.right_click_action_button_group.addButton(self.menu_action_radio)
        if self.initial_right_click_action == RIGHT_CLICK_ACTION_MENU: self.menu_action_radio.setChecked(True)
        else: self.metadata_action_radio.setChecked(True)
        right_click_action_layout.addWidget(self.metadata_action_radio)
        right_click_action_layout.addWidget(self.menu_action_radio)
        right_click_action_group.setLayout(right_click_action_layout)
        main_layout.addWidget(right_click_action_group)

        # Empty Folder Deletion Group
        empty_folder_group = QGroupBox("フォルダ操作設定")
        empty_folder_layout = QVBoxLayout()
        self.delete_empty_folders_checkbox = QCheckBox("フォルダ選択時に空のサブフォルダを検索して削除する")
        self.delete_empty_folders_checkbox.setChecked(self.initial_delete_empty_folders_setting)
        empty_folder_layout.addWidget(self.delete_empty_folders_checkbox)
        empty_folder_group.setLayout(empty_folder_layout)
        main_layout.addWidget(empty_folder_group)

        # --- WC Creator Comment Format Group ---
        wc_format_group = QGroupBox("ワイルドカード作成: コメント出力形式")
        wc_format_layout = QVBoxLayout()
        self.wc_comment_format_combo = QComboBox()
        self.wc_comment_format_combo.addItem("コメントを別行で出力 (# コメント)", WC_FORMAT_HASH_COMMENT)
        self.wc_comment_format_combo.addItem("コメントを角括弧で出力 ([コメント:100])", WC_FORMAT_BRACKET_COMMENT)
        
        # 初期値を設定 (MainWindowから渡された現在の設定値で)
        current_combo_index = 0 # デフォルトは0番目
        for i in range(self.wc_comment_format_combo.count()):
            if self.wc_comment_format_combo.itemData(i) == self.initial_wc_comment_format:
                current_combo_index = i
                break
        self.wc_comment_format_combo.setCurrentIndex(current_combo_index)

        wc_format_layout.addWidget(self.wc_comment_format_combo)
        wc_format_group.setLayout(wc_format_layout)
        main_layout.addWidget(wc_format_group)

        # --- Dialog Buttons (OK, Cancel) ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        self.setLayout(main_layout)

    def _update_thumbnail_size_preview(self, value):
        try:
            size = self.available_thumbnail_sizes[value]
            self.current_selected_thumbnail_size = size
            self.thumbnail_size_label.setText(f"選択中: {size}px")
            self.thumbnail_preview_widget.set_size(size)
        except IndexError:
            logger.error(f"Slider value {value} is out of range for available_thumbnail_sizes.")

    def accept(self):
        # MainWindowがこのダイアログのget_selected_...メソッドを呼び出して値を取得し、
        # 実際の保存処理はMainWindow側で行う。
        # このダイアログは、ユーザーの選択を伝える役割に徹する。
        super().accept()

    def get_selected_preview_mode(self):
        if self.fit_mode_radio.isChecked(): return PREVIEW_MODE_FIT
        elif self.original_zoom_mode_radio.isChecked(): return PREVIEW_MODE_ORIGINAL_ZOOM
        return self.initial_preview_mode

    def get_selected_thumbnail_size(self):
        return self.current_selected_thumbnail_size

    def get_selected_right_click_action(self):
        if self.metadata_action_radio.isChecked(): return RIGHT_CLICK_ACTION_METADATA
        elif self.menu_action_radio.isChecked(): return RIGHT_CLICK_ACTION_MENU
        return self.initial_right_click_action

    def get_selected_wc_comment_format(self):
        return self.wc_comment_format_combo.currentData()

    def get_selected_delete_empty_folders_setting(self):
        return self.delete_empty_folders_checkbox.isChecked()

    def get_selected_initial_folder_sort_setting(self):
        if self.sort_load_order_radio.isChecked():
            return SORT_BY_LOAD_ORDER_ALWAYS
        return SORT_BY_LAST_SELECTED # Default or if sort_last_selected_radio is checked

    def get_selected_double_click_action(self):
        if self.viewer_metadata_radio.isChecked():
            return DOUBLE_CLICK_ACTION_VIEWER_METADATA
        return DOUBLE_CLICK_ACTION_VIEWER
