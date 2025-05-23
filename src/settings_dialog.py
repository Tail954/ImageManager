# src/settings_dialog.py (WC Creator 設定追加・完全版)
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QRadioButton, QDialogButtonBox, QApplication, QCheckBox,
    QSlider, QLabel, QHBoxLayout, QWidget, QSizePolicy, QComboBox, QButtonGroup
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPainter, QColor, QPen
from src.constants import (
    APP_SETTINGS_FILE, # Import APP_SETTINGS_FILE
    PREVIEW_MODE_FIT, PREVIEW_MODE_ORIGINAL_ZOOM, # Import preview modes
    THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA, RIGHT_CLICK_ACTION_MENU, # Import right click actions
    WC_COMMENT_OUTPUT_FORMAT, WC_FORMAT_HASH_COMMENT, WC_FORMAT_BRACKET_COMMENT, # Import WC Creator constants
    DELETE_EMPTY_FOLDERS_ENABLED, # ★★★ 追加 ★★★
    INITIAL_SORT_ORDER_ON_FOLDER_SELECT, # ★★★ 初期ソート設定キー ★★★
    SORT_BY_LOAD_ORDER_ALWAYS,           # ★★★ 常に読み込み順 ★★★
    SORT_BY_LAST_SELECTED                # ★★★ 前回選択されたソート順 ★★★
) 
import json
import os

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
                 current_initial_folder_sort_setting, # ★★★ 追加: 初期ソート設定 ★★★
                 current_delete_empty_folders_setting, # ★★★ 追加 ★★★
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setMinimumWidth(450)

        self.initial_thumbnail_size = current_thumbnail_size
        self.available_thumbnail_sizes = available_thumbnail_sizes
        self.current_selected_thumbnail_size = current_thumbnail_size
        self.initial_right_click_action = current_right_click_action
        self.initial_wc_comment_format = current_wc_comment_format # 初期値を保持
        self.initial_folder_sort_setting = current_initial_folder_sort_setting # ★★★ 追加 ★★★
        self.initial_delete_empty_folders_setting = current_delete_empty_folders_setting # ★★★ 追加 ★★★

        # アプリケーション設定ファイルからダイアログに関連する値を読み込む
        # MainWindowと責任範囲を分けるため、このダイアログは自身の表示に必要な設定のみを
        # 直接ファイルから読み込む（ただし、MainWindowが主たる設定管理を行う）
        self.current_settings = self._load_settings_for_dialog_display()
        self.initial_preview_mode = self.current_settings.get("image_preview_mode", PREVIEW_MODE_FIT)
        # DELETE_EMPTY_FOLDERS_ENABLED は MainWindow から渡される値を優先
        # INITIAL_SORT_ORDER_ON_FOLDER_SELECT も MainWindow から渡される値を優先
        # self.initial_wc_comment_format はコンストラクタ引数で受け取ったものを優先する

        main_layout = QVBoxLayout(self)

        # --- Thumbnail Size Group ---
        thumbnail_size_group = QGroupBox("サムネイルサイズ設定")
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

        # --- Image Preview Mode Group ---
        preview_mode_group = QGroupBox("画像表示ダイアログの表示モード")
        preview_mode_layout = QVBoxLayout()
        self.fit_mode_radio = QRadioButton("ダイアログサイズに合わせて表示（フィット表示）")
        self.original_zoom_mode_radio = QRadioButton("原寸で表示（Ctrl+ホイールでズーム、ドラッグでスクロール）")
        preview_mode_layout.addWidget(self.fit_mode_radio)
        preview_mode_layout.addWidget(self.original_zoom_mode_radio)
        preview_mode_group.setLayout(preview_mode_layout)
        main_layout.addWidget(preview_mode_group)
        if self.initial_preview_mode == PREVIEW_MODE_ORIGINAL_ZOOM: self.original_zoom_mode_radio.setChecked(True)
        else: self.fit_mode_radio.setChecked(True)

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

        # --- ★★★ 追加: Empty Folder Deletion Group ★★★ ---
        empty_folder_group = QGroupBox("フォルダ操作設定")
        empty_folder_layout = QVBoxLayout()
        self.delete_empty_folders_checkbox = QCheckBox("フォルダ選択時に空のサブフォルダを検索して削除する")
        self.delete_empty_folders_checkbox.setChecked(self.initial_delete_empty_folders_setting)
        empty_folder_layout.addWidget(self.delete_empty_folders_checkbox)
        empty_folder_group.setLayout(empty_folder_layout)
        main_layout.addWidget(empty_folder_group)

        # --- ★★★ 追加: Initial Folder Sort Group ★★★ ---
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

    def _load_settings_for_dialog_display(self):
        """ダイアログ表示に必要な設定（主に初期値）をファイルから読み込む"""
        # MainWindow が主たる設定管理者なので、ここでは読み込みエラー時に過度に介入しない
        default_values = {
            "image_preview_mode": PREVIEW_MODE_FIT,
            # WC_COMMENT_OUTPUT_FORMAT は MainWindow から渡される値を優先するため、ここでは読み込まない
            # DELETE_EMPTY_FOLDERS_ENABLED も MainWindow から渡される値を優先
        }
        try:
            if os.path.exists(APP_SETTINGS_FILE):
                with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    # 必要なキーだけをロード
                    loaded_settings = default_values.copy()
                    if "image_preview_mode" in settings:
                        loaded_settings["image_preview_mode"] = settings["image_preview_mode"]
                    return loaded_settings
        except Exception as e:
            logger.error(f"設定ファイル ({APP_SETTINGS_FILE}) の読み込み中にエラー (SettingsDialog): {e}", exc_info=True)
        return default_values # エラー時やファイルがない場合はデフォルト

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

    def get_selected_delete_empty_folders_setting(self): # ★★★ 追加 ★★★
        return self.delete_empty_folders_checkbox.isChecked()

    def get_selected_initial_folder_sort_setting(self): # ★★★ 追加 ★★★
        if self.sort_load_order_radio.isChecked():
            return SORT_BY_LOAD_ORDER_ALWAYS
        return SORT_BY_LAST_SELECTED # Default or if sort_last_selected_radio is checked


