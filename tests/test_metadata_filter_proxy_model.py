import pytest
from PyQt6.QtCore import QSortFilterProxyModel, Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem

# Assuming MetadataFilterProxyModel and METADATA_ROLE are accessible
# Adjust the import path as necessary based on your project structure
# For example, if 'src' is in sys.path or tests are run from project root:
from src.metadata_filter_proxy_model import MetadataFilterProxyModel
from src.main_window import METADATA_ROLE # Or wherever METADATA_ROLE is defined

@pytest.fixture
def source_model_with_data():
    model = QStandardItemModel()
    # Item 1: Matches "apple" in positive_prompt
    item1 = QStandardItem("Item 1")
    item1.setData({"positive_prompt": "an apple on a table", "negative_prompt": "banana", "generation_info": "test info 1"}, METADATA_ROLE)
    model.appendRow(item1)

    # Item 2: Matches "banana" in negative_prompt
    item2 = QStandardItem("Item 2")
    item2.setData({"positive_prompt": "orange", "negative_prompt": "a ripe banana", "generation_info": "test info 2"}, METADATA_ROLE)
    model.appendRow(item2)

    # Item 3: Matches "apple" and "orange"
    item3 = QStandardItem("Item 3")
    item3.setData({"positive_prompt": "apple, orange", "negative_prompt": "grape", "generation_info": "test info 3"}, METADATA_ROLE)
    model.appendRow(item3)
    
    # Item 4: No matching keywords for simple tests
    item4 = QStandardItem("Item 4")
    item4.setData({"positive_prompt": "kiwi", "negative_prompt": "grape", "generation_info": "test info 4"}, METADATA_ROLE)
    model.appendRow(item4)

    # Item 5: Missing negative_prompt and generation_info
    item5 = QStandardItem("Item 5")
    item5.setData({"positive_prompt": "sky"}, METADATA_ROLE)
    model.appendRow(item5)

    # Item 6: Empty positive_prompt
    item6 = QStandardItem("Item 6")
    item6.setData({"positive_prompt": "", "negative_prompt": "tree", "generation_info": "test info 6"}, METADATA_ROLE)
    model.appendRow(item6)
    return model

@pytest.fixture
def filter_proxy_model(source_model_with_data):
    proxy_model = MetadataFilterProxyModel()
    proxy_model.setSourceModel(source_model_with_data)
    return proxy_model

def test_filter_positive_prompt_exact_match(filter_proxy_model, source_model_with_data):
    """Test filtering by a single exact keyword in positive_prompt."""
    filter_proxy_model.set_positive_prompt_filter("apple")
    filter_proxy_model.set_negative_prompt_filter("")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND") # Explicitly set for clarity
    
    # Expected: Item 1 and Item 3 should match "apple"
    # The filterAcceptsRow method in the proxy model will determine visibility.
    # We check the rowCount of the proxy model.
    
    # To verify which items are visible, we can iterate through source model rows
    # and check if proxy_model.filterAcceptsRow(row, QModelIndex()) is true.
    # Or, more simply, check the rowCount of the proxy model.
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
        
    assert filter_proxy_model.rowCount() == 2
    assert "Item 1" in visible_item_texts
    assert "Item 3" in visible_item_texts

def test_filter_no_match(filter_proxy_model):
    """Test filtering with a keyword that matches no items."""
    filter_proxy_model.set_positive_prompt_filter("nonexistent_keyword")
    filter_proxy_model.set_negative_prompt_filter("")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND")
    
    assert filter_proxy_model.rowCount() == 0

def test_filter_cleared(filter_proxy_model, source_model_with_data):
    """Test if clearing filters shows all items."""
    # Apply some filter first
    filter_proxy_model.set_positive_prompt_filter("apple")
    assert filter_proxy_model.rowCount() < source_model_with_data.rowCount()
    
    # Clear filters
    filter_proxy_model.set_positive_prompt_filter("")
    filter_proxy_model.set_negative_prompt_filter("")
    filter_proxy_model.set_generation_info_filter("")
    
    assert filter_proxy_model.rowCount() == source_model_with_data.rowCount()

def test_filter_negative_prompt_exact_match(filter_proxy_model, source_model_with_data):
    """Test filtering by a single exact keyword in negative_prompt."""
    filter_proxy_model.set_positive_prompt_filter("")
    filter_proxy_model.set_negative_prompt_filter("banana")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND")
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
        
    # Item 1 ("banana") and Item 2 ("a ripe banana") should match
    assert filter_proxy_model.rowCount() == 2 
    assert "Item 1" in visible_item_texts
    assert "Item 2" in visible_item_texts

