# src/constants.py (既存の内容にWC Creator関連の定数を追加)
from PyQt6.QtCore import Qt

METADATA_ROLE = Qt.ItemDataRole.UserRole + 1
SELECTION_ORDER_ROLE = Qt.ItemDataRole.UserRole + 2

# Thumbnail right-click action settings
THUMBNAIL_RIGHT_CLICK_ACTION = "thumbnail_right_click_action"
RIGHT_CLICK_ACTION_METADATA = "metadata"
RIGHT_CLICK_ACTION_MENU = "menu"

# --- ★★★ 追加: WC Creator コメント出力形式 ★★★ ---
WC_COMMENT_OUTPUT_FORMAT = "wc_creator_comment_format" # 設定ファイル保存時のキー名
WC_FORMAT_HASH_COMMENT = "separate_lines" # # コメント (従来の形式)
WC_FORMAT_BRACKET_COMMENT = "bracket_100" # [コメント:100] (新しい形式の例)
# --- ★★★ 追加終わり ★★★ ---