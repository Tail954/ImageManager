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
        # Disable dynamic filtering to rely on explicit calls to sort() and invalidateFilter().
        # self.setDynamicSortFilter(False) 
        # Filter on all columns by default, though we use custom data roles
        self.setFilterKeyColumn(-1) 
        # self.setSortRole(METADATA_ROLE) # Explicitly set a sort role
        # self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive) # Add this line
        
        # For custom sorting
        # self.sort_key_index = 0  # 0 for filename, 1 for modification date
        # self.sort_order = Qt.SortOrder.AscendingOrder

    # def set_sort_criteria(self, key_index, order):
    #     """Sets the criteria for sorting."""
    #     logger.debug(f"MetadataFilterProxyModel.set_sort_criteria called. key_index: {key_index}, order: {order}")
    #     self.sort_key_index = key_index
    #     self.sort_order = order # Our custom state for lessThan
        
        # Set the QSortFilterProxyModel's native sort order.
        # The sort column can be a dummy one (e.g., 0) as our lessThan uses sort_key_index.
        # However, it's crucial that QSortFilterProxyModel itself is told to sort.
        # self.setSortOrder(order) # This was incorrect. sortOrder is a property accessed by sortOrder() or set via sort().
        # self.setSortColumn(0) # Set a consistent sort column if needed, though lessThan might ignore it.
                             # Let's rely on the sort() call from MainWindow for now to specify column.

        # logger.debug(f"Internal sort order set to: {self.sortOrder()}, sort column: {self.sortColumn()}") # This would call the getter
        
        # self.invalidate() # This should make the model re-filter and re-sort when sort() is called.
        # The actual sort() call will be made from MainWindow after this.
        # Let's test without this invalidate() to see if it has an adverse effect on explicit sort()
        # logger.debug("Skipping self.invalidate() in set_sort_criteria for testing.")

    # def apply_internal_sort(self, column: int, order: Qt.SortOrder):
    #     """
    #     Internal method to apply sorting, intended to be called after set_sort_criteria.
    #     This ensures that self.sort_key_index and self.sort_order are up-to-date.
    #     """
    #     logger.debug(f"MetadataFilterProxyModel.apply_internal_sort called. Column from MW: {column}, Order from MW: {order}. Using internal criteria: key_index={self.sort_key_index}, order={self.sort_order}. Will call super().sort(0, self.sort_order).")
        # We call super().sort() directly here.
        # We will use column 0 for the super().sort() call, as our METADATA_ROLE data
        # is not tied to a specific column in the source model in a multi-column sense,
        # and our lessThan uses self.sort_key_index.
        # The 'order' parameter (from MainWindow, via self.sort_order) should be consistent.
        # Instead of calling super().sort() directly, call our overridden sort method.
        # self.sort(0, self.sort_order) # Call the overridden sort method.
        # logger.debug(f"MetadataFilterProxyModel.apply_internal_sort finished (called self.sort(0, {self.sort_order})). Current proxy sortColumn: {self.sortColumn()}, sortOrder: {self.sortOrder()}")

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

    def set_positive_prompt_filter(self, text):
        self._positive_prompt_filter = text.lower()
        self.invalidateFilter() # Re-apply the filter

    def set_negative_prompt_filter(self, text):
        self._negative_prompt_filter = text.lower()
        self.invalidateFilter()

    def set_generation_info_filter(self, text):
        self._generation_info_filter = text.lower()
        self.invalidateFilter()

    def _keywords_match(self, text_to_search, filter_keywords):
        """Helper to check if keywords match text based on current search mode."""
        if not filter_keywords: # No keywords to filter by for this field
            return True
        
        text_to_search_lower = text_to_search.lower()

        if self._search_mode == "AND":
            return all(keyword in text_to_search_lower for keyword in filter_keywords)
        elif self._search_mode == "OR":
            return any(keyword in text_to_search_lower for keyword in filter_keywords)
        return False # Should not happen

    def filterAcceptsRow(self, source_row, source_parent):
        """
        Determines if a row from the source model should be included in the proxy model.
        """
        logger.debug(f"filterAcceptsRow called for source_row: {source_row}")
        if not self.sourceModel():
            logger.debug("filterAcceptsRow: No source model. Returning False.")
            return False

        source_index = self.sourceModel().index(source_row, 0, source_parent)
        if not source_index.isValid():
            return False

        metadata = self.sourceModel().data(source_index, METADATA_ROLE)
        
        if not isinstance(metadata, dict):
            # If no metadata, only pass if all filter fields are empty
            result = not self._positive_prompt_filter and \
                     not self._negative_prompt_filter and \
                     not self._generation_info_filter
            logger.debug(f"filterAcceptsRow (no metadata): Filters empty? P: {not self._positive_prompt_filter}, N: {not self._negative_prompt_filter}, G: {not self._generation_info_filter}. Result: {result}")
            return result

        # --- Prepare keywords for each filter field ---
        # Split by comma, strip whitespace, and filter out empty strings
        positive_keywords = [kw.strip() for kw in self._positive_prompt_filter.split(',') if kw.strip()]
        negative_keywords = [kw.strip() for kw in self._negative_prompt_filter.split(',') if kw.strip()]
        generation_keywords = [kw.strip() for kw in self._generation_info_filter.split(',') if kw.strip()]

        # --- Apply filters for each field ---
        # Each field must satisfy its own keyword search (AND/OR based on self._search_mode)
        # The results of these per-field checks are then ANDed together.

        # --- Apply filters for each field ---
        # The _keywords_match helper itself respects the AND/OR mode for keywords *within* a single field.
        # Now we need to combine the results from different fields based on the overall search mode.

        positive_match_field = self._keywords_match(metadata.get('positive_prompt', ''), positive_keywords)
        negative_match_field = self._keywords_match(metadata.get('negative_prompt', ''), negative_keywords)
        generation_match_field = self._keywords_match(metadata.get('generation_info', ''), generation_keywords)

        if self._search_mode == "AND":
            # For AND mode, all active filters must be true.
            # If a filter text is empty, its corresponding _match_field will be True from _keywords_match,
            # so it doesn't prevent a match if other fields match.
            return positive_match_field and negative_match_field and generation_match_field
        
        elif self._search_mode == "OR":
            # For OR mode, at least one active filter must be true.
            # A field is considered "active" for OR if its filter text is not empty.
            # If all filter texts are empty, then all items should pass (handled by _keywords_match returning True).
            
            # If all filter texts are empty, all _match_field will be True, so it returns True.
            if not positive_keywords and not negative_keywords and not generation_keywords:
                return True

            # At least one filter text is active. Accept if any active field matches.
            accepted_by_or = False
            if positive_keywords and positive_match_field:
                accepted_by_or = True
            if negative_keywords and negative_match_field:
                accepted_by_or = True
            if generation_keywords and generation_match_field:
                accepted_by_or = True
            
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
            if positive_keywords:
                active_filter_results.append(positive_match_field)
            if negative_keywords:
                active_filter_results.append(negative_match_field)
            if generation_keywords:
                active_filter_results.append(generation_match_field)
            
            if not active_filter_results: # No active filters (all filter texts were empty)
                return True # All items pass
            
            final_or_result = any(active_filter_results)
            logger.debug(f"filterAcceptsRow (OR mode): Active filter results: {active_filter_results}. Final OR result: {final_or_result}")
            return final_or_result

        logger.debug("filterAcceptsRow: Unknown search mode. Returning False.")
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

    # def lessThan(self, source_left: QModelIndex, source_right: QModelIndex) -> bool:
    #     """
    #     Custom comparison logic for sorting items.
    #     source_left and source_right are QModelIndex objects from the source model.
    #     NOTE: With the overridden data() method providing sort-specific data for sortRole,
    #     this lessThan might not be strictly necessary if the default lessThan behavior
    #     on the data returned by data(index, sortRole()) is sufficient.
    #     However, keeping it allows for more complex or nuanced comparisons if needed,
    #     and ensures our explicit logging remains.
    #     The QSortFilterProxyModel will call this method with source model indexes.
    #     """
    #     logger.info(f"lessThan CALLED. Left: {source_left.row()}, Right: {source_right.row()}. SortKeyIndex: {self.sort_key_index}, SortOrder: {self.sort_order}, SortRole: {self.sortRole()}")
    #     if not source_left.isValid() or not source_right.isValid():
    #         logger.debug("lessThan: one or both QModelIndex invalid.")
    #         return False

        # When lessThan is called by the proxy model's sort, it uses source model indexes.
        # We can directly get the sort-relevant data from the source model items
        # using our internal sort_key_index and sort_order.

        # left_path = self.sourceModel().data(source_left, Qt.ItemDataRole.UserRole)
        # right_path = self.sourceModel().data(source_right, Qt.ItemDataRole.UserRole)
        
        # # logger.debug(f"lessThan DATA: Comparing Left Path: '{left_path}', Right Path: '{right_path}'.")

        # if left_path is None or right_path is None:
        #     logger.debug(f"lessThan: Path is None. Left: {left_path}, Right: {right_path}. Returning False.")
        #     return False

        # val_left = None
        # val_right = None

        # if self.sort_key_index == 0: # Sort by filename
        #     val_left = os.path.basename(left_path).lower()
        #     val_right = os.path.basename(right_path).lower()
        #     logger.debug(f"lessThan (Filename): Comparing val_left='{val_left}' (type: {type(val_left)}) with val_right='{val_right}' (type: {type(val_right)})")
        # elif self.sort_key_index == 1: # Sort by modification date
        #     try:
        #         val_left = os.path.getmtime(left_path)
        #         val_right = os.path.getmtime(right_path)
        #         logger.debug(f"lessThan (ModDate): Comparing val_left={val_left} (type: {type(val_left)}) with val_right={val_right} (type: {type(val_right)})")
        #     except FileNotFoundError as e:
        #         logger.warning(f"lessThan (ModDate): FileNotFoundError for {e.filename}. Left path: {left_path}, Right path: {right_path}")
        #         if not os.path.exists(left_path) and not os.path.exists(right_path):
        #             return False 
        #         elif not os.path.exists(left_path): # left missing, right exists: left is "smaller" (older) if asc, "larger" if desc
        #             return self.sort_order == Qt.SortOrder.AscendingOrder
        #         elif not os.path.exists(right_path): # right missing, left exists: left is "larger" (newer) if asc, "smaller" if desc
        #             return self.sort_order == Qt.SortOrder.DescendingOrder
        #         return False # Should not happen if one must exist
        #     except Exception as e:
        #         logger.error(f"lessThan (ModDate): Error getting mtime for {left_path} or {right_path}: {e}", exc_info=True)
        #         return False 
        # else:
        #     logger.warning(f"lessThan: Unknown sort_key_index: {self.sort_key_index}. Falling back to False.")
        #     return False


        # if val_left is None or val_right is None:
        #     logger.debug(f"lessThan: val_left or val_right is None after key processing. Left: {val_left}, Right: {val_right}. Returning False.")
        #     return False 

        # result = False
        # if self.sort_order == Qt.SortOrder.AscendingOrder:
        #     result = val_left < val_right
        # else:
        #     result = val_left > val_right
        
        # logger.info(f"lessThan: Final Comparison: val_left='{val_left}', val_right='{val_right}'. SortOrder: {self.sort_order}. Result: {result}")
        # return result