def test_filter_generation_info_exact_match(filter_proxy_model, source_model_with_data):
    """Test filtering by a single exact keyword in generation_info."""
    filter_proxy_model.set_positive_prompt_filter("")
    filter_proxy_model.set_negative_prompt_filter("")
    filter_proxy_model.set_generation_info_filter("test info 1")
    filter_proxy_model.set_search_mode("AND")
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
        
    assert filter_proxy_model.rowCount() == 1
    assert "Item 1" in visible_item_texts

def test_filter_and_search_multiple_fields(filter_proxy_model, source_model_with_data):
    """Test AND search across positive_prompt and negative_prompt."""
    # Item 1: positive_prompt: "an apple on a table", negative_prompt: "banana"
    filter_proxy_model.set_positive_prompt_filter("apple")
    filter_proxy_model.set_negative_prompt_filter("banana")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND")
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
        
    assert filter_proxy_model.rowCount() == 1
    assert "Item 1" in visible_item_texts

def test_filter_or_search_multiple_fields(filter_proxy_model, source_model_with_data):
    """Test OR search across positive_prompt and negative_prompt."""
    # Item 1: positive_prompt: "an apple on a table", negative_prompt: "banana"
    # Item 2: positive_prompt: "orange", negative_prompt: "a ripe banana"
    # Item 3: positive_prompt: "apple, orange"
    filter_proxy_model.set_positive_prompt_filter("table") # Matches Item 1
    filter_proxy_model.set_negative_prompt_filter("ripe")  # Matches Item 2
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("OR")
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
        
    assert filter_proxy_model.rowCount() == 2
    assert "Item 1" in visible_item_texts # Matches "table" in positive_prompt
    assert "Item 2" in visible_item_texts # Matches "ripe" in negative_prompt

def test_filter_positive_prompt_comma_separated_and_mode(filter_proxy_model, source_model_with_data):
    """Test filtering by comma-separated keywords in positive_prompt (AND logic within field)."""
    # Item 3: positive_prompt: "apple, orange"
    filter_proxy_model.set_positive_prompt_filter("apple, orange")
    filter_proxy_model.set_negative_prompt_filter("")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND") # This AND is for *between* fields.
                                          # _keywords_match also uses "AND" for keywords within a field by default.
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
        
    assert filter_proxy_model.rowCount() == 1
    assert "Item 3" in visible_item_texts

def test_filter_positive_prompt_comma_separated_or_mode(filter_proxy_model, source_model_with_data):
    """Test filtering by comma-separated keywords in positive_prompt (OR logic within field)."""
    # Item 1: positive_prompt: "an apple on a table"
    # Item 3: positive_prompt: "apple, orange"
    # We search for "table" OR "orange" in positive_prompt.
    # The overall search mode is OR, which also makes _keywords_match use OR for within-field keywords.
    filter_proxy_model.set_positive_prompt_filter("table, orange")
    filter_proxy_model.set_negative_prompt_filter("")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("OR") 
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
        
    # Item 1 matches "table"
    # Item 2 has "orange" in positive_prompt (from item2.setData in fixture)
    # Item 3 matches "orange" (and "apple")
    # So, Item 1, Item 2, and Item 3 should be visible.
    # Let's re-check fixture data for Item 2: positive_prompt: "orange"
    # Item 1: "an apple on a table" -> matches "table"
    # Item 2: "orange" -> matches "orange"
    # Item 3: "apple, orange" -> matches "orange"
    assert filter_proxy_model.rowCount() == 3
    assert "Item 1" in visible_item_texts
    assert "Item 2" in visible_item_texts
    assert "Item 3" in visible_item_texts

def test_filter_case_insensitivity(filter_proxy_model, source_model_with_data):
    """Test that filtering is case-insensitive."""
    # Item 1: positive_prompt: "an apple on a table"
    filter_proxy_model.set_positive_prompt_filter("APPLE") # Uppercase keyword
    filter_proxy_model.set_negative_prompt_filter("")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND")
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
        
    # Item 1 and Item 3 contain "apple" (case-insensitive)
    assert filter_proxy_model.rowCount() == 2
    assert "Item 1" in visible_item_texts
    assert "Item 3" in visible_item_texts

    # Test with mixed case in metadata and lowercase keyword
    # Modify Item 4's positive_prompt for this test case in the fixture if needed,
    # or add a new item. For now, let's assume Item 1's "apple" is sufficient.
    # Let's test negative prompt with mixed case
    # Item 2: negative_prompt: "a ripe banana"
    filter_proxy_model.set_positive_prompt_filter("")
    filter_proxy_model.set_negative_prompt_filter("BaNaNa") # Mixed case keyword
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)

    # Item 1 and Item 2 contain "banana" (case-insensitive)
    assert filter_proxy_model.rowCount() == 2
    assert "Item 1" in visible_item_texts
    assert "Item 2" in visible_item_texts

