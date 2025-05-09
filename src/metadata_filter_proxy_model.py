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

        # Positive Prompt Filter
        positive_match = self._keywords_match(metadata.get('positive_prompt', ''), positive_keywords)
        if not positive_match:
            return False

        # Negative Prompt Filter
        negative_match = self._keywords_match(metadata.get('negative_prompt', ''), negative_keywords)
        if not negative_match:
            return False

        # Generation Info Filter
        generation_match = self._keywords_match(metadata.get('generation_info', ''), generation_keywords)
        if not generation_match:
            return False
        
        return True # Row is accepted if all field filters pass
