"""Selection and copy order are path based and survive proxy changes."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListView, QAbstractItemView
from PyQt6.QtGui import QStandardItem, QStandardItemModel

from src.constants import METADATA_ROLE, SELECTION_ORDER_ROLE
from src.metadata_filter_proxy_model import MetadataFilterProxyModel
from src.selection_controller import SelectionController


class _Thumbnails:
    def __init__(self, model, items):
        self.source_model = model
        self.items = items

    def item_for_path(self, path):
        return self.items.get(path)


def _setup(qapplication):
    source = QStandardItemModel()
    items = {}
    records = (
        ("/images/cat.png", "cat portrait"),
        ("/images/dog.png", "dog portrait"),
        ("/images/fox.png", "fox portrait"),
    )
    for path, prompt in records:
        item = QStandardItem(path.rsplit("/", 1)[-1])
        item.setData(path, Qt.ItemDataRole.UserRole)
        item.setData({"positive_prompt": prompt, "negative_prompt": "", "generation_info": "",
                      "filename_for_sort": item.text(), "update_timestamp": 0.0}, METADATA_ROLE)
        source.appendRow(item)
        items[path] = item
    proxy = MetadataFilterProxyModel()
    proxy.setSourceModel(source)
    view = QListView()
    view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    view.setModel(proxy)
    thumbnails = _Thumbnails(source, items)
    selection = SelectionController(thumbnails, proxy, view)
    return source, proxy, view, items, selection


def test_copy_selection_tracks_paths_in_user_order_and_renumbers(qapplication):
    source, _proxy, _view, items, selection = _setup(qapplication)
    first, second = "/images/dog.png", "/images/cat.png"
    selection.set_copy_mode(True)

    selection.toggle(first)
    selection.toggle(second)

    assert selection.is_selected(first)
    assert selection.selected_paths() == (first, second)
    assert selection.copy_paths() == (first, second)
    assert items[first].data(SELECTION_ORDER_ROLE) == 1
    assert items[second].data(SELECTION_ORDER_ROLE) == 2

    selection.toggle(first)

    assert selection.selected_paths() == (second,)
    assert selection.copy_paths() == (second,)
    assert items[first].data(SELECTION_ORDER_ROLE) is None
    assert items[second].data(SELECTION_ORDER_ROLE) == 1


def test_filter_drops_hidden_selection_and_preserves_visible_copy_order(qapplication):
    _source, _proxy, _view, items, selection = _setup(qapplication)
    dog, cat = "/images/dog.png", "/images/cat.png"
    selection.set_copy_mode(True)
    selection.toggle(dog)
    selection.toggle(cat)

    selection.apply_filters("cat", "", "", "AND", preserve_selection=True)

    assert selection.selected_paths() == (cat,)
    assert selection.copy_paths() == (cat,)
    assert items[dog].data(SELECTION_ORDER_ROLE) is None
    assert items[cat].data(SELECTION_ORDER_ROLE) == 1


def test_filter_can_clear_selection_and_sort_preserves_selection(qapplication):
    _source, proxy, _view, _items, selection = _setup(qapplication)
    cat, dog = "/images/cat.png", "/images/dog.png"
    selection.set_copy_mode(True)
    selection.toggle(dog)
    selection.toggle(cat)

    selection.apply_sort(0, Qt.SortOrder.DescendingOrder)
    assert selection.selected_paths() == (dog, cat)
    assert selection.copy_paths() == (dog, cat)

    selection.apply_filters("fox", "", "", "AND", preserve_selection=False)
    assert selection.selected_paths() == ()
    assert selection.copy_paths() == ()
    assert proxy.rowCount() == 1


def test_clear_and_remove_paths_clear_only_selection_state(qapplication):
    source, _proxy, _view, items, selection = _setup(qapplication)
    selection.set_copy_mode(True)
    selection.toggle("/images/cat.png")
    selection.toggle("/images/dog.png")

    selection.remove_paths(["/images/cat.png"])
    assert selection.selected_paths() == ("/images/dog.png",)
    assert selection.copy_paths() == ("/images/dog.png",)
    assert source.rowCount() == 3
    assert items["/images/cat.png"].data(SELECTION_ORDER_ROLE) is None

    selection.clear()
    assert selection.selected_paths() == ()
    assert selection.copy_paths() == ()
    assert source.rowCount() == 3


def test_select_all_and_and_or_filter_semantics(qapplication):
    _source, proxy, view, _items, selection = _setup(qapplication)
    selection.select_all()
    assert len(selection.selected_paths()) == 3

    selection.apply_filters("cat,fox", "", "", "AND", preserve_selection=False)
    assert proxy.rowCount() == 0
    assert selection.selected_paths() == ()

    selection.apply_filters("cat,fox", "", "", "OR", preserve_selection=False)
    assert proxy.rowCount() == 2
    view.selectAll()
    selection.sync_from_view()
    assert set(selection.selected_paths()) == {"/images/cat.png", "/images/fox.png"}