def test_filter_whitespace_stripping(filter_proxy_model, source_model_with_data):
    """Test that leading/trailing whitespace in filter keywords is stripped."""
    # Item 1: positive_prompt: "an apple on a table"
    filter_proxy_model.set_positive_prompt_filter(" apple ") # Keyword with spaces
    filter_proxy_model.set_negative_prompt_filter("")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND")
    
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
        
    # Item 1 and Item 3 contain "apple"
    assert filter_proxy_model.rowCount() == 2
    assert "Item 1" in visible_item_texts
    assert "Item 3" in visible_item_texts

    # Test with comma-separated keywords with spaces
    # Item 3: positive_prompt: "apple, orange"
    filter_proxy_model.set_positive_prompt_filter(" apple , orange ")
    visible_item_texts = []
    for i in range(filter_proxy_model.rowCount()):
        proxy_index = filter_proxy_model.index(i, 0)
        source_index = filter_proxy_model.mapToSource(proxy_index)
        item_text = source_model_with_data.itemFromIndex(source_index).text()
        visible_item_texts.append(item_text)
    
    assert filter_proxy_model.rowCount() == 1
    assert "Item 3" in visible_item_texts

def test_filter_empty_or_missing_metadata_fields(filter_proxy_model, source_model_with_data):
    """Test filtering behavior with items having empty or missing metadata fields."""
    # Case 1: Filter for "sky" in positive_prompt. Item 5 should match.
    # Other fields are empty/missing in Item 5, so they should pass if their filters are empty.
    filter_proxy_model.set_positive_prompt_filter("sky")
    filter_proxy_model.set_negative_prompt_filter("")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND")
    
    visible_item_texts = [filter_proxy_model.mapToSource(filter_proxy_model.index(i, 0)).data(Qt.ItemDataRole.DisplayRole) for i in range(filter_proxy_model.rowCount())]
    assert filter_proxy_model.rowCount() == 1
    assert "Item 5" in visible_item_texts

    # Case 2: Filter for "tree" in negative_prompt. Item 6 should match.
    # Item 6 has empty positive_prompt.
    filter_proxy_model.set_positive_prompt_filter("")
    filter_proxy_model.set_negative_prompt_filter("tree")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND")

    visible_item_texts = [filter_proxy_model.mapToSource(filter_proxy_model.index(i, 0)).data(Qt.ItemDataRole.DisplayRole) for i in range(filter_proxy_model.rowCount())]
    assert filter_proxy_model.rowCount() == 1
    assert "Item 6" in visible_item_texts

    # Case 3: Filter for something in positive_prompt that Item 6 (empty positive) shouldn't match.
    filter_proxy_model.set_positive_prompt_filter("anything")
    filter_proxy_model.set_negative_prompt_filter("tree") # Item 6 matches this
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("AND") # "anything" AND "tree"

    # Item 6 should NOT appear because its positive_prompt is "" which doesn't contain "anything".
    visible_item_texts = [filter_proxy_model.mapToSource(filter_proxy_model.index(i, 0)).data(Qt.ItemDataRole.DisplayRole) for i in range(filter_proxy_model.rowCount())]
    assert "Item 6" not in visible_item_texts
    assert filter_proxy_model.rowCount() == 0 # Assuming no other item matches "anything" AND "tree"

    # Case 4: OR mode, filter for "sky" (Item 5) OR "tree" (Item 6)
    filter_proxy_model.set_positive_prompt_filter("sky")
    filter_proxy_model.set_negative_prompt_filter("tree")
    filter_proxy_model.set_generation_info_filter("")
    filter_proxy_model.set_search_mode("OR")

    visible_item_texts = [filter_proxy_model.mapToSource(filter_proxy_model.index(i, 0)).data(Qt.ItemDataRole.DisplayRole) for i in range(filter_proxy_model.rowCount())]
    assert filter_proxy_model.rowCount() == 2
    assert "Item 5" in visible_item_texts
    assert "Item 6" in visible_item_texts


# Dummy test can be removed or kept for basic sanity check
# def test_dummy():
# """A dummy test to ensure pytest setup is working."""
# assert True
