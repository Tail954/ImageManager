import logging
from PyQt6.QtCore import QSortFilterProxyModel, Qt, QVariant

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
        # Enable dynamic filtering. When the source model changes, the filter is reapplied.
        self.setDynamicSortFilter(True) 
        # Filter on all columns by default, though we use custom data roles
        self.setFilterKeyColumn(-1) 

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
        if not self.sourceModel():
            return False

        source_index = self.sourceModel().index(source_row, 0, source_parent)
        if not source_index.isValid():
            return False

        metadata = self.sourceModel().data(source_index, METADATA_ROLE)
        
        if not isinstance(metadata, dict):
            # If no metadata, only pass if all filter fields are empty
            return not self._positive_prompt_filter and \
                   not self._negative_prompt_filter and \
                   not self._generation_info_filter

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
            
            return any(active_filter_results) # If any active filter matched, pass

        return False # Should not be reached if mode is AND/OR
