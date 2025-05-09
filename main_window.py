import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeView, QListView, QSplitter, QFrame, QFileDialog, QSlider
)
from PyQt6.QtGui import QFileSystemModel, QPixmap, QIcon, QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt, QDir, QSize, QTimer, QDirIterator

from thumbnail_loader import ThumbnailLoaderThread # Import from new file

# PillowのImageオブジェクトをQImageに変換するために必要
# PIL.ImageQt が Pillow 9.0.0 以降で推奨される方法
try:
    from PIL import ImageQt
except ImportError:
    print("Pillow (PIL) の ImageQt モジュールが見つかりません。pip install Pillow --upgrade を試してください。")
    ImageQt = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.thumbnail_loader_thread = None
        self.setWindowTitle("ImageManager")
        self.setGeometry(100, 100, 1200, 800)

        self.available_sizes = [96, 128, 200]
        self.current_thumbnail_size = self.available_sizes[1] # Default to 128
        self.current_folder_path = None # To store the currently selected folder path
        self.is_loading_thumbnails = False # Flag to indicate loading state
        self.recursive_search_enabled = True # Default to ON

        # Status bar
        self.statusBar = self.statusBar()

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)

        # Splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel (folder tree and button)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.folder_select_button = QPushButton("フォルダを選択...")
        self.folder_select_button.clicked.connect(self.select_folder)
        left_layout.addWidget(self.folder_select_button)

        self.recursive_toggle_button = QPushButton("サブフォルダ検索: ON")
        self.recursive_toggle_button.setCheckable(True)
        self.recursive_toggle_button.setChecked(self.recursive_search_enabled)
        self.recursive_toggle_button.toggled.connect(self.handle_recursive_search_toggled)
        left_layout.addWidget(self.recursive_toggle_button)

        size_control_layout = QHBoxLayout()
        self.size_label = QLabel(f"サイズ: {self.current_thumbnail_size}px")
        size_control_layout.addWidget(self.size_label)
        
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(0)
        self.size_slider.setMaximum(len(self.available_sizes) - 1)
        self.size_slider.setValue(self.available_sizes.index(self.current_thumbnail_size))
        self.size_slider.setTickInterval(1)
        self.size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.size_slider.valueChanged.connect(self.handle_slider_value_changed)
        self.size_slider.sliderReleased.connect(self.trigger_thumbnail_reload)
        size_control_layout.addWidget(self.size_slider)
        left_layout.addLayout(size_control_layout)

        self.folder_tree_view = QTreeView()
        self.folder_tree_view.setHeaderHidden(True)
        self.file_system_model = QFileSystemModel()
        self.file_system_model.setNameFilters(["*.png", "*.jpg", "*.jpeg", "*.webp"])
        self.file_system_model.setNameFilterDisables(False)
        self.folder_tree_view.setModel(self.file_system_model)
        for i in range(1, self.file_system_model.columnCount()):
            self.folder_tree_view.hideColumn(i)
        left_layout.addWidget(self.folder_tree_view)
        self.folder_tree_view.clicked.connect(self.on_folder_tree_clicked)

        splitter.addWidget(left_panel)

        self.thumbnail_view = QListView()
        self.thumbnail_view.setViewMode(QListView.ViewMode.IconMode)
        self.thumbnail_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.thumbnail_view.setMovement(QListView.Movement.Static)
        self.thumbnail_view.setSpacing(10)
        self.thumbnail_view.setIconSize(QSize(self.current_thumbnail_size, self.current_thumbnail_size))
        self.thumbnail_view.setGridSize(QSize(self.current_thumbnail_size + 10, self.current_thumbnail_size + 10))
        self.thumbnail_view.setUniformItemSizes(True)
        self.thumbnail_view.setLayoutMode(QListView.LayoutMode.Batched)
        self.thumbnail_model = QStandardItemModel(self.thumbnail_view)
        self.thumbnail_view.setModel(self.thumbnail_model)
        splitter.addWidget(self.thumbnail_view)

        splitter.setSizes([300, 900])
        main_layout.addWidget(splitter)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "画像フォルダを選択", "")
        if folder_path:
            print(f"選択されたフォルダ: {folder_path}")
            self.update_folder_tree(folder_path)

    def update_folder_tree(self, folder_path):
        self.current_folder_path = folder_path
        self.file_system_model.setRootPath(folder_path)
        self.folder_tree_view.setRootIndex(self.file_system_model.index(folder_path))
        print(f"フォルダツリーを更新しました: {folder_path}")
        self.load_thumbnails_from_folder(folder_path)

    def on_folder_tree_clicked(self, index):
        path = self.file_system_model.filePath(index)
        if self.file_system_model.isDir(index):
            print(f"フォルダがクリックされました: {path}")
            self.current_folder_path = path
            self.load_thumbnails_from_folder(path)
        else:
            print(f"ファイルがクリックされました: {path}")

    def load_thumbnails_from_folder(self, folder_path):
        if ImageQt is None: # Ensure ImageQt is available before loading
            self.statusBar.showMessage("ImageQtモジュールが見つかりません。処理を中止します。", 5000)
            print("ImageQt module not found. Cannot load thumbnails.")
            return

        print(f"{folder_path} からサムネイルを読み込みます。")
        image_files = []
        try:
            search_flags = QDirIterator.IteratorFlag.Subdirectories if self.recursive_search_enabled else QDirIterator.IteratorFlag.NoIteratorFlags
            iterator = QDirIterator(folder_path,
                                    ["*.png", "*.jpg", "*.jpeg", "*.webp"],
                                    QDir.Filter.Files | QDir.Filter.NoSymLinks,
                                    search_flags)
            while iterator.hasNext():
                image_files.append(iterator.next())
            
            print(f"見つかった画像ファイル (再帰検索{'含む' if self.recursive_search_enabled else '含まない'}): {len(image_files)}個")
            
            self.is_loading_thumbnails = True
            self.size_slider.setEnabled(False) 
            self.folder_tree_view.setEnabled(False)
            self.recursive_toggle_button.setEnabled(False)

            self.thumbnail_model.clear()

            self.thumbnail_view.setIconSize(QSize(self.current_thumbnail_size, self.current_thumbnail_size))
            self.thumbnail_view.setGridSize(QSize(self.current_thumbnail_size + 10, self.current_thumbnail_size + 10))

            placeholder_pixmap = QPixmap(self.current_thumbnail_size, self.current_thumbnail_size)
            placeholder_pixmap.fill(Qt.GlobalColor.transparent)
            placeholder_icon = QIcon(placeholder_pixmap)

            for f_path in image_files:
                item = QStandardItem()
                item.setIcon(placeholder_icon)
                item.setText(QDir().toNativeSeparators(f_path).split(QDir.separator())[-1])
                item.setEditable(False)
                item.setData(f_path, Qt.ItemDataRole.UserRole)
                self.thumbnail_model.appendRow(item)

        except Exception as e:
            print(f"サムネイル読み込み準備中にエラー: {e}")
        
        if self.thumbnail_loader_thread and self.thumbnail_loader_thread.isRunning():
            print("既存のスレッドを停止します...")
            self.thumbnail_loader_thread.stop()
            self.thumbnail_loader_thread.quit()
            if not self.thumbnail_loader_thread.wait(5000):
                print("警告: 既存スレッドの終了待機がタイムアウトしました。")
            else:
                print("既存スレッドが正常に終了しました。")

        self.thumbnail_loader_thread = ThumbnailLoaderThread(image_files, self.current_thumbnail_size)
        self.thumbnail_loader_thread.thumbnailLoaded.connect(self.update_thumbnail_item)
        self.thumbnail_loader_thread.progressUpdated.connect(self.update_progress_bar)
        self.thumbnail_loader_thread.finished.connect(self.on_thumbnail_loading_finished)
        if image_files:
            self.statusBar.showMessage(f"サムネイル読み込み中... 0/{len(image_files)}")
            self.thumbnail_loader_thread.start()
        else:
            self.statusBar.showMessage("フォルダに画像がありません", 5000)
            self.is_loading_thumbnails = False # Reset flag if no files
            self.size_slider.setEnabled(True)
            self.folder_tree_view.setEnabled(True)
            self.recursive_toggle_button.setEnabled(True)


    def handle_slider_value_changed(self, value):
        preview_size = self.available_sizes[value]
        self.size_label.setText(f"サイズ: {preview_size}px")

    def handle_recursive_search_toggled(self, checked):
        self.recursive_search_enabled = checked
        self.recursive_toggle_button.setText(f"サブフォルダ検索: {'ON' if checked else 'OFF'}")
        print(f"再帰検索設定変更: {'ON' if checked else 'OFF'}. 次回フォルダ読み込み時に適用されます。")

    def trigger_thumbnail_reload(self):
        if self.is_loading_thumbnails:
            print("現在サムネイル読み込み中のため、サイズ変更はスキップされました。")
            current_value_index = self.available_sizes.index(self.current_thumbnail_size)
            if self.size_slider.value() != current_value_index:
                self.size_slider.setValue(current_value_index)
                self.size_label.setText(f"サイズ: {self.current_thumbnail_size}px")
            return

        slider_selected_index = self.size_slider.value()
        new_selected_size = self.available_sizes[slider_selected_index]

        if new_selected_size != self.current_thumbnail_size:
            self.current_thumbnail_size = new_selected_size
            if self.current_folder_path:
                print(f"サムネイルサイズ変更適用: {self.current_thumbnail_size}px. 再読み込み開始...")
                self.load_thumbnails_from_folder(self.current_folder_path)
            else:
                print("再読み込みするフォルダが選択されていません。")
        else:
            self.size_label.setText(f"サイズ: {self.current_thumbnail_size}px")
            print("選択されたサイズは現在のサイズと同じため、再読み込みは行いません。")

    def update_progress_bar(self, processed_count, total_files):
        self.statusBar.showMessage(f"サムネイル読み込み中... {processed_count}/{total_files}")

    def update_thumbnail_item(self, file_path, q_image):
        if ImageQt is None: return # Should not happen if checked in load_thumbnails
        pixmap = QPixmap.fromImage(q_image)
        for row in range(self.thumbnail_model.rowCount()):
            item = self.thumbnail_model.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == file_path:
                item.setIcon(QIcon(pixmap))
                break

    def on_thumbnail_loading_finished(self):
        print("サムネイルの非同期読み込みが完了しました。")
        self.statusBar.showMessage("サムネイル読み込み完了", 5000)
        self.is_loading_thumbnails = False
        self.size_slider.setEnabled(True) 
        self.folder_tree_view.setEnabled(True)
        self.recursive_toggle_button.setEnabled(True)
        if self.thumbnail_loader_thread:
            self.thumbnail_loader_thread.deleteLater()
            self.thumbnail_loader_thread = None
