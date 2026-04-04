import os
import yaml
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QScrollArea, QPushButton, QLabel, QApplication, QSizePolicy, QFileDialog
)
from PyQt6.QtCore import Qt, QEvent, QByteArray

from .flow_layout import FlowLayout
from .toast_widget import ToastWidget
from .constants import TAGS_FOLDER_PATH, DEFAULT_TAGS_FOLDER, TAG_PALETTE_GEOMETRY, TAG_PALETTE_SPLITTER_STATE

logger = logging.getLogger(__name__)

class OrderedLoader(yaml.SafeLoader):
    pass

def construct_mapping(loader, node):
    loader.flatten_mapping(node)
    return dict(loader.construct_pairs(node))

OrderedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_mapping)

class DataWrapper:
    """ PyQtのQVariant変換によってdictの順序が意図せずソートされるのを防ぐためのラッパー """
    def __init__(self, data):
        self.data = data

class TagPaletteWindow(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.main_window = main_window
        self.setWindowTitle("タグパレット")
        self.resize(800, 600)
        
        # Tags directory check
        self.tags_dir = self.main_window.app_settings.get(TAGS_FOLDER_PATH, DEFAULT_TAGS_FOLDER)
        
        self.selected_tags = {}  # Use dict to keep order of added tags (Python 3.7+)
        self.button_widgets = []    # Keep references to keep state

        self.toast = ToastWidget(self)

        self._setup_ui()
        
        # tags_dirが設定されていないか、ディレクトリが存在しない場合のみダイアログを出す
        if not self.tags_dir or not os.path.isdir(self.tags_dir):
            if not self._select_tags_directory():
                logger.warning("タグフォルダが選択されませんでした。")

        self._load_yaml_files()
        self._restore_settings()

    def _restore_settings(self):
        geom_str = self.main_window.app_settings.get(TAG_PALETTE_GEOMETRY)
        if geom_str:
            self.restoreGeometry(QByteArray.fromBase64(geom_str.encode('utf-8')))
        
        splitter_str = self.main_window.app_settings.get(TAG_PALETTE_SPLITTER_STATE)
        if splitter_str:
            self.splitter.restoreState(QByteArray.fromBase64(splitter_str.encode('utf-8')))

    def _select_tags_directory(self):
        # ツール起動時にフォルダ選択ダイアログを表示
        selected_dir = QFileDialog.getExistingDirectory(
            self, "タグYAMLフォルダを選択", self.tags_dir
        )
        if selected_dir:
            self.tags_dir = selected_dir
            # app_settingsに保存して次回起動時の初期フォルダとして記憶
            self.main_window.app_settings[TAGS_FOLDER_PATH] = self.tags_dir
            self.main_window._write_app_settings_file()
            return True
        return False

    def _on_change_folder_clicked(self):
        if self._select_tags_directory():
            self.tree_widget.clear()
            self._clear_scroll_content()
            self._load_yaml_files()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left pane (Tree)
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setStyleSheet("""
            QTreeView::item:selected {
                background-color: #4A90E2; 
                color: white;
            }
            QTreeView::item:selected:!active {
                background-color: #90BBEA;
                color: white;
            }
            QTreeView::item:hover {
                background-color: #E5F3FF;
                color: black;
            }
        """)
        self.tree_widget.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.splitter.addWidget(self.tree_widget)

        # Right pane (Scroll area with FlowLayouts inside QVBoxLayout)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content_layout = QVBoxLayout(self.scroll_content)
        self.scroll_content_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_content_layout.setSpacing(10)
        self.scroll_area.setWidget(self.scroll_content)
        self.splitter.addWidget(self.scroll_area)

        # Set stretch factor (1:3 approx)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 4)

        main_layout.addWidget(self.splitter)

        # Control panel (Optional, can just rely on deactivate)
        ctrl_layout = QHBoxLayout()
        
        change_folder_btn = QPushButton("フォルダ変更...")
        change_folder_btn.clicked.connect(self._on_change_folder_clicked)
        ctrl_layout.addWidget(change_folder_btn)
        
        self.status_label = QLabel("タグを選択してウィンドウを離れるとクリップボードにコピーされます")
        ctrl_layout.addWidget(self.status_label)
        
        copy_btn = QPushButton("手動でコピー")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(copy_btn)
        
        main_layout.addLayout(ctrl_layout)

    def _load_yaml_files(self):
        if not os.path.exists(self.tags_dir) or not os.path.isdir(self.tags_dir):
            logger.warning(f"Tag directory not found: {self.tags_dir}")
            root_item = QTreeWidgetItem(["タグフォルダが見つかりません"])
            self.tree_widget.addTopLevelItem(root_item)
            return

        for filename in sorted(os.listdir(self.tags_dir)):
            if filename.endswith(".yml") or filename.endswith(".yaml"):
                file_path = os.path.join(self.tags_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = yaml.load(f, Loader=OrderedLoader)
                        if data:
                            # Create root item for the file
                            file_item = QTreeWidgetItem([filename])
                            file_item.setData(0, Qt.ItemDataRole.UserRole, DataWrapper(data))
                            self.tree_widget.addTopLevelItem(file_item)
                            self._populate_tree(file_item, data)
                except Exception as e:
                    logger.error(f"Failed to load yaml {filename}: {e}", exc_info=True)

    def _populate_tree(self, parent_item, data):
        if isinstance(data, dict):
            for k, v in data.items():
                # 値が dict や list などのコンテナ（さらなる階層）の場合のみツリーを展開する。
                # 文字列など（末端のタグ実体）の場合はツリーには表示せず、親をクリックした時の右ペイン専用のデータとする構造です。
                if isinstance(v, (dict, list)):
                    child_item = QTreeWidgetItem([str(k)])
                    child_item.setData(0, Qt.ItemDataRole.UserRole, DataWrapper(v))
                    parent_item.addChild(child_item)
                    self._populate_tree(child_item, v)

    def _on_tree_selection_changed(self):
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            return
        
        item = selected_items[0]
        wrapped_data = item.data(0, Qt.ItemDataRole.UserRole)
        
        if wrapped_data is None:
            self._clear_scroll_content()
            return
            
        data = wrapped_data.data if isinstance(wrapped_data, DataWrapper) else wrapped_data
        self._populate_scroll_content(data)

    def _clear_scroll_content(self):
        while self.scroll_content_layout.count():
            item = self.scroll_content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                layout = item.layout()
                if layout is not None:
                    # layout自体のみの削除(通常addWidgetなので上記ルートを通る)
                    pass
        self.button_widgets.clear()

    def _extract_categories(self, data, prefix=""):
        categories = []
        if isinstance(data, list):
             categories.append((prefix, data))
        elif isinstance(data, dict):
             # check if terminal dict
             is_terminal = True
             for v in data.values():
                 if isinstance(v, (dict, list)):
                     is_terminal = False
                     break
             if is_terminal:
                 items = [(str(k), str(v)) for k, v in data.items()]
                 categories.append((prefix, items))
             else:
                 for k, v in data.items():
                     new_prefix = f"{prefix} / {k}" if prefix else str(k)
                     categories.extend(self._extract_categories(v, new_prefix))
        return categories

    def _populate_scroll_content(self, data):
        self._clear_scroll_content()

        categories = self._extract_categories(data)
        
        for title, items in categories:
            if title:
                label = QLabel(title)
                # フォントを太字にするなどのスタイルを使用
                label.setStyleSheet("font-weight: bold; padding-top: 8px; color: #AAA;")
                self.scroll_content_layout.addWidget(label)
                
            flow_widget = QWidget()
            flow_layout = FlowLayout(flow_widget, margin=5, spacing=5)
            
            for item in items:
                text = value = ""
                if isinstance(item, tuple):
                    text, value = item
                else:
                    text = value = str(item)
                    
                btn = QPushButton(text)
                btn.setCheckable(True)
                if value in self.selected_tags:
                    btn.setChecked(True)
                    
                btn.toggled.connect(lambda checked, v=value: self._on_button_toggled(checked, v))
                btn.setToolTip(f"{value}")
                
                if value:
                    flow_layout.addWidget(btn)
                    self.button_widgets.append(btn)
                    
            self.scroll_content_layout.addWidget(flow_widget)
            
        self.scroll_content_layout.addStretch()

    def _on_button_toggled(self, checked, value):
        if checked:
            self.selected_tags[value] = None
        else:
            if value in self.selected_tags:
                del self.selected_tags[value]

    def _copy_to_clipboard(self):
        if not self.selected_tags:
            return
        
        # 順番を保つ（Python 3.7+のdictは挿入順序を保持する）
        clipboard = QApplication.clipboard()
        text_to_copy = ", ".join(filter(None, self.selected_tags.keys()))
        clipboard.setText(text_to_copy)
        
        self.toast.show_message(f"クリップボードにコピーしました！\n{text_to_copy}", duration_ms=2500, target_widget=self)
        
        # コピー後、選択をクリアする（好みによるが、今回はクリアする）
        self.selected_tags.clear()
        for btn in self.button_widgets:
            btn.setChecked(False)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                # ウィンドウが非アクティブになった（別のアプリやウィンドウをクリックした）
                if self.selected_tags:
                    self._copy_to_clipboard()

    def _save_window_state(self):
        self.main_window.app_settings[TAG_PALETTE_GEOMETRY] = self.saveGeometry().toBase64().data().decode('utf-8')
        self.main_window.app_settings[TAG_PALETTE_SPLITTER_STATE] = self.splitter.saveState().toBase64().data().decode('utf-8')
        self.main_window._write_app_settings_file()

    def hideEvent(self, event):
        self._save_window_state()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._save_window_state()
        super().closeEvent(event)
