import logging
import os # Import os for os.path.basename and os.path.getmtime
from PyQt6.QtCore import QSortFilterProxyModel, Qt, QVariant, QModelIndex # Import QModelIndex

logger = logging.getLogger(__name__)

# This should match the METADATA_ROLE in main_window.py
METADATA_ROLE = Qt.ItemDataRole.UserRole + 1

class MetadataFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._positive_prompt_filter = ""
        self._negative_prompt_filter = ""
        self._generation_info_filter = ""
        self._search_mode = "AND"  # Default search mode
        # --- ★ フィルタキーワードをキャッシュするためのメンバ変数を追加 ---
        self._positive_keywords_cache = []
        self._negative_keywords_cache = []
        self._generation_keywords_cache = []
        # --- ★ ここまで ---
        self._hidden_paths = set() # Set of file paths to hide
        self.setDynamicSortFilter(False) # ソートは明示的に sort() で行う
        # Filter on all columns by default, though we use custom data roles
        self.setFilterKeyColumn(-1) 
        self.setSortRole(METADATA_ROLE) # ソートにMETADATA_ROLEを使用
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        # カスタムソート用のキータイプ (0: ファイル名, 1: 更新日時)
        self._sort_key_type = 0 

    def set_sort_key_type(self, key_type: int):
        """ソートに使用するキーのタイプを設定します (0: ファイル名, 1: 更新日時)。"""
        logger.debug(f"MetadataFilterProxyModel.set_sort_key_type called. key_type: {key_type}")
        if self._sort_key_type != key_type:
            self._sort_key_type = key_type
            # invalidate() や invalidateFilter() はここでは不要。
            # sort() が呼び出されたときに再ソートされる。

    # def sort(self, column: int, order: Qt.SortOrder) -> None:
    #     logger.debug(f"MetadataFilterProxyModel.sort() OVERRIDE called. Column: {column}, Order: {order}. Current internal criteria: key_index={self.sort_key_index}, order={self.sort_order}")
        # Ensure our custom criteria (self.sort_key_index and self.sort_order) are set by set_sort_criteria
        # before this sort is called.
        # The 'order' parameter passed to super().sort() should align with self.sort_order.
        
        # It's crucial to emit signals around the sort operation if we override sort.
        # This tells the views that the model is about to change and then has changed.
        
        # Invalidate any existing sort/filter before applying a new one.
        # This might help ensure that the model correctly rebuilds its internal mapping.
        # logger.debug("Calling self.invalidate() at the beginning of overridden sort().")
        # self.invalidate()

        # self.beginResetModel()
        # Call the base class's sort implementation.
        # We use self.sort_order which should have been set by set_sort_criteria
        # and should be consistent with the 'order' parameter if MainWindow calls this correctly.
        # The 'column' parameter here is the one QSortFilterProxyModel will store internally.
        # Since our lessThan and data methods use self.sort_key_index, the actual column value
        # passed to super().sort() might be less critical for the comparison logic itself,
        # but it's important for the model's internal state (e.g., what sortColumn() returns).
        # We'll use the column passed from apply_internal_sort (which is 0).
        # super().sort(column, self.sort_order) 
        # self.endResetModel()
        # logger.debug(f"MetadataFilterProxyModel.sort() OVERRIDE finished. Proxy sortColumn: {self.sortColumn()}, sortOrder: {self.sortOrder()}")

    def set_search_mode(self, mode):
        if mode in ["AND", "OR"]:
            self._search_mode = mode
            self.invalidateFilter()
        else:
            logger.warning(f"Invalid search mode: {mode}. Keeping {self._search_mode}.")

    def set_hidden_paths(self, paths):
        """Sets the set of file paths that should be hidden by the filter."""
        # Ensure we are working with a set for efficient lookups
        self._hidden_paths = set(paths) if paths is not None else set()
        # invalidateFilter() will be called by the caller (MainWindow) after setting paths

    def set_positive_prompt_filter(self, text):
        self._positive_prompt_filter = text.lower()
        # --- ★ キーワードをキャッシュ ---
        self._positive_keywords_cache = [kw.strip() for kw in self._positive_prompt_filter.split(',') if kw.strip()]
        # --- ★ ここまで ---
        self.invalidateFilter() # Re-apply the filter

    def set_negative_prompt_filter(self, text):
        self._negative_prompt_filter = text.lower()
        # --- ★ キーワードをキャッシュ ---
        self._negative_keywords_cache = [kw.strip() for kw in self._negative_prompt_filter.split(',') if kw.strip()]
        # --- ★ ここまで ---
        self.invalidateFilter()

    def set_generation_info_filter(self, text):
        self._generation_info_filter = text.lower()
        # --- ★ キーワードをキャッシュ ---
        self._generation_keywords_cache = [kw.strip() for kw in self._generation_info_filter.split(',') if kw.strip()]
        # --- ★ ここまで ---
        self.invalidateFilter()

    def _keywords_match(self, text_to_search, filter_keywords):
        """Helper to check if keywords match text based on current search mode."""
        # filter_keywords は既に小文字化され、リストになっている前提
        if not filter_keywords: # No keywords to filter by for this field
            return True
        
        # --- ★ text_to_search は呼び出し元で一度だけ小文字化する ---
        # text_to_search_lower = text_to_search.lower() 

        if self._search_mode == "AND":
            return all(keyword in text_to_search for keyword in filter_keywords) # text_to_search は既に小文字
        elif self._search_mode == "OR":
            return any(keyword in text_to_search for keyword in filter_keywords) # text_to_search は既に小文字
        return False # Should not happen

    def filterAcceptsRow(self, source_row, source_parent):
        """
        Determines if a row from the source model should be included in the proxy model.
        """
        # --- Check if the item's file path is in the hidden list ---
        # This check should happen first, before any metadata filtering.
        source_index_for_path = self.sourceModel().index(source_row, 0, source_parent)
        file_path_for_hiding_check = self.sourceModel().data(source_index_for_path, Qt.ItemDataRole.UserRole)
        
        if file_path_for_hiding_check and file_path_for_hiding_check in self._hidden_paths:
            # logger.debug(f"filterAcceptsRow: Hiding row {source_row} (path: '{file_path_for_hiding_check}') because it is in hidden list.")
            return False # Hide this row
        # --- End hidden path check ---

        # logger.debug(f"filterAcceptsRow: Processing source_row={source_row}, path='{file_path_for_hiding_check}'. Filters(P='{self._positive_prompt_filter}', N='{self._negative_prompt_filter}', G='{self._generation_info_filter}'), mode='{self._search_mode}'")

        # ソート問題用
        # logger.debug(f"filterAcceptsRow: START - source_row={source_row}, filters(P='{self._positive_prompt_filter}', N='{self._negative_prompt_filter}', G='{self._generation_info_filter}'), mode='{self._search_mode}'") # DEBUGに変更
        if not self.sourceModel():
            # ソート問題用
            # logger.info(f"filterAcceptsRow: END - No source model. Returning False for row {source_row}.")
            return False

        source_index = self.sourceModel().index(source_row, 0, source_parent)
        if not source_index.isValid():
            # ソート問題用
            # logger.info(f"filterAcceptsRow: END - Invalid source_index for row {source_row}. Returning False.")
            return False

        metadata = self.sourceModel().data(source_index, METADATA_ROLE)
        # logger.debug(f"  filterAcceptsRow: Metadata for row {source_row}: {str(metadata)[:200]}") # Log first 200 chars of metadata
        
        if not isinstance(metadata, dict):
            # If no metadata, only pass if all filter fields are empty
            result = not self._positive_prompt_filter and \
                     not self._negative_prompt_filter and \
                     not self._generation_info_filter
            # logger.debug(f"filterAcceptsRow (no metadata): Filters empty? P: {not self._positive_prompt_filter}, N: {not self._negative_prompt_filter}, G: {not self._generation_info_filter}. Result: {result}")
            # logger.debug(f"filterAcceptsRow: END - No metadata for row {source_row}. Returning {result}.")
            return result

        # --- ★ メタデータからテキストを取得し、一度だけ小文字化 ---
        positive_text_lower = metadata.get('positive_prompt', '').lower()
        negative_text_lower = metadata.get('negative_prompt', '').lower()
        generation_text_lower = metadata.get('generation_info', '').lower()
        # --- ★ ここまで ---

        # --- Apply filters for each field ---
        # Each field must satisfy its own keyword search (AND/OR based on self._search_mode)
        # The results of these per-field checks are then ANDed together.

        # --- Apply filters for each field ---
        # The _keywords_match helper itself respects the AND/OR mode for keywords *within* a single field.
        # Now we need to combine the results from different fields based on the overall search mode.
        # --- ★ キャッシュされたキーワードと小文字化済みのテキストを使用 ---
        positive_match_field = self._keywords_match(positive_text_lower, self._positive_keywords_cache)
        negative_match_field = self._keywords_match(negative_text_lower, self._negative_keywords_cache)
        generation_match_field = self._keywords_match(generation_text_lower, self._generation_keywords_cache)
        # --- ★ ここまで ---
        # logger.debug(f"  filterAcceptsRow: Field matches for row {source_row} - P_match: {positive_match_field}, N_match: {negative_match_field}, G_match: {generation_match_field}")

        if self._search_mode == "AND":
            # For AND mode, all active filters must be true.
            # If a filter text is empty, its corresponding _match_field will be True from _keywords_match,
            # so it doesn't prevent a match if other fields match.
            final_and_result = positive_match_field and negative_match_field and generation_match_field
            # logger.debug(f"  filterAcceptsRow (AND mode): Final result for row {source_row} (path: '{file_path_for_hiding_check}'): {final_and_result}")
            # logger.info(f"filterAcceptsRow: END - AND mode for row {source_row}. Returning {final_and_result}.")
            return final_and_result
        
        elif self._search_mode == "OR":
            # For OR mode, at least one active filter must be true.
            # A field is considered "active" for OR if its filter text is not empty.
            # If all filter texts are empty, then all items should pass (handled by _keywords_match returning True).
            # --- ★ キャッシュされたキーワードリストの空チェックに変更 ---
            # If all filter texts are empty, all _match_field will be True, so it returns True.
            if not self._positive_keywords_cache and not self._negative_keywords_cache and not self._generation_keywords_cache:
                # ソート問題用
                #logger.info(f"  filterAcceptsRow (OR mode): No active keywords for row {source_row}. Returning True.")
                #logger.info(f"filterAcceptsRow: END - OR mode (no active keywords) for row {source_row}. Returning True.")
                return True

            # At least one filter text is active. Accept if any *active* field matches.
            accepted_by_or = False
            if self._positive_keywords_cache and positive_match_field:
                accepted_by_or = True
            if self._negative_keywords_cache and negative_match_field:
                accepted_by_or = True
            if self._generation_keywords_cache and generation_match_field:
                accepted_by_or = True
            # ソート問題用
            # logger.info(f"  filterAcceptsRow (OR mode): Initial accepted_by_or for row {source_row}: {accepted_by_or} (based on active fields matching)")
            
            # If no filter texts were active (e.g. all were empty strings but not None),
            # the above logic might not set accepted_by_or.
            # However, the _keywords_match for empty filter_keywords returns True.
            # The logic needs to be: if any field has keywords AND matches, it's an OR pass.
            # If a field has NO keywords, it does not contribute to an OR pass, nor does it block it.
            
            # Refined OR logic:
            # If any field has keywords and its specific match is true, then the row is accepted.
            # If all fields that *have* keywords do *not* match, then the row is rejected.
            # If no fields have keywords, the row is accepted (as per _keywords_match behavior).

            # Let's list the results of active filters
            active_filter_results = []
            if self._positive_keywords_cache:
                active_filter_results.append(positive_match_field)
            if self._negative_keywords_cache:
                active_filter_results.append(negative_match_field)
            if self._generation_keywords_cache:
                active_filter_results.append(generation_match_field)
            # ソート問題用
            # logger.info(f"  filterAcceptsRow (OR mode): Active filter results list for row {source_row}: {active_filter_results}")
            
            if not active_filter_results: # No active filters (all filter texts were empty)
                # This case should have been caught by the "if not positive_keywords and not negative_keywords..." check above.
                # However, keeping it as a safeguard or for clarity.
                # ソート問題用
                # logger.info(f"  filterAcceptsRow (OR mode): No active_filter_results (should be redundant check) for row {source_row}. Returning True.")
                # logger.info(f"filterAcceptsRow: END - OR mode (no active_filter_results) for row {source_row}. Returning True.")
                return True # All items pass
            
            final_or_result = any(active_filter_results)
            # logger.debug(f"  filterAcceptsRow (OR mode): Final OR result for row {source_row} (path: '{file_path_for_hiding_check}') from 'any(active_filter_results)': {final_or_result}")
            # logger.info(f"filterAcceptsRow: END - OR mode for row {source_row}. Returning {final_or_result}.")
            return final_or_result

        # logger.warning(f"filterAcceptsRow: Unknown search mode '{self._search_mode}' for row {source_row} (path: '{file_path_for_hiding_check}'). Returning False.") # 通常は発生しないはずなのでコメントアウト
        return False # Should not be reached if mode is AND/OR

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> QVariant:
        """
        Returns the data for the given role and index, customized for sorting.
        """
        # if role == self.sortRole(): # self.sortRole() should be METADATA_ROLE
            # Provide the actual data to be used for sorting based on current sort_key_index
            # source_index = self.mapToSource(index)
            # if not source_index.isValid():
            #     return QVariant()

            # Get the original file path from the source model using UserRole
            # file_path = self.sourceModel().data(source_index, Qt.ItemDataRole.UserRole) 
            # if file_path is None:
            #     return QVariant()

            # if self.sort_key_index == 0: # Filename
            #     return QVariant(os.path.basename(file_path).lower())
            # elif self.sort_key_index == 1: # Modification date
            #     try:
            #         return QVariant(float(os.path.getmtime(file_path))) # Ensure float for QVariant
            #     except FileNotFoundError:
            #         logger.warning(f"data(): FileNotFoundError for {file_path}. Returning 0 for mtime.")
            #         return QVariant(0.0) # Treat missing files as very old for sorting
            #     except Exception as e:
            #         logger.error(f"Error getting mtime for {file_path} in data(): {e}")
            #         return QVariant(0.0)
            # else: # Should not happen
            #     logger.warning(f"data(): Unknown sort_key_index: {self.sort_key_index}. Returning empty QVariant.")
            #     return QVariant() 
        return super().data(index, role)
    
    def lessThan(self, source_left: QModelIndex, source_right: QModelIndex) -> bool:
        """
        カスタム比較ロジック。source_left と source_right はソースモデルのインデックス。
        QSortFilterProxyModel はこのメソッドの結果と sortOrder() を組み合わせてソートする。
        このメソッドは常に「昇順の場合の比較」を行う。
        """
        if not source_left.isValid() or not source_right.isValid():
            logger.debug("lessThan: one or both QModelIndex invalid.")
            return False

        # METADATA_ROLE からキャッシュされたメタデータ辞書を取得
        left_metadata = self.sourceModel().data(source_left, METADATA_ROLE)
        right_metadata = self.sourceModel().data(source_right, METADATA_ROLE)
        # logger.debug(f"lessThan: Left metadata ({source_left.row()}): {left_metadata}, Right metadata ({source_right.row()}): {right_metadata}")

        if not isinstance(left_metadata, dict) or not isinstance(right_metadata, dict):
            logger.warning(f"lessThan: Metadata is not a dict. Left: {type(left_metadata)}, Right: {type(right_metadata)}. Returning False.")
            # メタデータがない場合は、ファイルパスから取得しようと試みる (フォールバック、理想的には不要)
            # ただし、パフォーマンスのため、ここでは単純にFalseを返すか、ファイル名での比較にフォールバックする
            # 今回は、METADATA_ROLEに必ず必要な情報が含まれている前提とする
            return False 

        val_left = None
        val_right = None

        if self._sort_key_type == 0: # ファイル名でソート
            val_left = left_metadata.get('filename_for_sort', '') # キャッシュされたファイル名を使用
            val_right = right_metadata.get('filename_for_sort', '')
            # logger.debug(f"lessThan (Filename): Comparing '{val_left}' with '{val_right}'")
        elif self._sort_key_type == 1: # 更新日時でソート
            val_left = left_metadata.get('update_timestamp', 0.0) # キャッシュされた更新日時を使用
            val_right = right_metadata.get('update_timestamp', 0.0)
            # logger.debug(f"lessThan (ModDate): Comparing {val_left} with {val_right}")
        else:
            logger.warning(f"lessThan: Unknown _sort_key_type: {self._sort_key_type}. Falling back to False.")
            return False

        if val_left is None or val_right is None:
             # 通常、getのデフォルト値でNoneは回避されるはずだが念のため
             logger.debug(f"lessThan: val_left or val_right is None after key processing. Left: {val_left}, Right: {val_right}. Returning False.")
             return False

        # 常に昇順で比較 (val_left < val_right)
        # QSortFilterProxyModelが sortOrder() に基づいて結果を解釈する
        return val_left < val_right