if __name__ == '__main__':
    import sys
    # Dummy data for testing
    available_sizes_test = [96, 128, 200, 256]
    current_size_test = 128
    current_preview_mode_test = PREVIEW_MODE_FIT
    current_delete_empty_folders_test = True # ★★★ 追加 ★★★
    current_initial_sort_test = SORT_BY_LOAD_ORDER_ALWAYS # ★★★ デフォルト変更 ★★★

    # Create a dummy app_settings.json for testing if it doesn't exist
    dummy_settings_for_test = {
        "image_preview_mode": PREVIEW_MODE_ORIGINAL_ZOOM,
        "thumbnail_size": 128,
        THUMBNAIL_RIGHT_CLICK_ACTION: RIGHT_CLICK_ACTION_METADATA, # Add new setting for test
        DELETE_EMPTY_FOLDERS_ENABLED: False, # ★★★ 追加 ★★★
        INITIAL_SORT_ORDER_ON_FOLDER_SELECT: SORT_BY_LOAD_ORDER_ALWAYS, # ★★★ 追加 ★★★
        "other_setting": "test",
    }
    if not os.path.exists(APP_SETTINGS_FILE):
        with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(dummy_settings_for_test, f, indent=4)
    else: # Ensure it has expected keys for test
        with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            temp_settings = json.load(f)
        temp_settings.setdefault("image_preview_mode", PREVIEW_MODE_FIT)
        temp_settings.setdefault("thumbnail_size", 128)
        temp_settings.setdefault(THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA)
        temp_settings.setdefault(DELETE_EMPTY_FOLDERS_ENABLED, True) # ★★★ 追加 ★★★
        temp_settings.setdefault(INITIAL_SORT_ORDER_ON_FOLDER_SELECT, SORT_BY_LAST_SELECTED) # ★★★ 追加 ★★★
        with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(temp_settings, f, indent=4)


    app = QApplication(sys.argv)
    # Test with initial right click action
    current_right_click_action_test = dummy_settings_for_test.get(THUMBNAIL_RIGHT_CLICK_ACTION, RIGHT_CLICK_ACTION_METADATA)
    current_initial_sort_test = dummy_settings_for_test.get(INITIAL_SORT_ORDER_ON_FOLDER_SELECT, SORT_BY_LOAD_ORDER_ALWAYS) # ★★★ デフォルト変更 ★★★
    current_delete_empty_folders_test = dummy_settings_for_test.get(DELETE_EMPTY_FOLDERS_ENABLED, True) # ★★★ 追加 ★★★
    dialog = SettingsDialog(
        current_thumbnail_size=current_size_test,
        available_thumbnail_sizes=available_sizes_test,
        current_preview_mode=current_preview_mode_test,
        current_right_click_action=current_right_click_action_test,
        current_wc_comment_format=WC_FORMAT_HASH_COMMENT, # Dummy for test
        current_initial_folder_sort_setting=current_initial_sort_test, # ★★★ 追加 ★★★
        current_delete_empty_folders_setting=current_delete_empty_folders_test # ★★★ 追加 ★★★
    )
    if dialog.exec():
        print("Settings accepted by dialog.")
        selected_size = dialog.get_selected_thumbnail_size()
        selected_mode = dialog.get_selected_preview_mode()
        selected_right_click_action = dialog.get_selected_right_click_action()
        selected_initial_sort = dialog.get_selected_initial_folder_sort_setting() # ★★★ 追加 ★★★
        selected_delete_empty = dialog.get_selected_delete_empty_folders_setting() # ★★★ 追加 ★★★
        print(f"Selected thumbnail size from dialog: {selected_size}")
        print(f"Selected preview mode from dialog: {selected_mode}")
        print(f"Selected right-click action from dialog: {selected_right_click_action}")
        print(f"Selected initial folder sort setting from dialog: {selected_initial_sort}") # ★★★ 追加 ★★★
        print(f"Selected delete empty folders setting from dialog: {selected_delete_empty}") # ★★★ 追加 ★★★

        # Simulate MainWindow saving the settings
        # In real app, MainWindow would show confirmation for thumbnail size change
        # and then save all settings.
        print("Simulating MainWindow saving all settings...")
        main_window_settings_to_save = {}
        if os.path.exists(APP_SETTINGS_FILE):
             with open(APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                main_window_settings_to_save = json.load(f)
        
        main_window_settings_to_save["thumbnail_size"] = selected_size
        main_window_settings_to_save["image_preview_mode"] = selected_mode
        main_window_settings_to_save[THUMBNAIL_RIGHT_CLICK_ACTION] = selected_right_click_action
        main_window_settings_to_save[INITIAL_SORT_ORDER_ON_FOLDER_SELECT] = selected_initial_sort # ★★★ 追加 ★★★
        main_window_settings_to_save[DELETE_EMPTY_FOLDERS_ENABLED] = selected_delete_empty # ★★★ 追加 ★★★

        with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(main_window_settings_to_save, f, indent=4)
        print(f"MainWindow saved: {main_window_settings_to_save}")

    else:
        print("Settings cancelled by dialog.")
    
    sys.exit()
