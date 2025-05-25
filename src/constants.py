# src/constants.py (既存の内容にWC Creator関連の定数を追加)
from PyQt6.QtCore import Qt

# --- Application Settings ---
APP_SETTINGS_FILE = "app_settings.json"

METADATA_ROLE = Qt.ItemDataRole.UserRole + 1
SELECTION_ORDER_ROLE = Qt.ItemDataRole.UserRole + 2

# Thumbnail right-click action settings
THUMBNAIL_RIGHT_CLICK_ACTION = "thumbnail_right_click_action"
RIGHT_CLICK_ACTION_METADATA = "metadata"
RIGHT_CLICK_ACTION_MENU = "menu"

# --- Image Preview Modes ---
PREVIEW_MODE_FIT = "fit"
PREVIEW_MODE_ORIGINAL_ZOOM = "original_zoom"

# --- ★★★ 追加: WC Creator コメント出力形式 ★★★ ---
WC_COMMENT_OUTPUT_FORMAT = "wc_creator_comment_format" # 設定ファイル保存時のキー名
WC_FORMAT_HASH_COMMENT = "separate_lines" # # コメント (従来の形式)
WC_FORMAT_BRACKET_COMMENT = "bracket_100" # [コメント:100] (新しい形式の例)
# --- ★★★ 追加: 空フォルダ削除設定 ★★★ ---
DELETE_EMPTY_FOLDERS_ENABLED = "delete_empty_folders_enabled"
# --- ★★★ 追加: ウィンドウジオメトリ設定 ★★★ ---
MAIN_WINDOW_GEOMETRY = "main_window_geometry"
METADATA_DIALOG_GEOMETRY = "metadata_dialog_geometry"

# --- ★★★ 追加: ファイル操作時の最終宛先フォルダ ★★★ ---
LAST_MOVE_DESTINATION_FOLDER = "last_move_destination_folder"
LAST_COPY_DESTINATION_FOLDER = "last_copy_destination_folder"

# --- ★★★ 追加終わり ★★★ ---

# --- Image File Extensions ---
# (drop_window.py から移動)
IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.heif']

# ★★★ フォルダ選択時の初期ソート設定 ★★★
INITIAL_SORT_ORDER_ON_FOLDER_SELECT = "initial_sort_order_on_folder_select"
SORT_BY_LOAD_ORDER_ALWAYS = "sort_by_load_order_always" # 常に読み込み順
SORT_BY_LAST_SELECTED = "sort_by_last_selected"         # 前回選択されたソート順を維持