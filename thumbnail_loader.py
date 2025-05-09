from PyQt6.QtCore import QThread, pyqtSignal
from PIL import Image
try:
    from PIL import ImageQt # Pillow 9.0.0+
except ImportError:
    ImageQt = None # Fallback for older Pillow if necessary, though requirements specify 11.1.0

class ThumbnailLoaderThread(QThread):
    thumbnailLoaded = pyqtSignal(str, object) # file_path, q_image (QImage)
    progressUpdated = pyqtSignal(int, int) # processed_count, total_count
    finished = pyqtSignal()

    def __init__(self, file_paths, target_size):
        super().__init__()
        self.file_paths = file_paths
        self.target_size = target_size
        self._is_running = True

    def run(self):
        if ImageQt is None: # Ensure ImageQt is available in the thread
            print("ImageQt module not found in thread. Cannot generate thumbnails.")
            self.finished.emit()
            return

        total_files = len(self.file_paths)
        processed_count = 0
        for file_path in self.file_paths:
            if not self._is_running:
                break
            try:
                processed_count += 1
                img = Image.open(file_path)
                img.thumbnail((self.target_size, self.target_size))

                if img.mode == "RGBA":
                    q_image = ImageQt.ImageQt(img)
                elif img.mode == "RGB":
                    img = img.convert("RGBA")
                    q_image = ImageQt.ImageQt(img)
                else:
                    img = img.convert("RGBA")
                    q_image = ImageQt.ImageQt(img)
                
                self.thumbnailLoaded.emit(file_path, q_image) 
                self.progressUpdated.emit(processed_count, total_files)
            except Exception as e:
                print(f"サムネイル生成エラー (スレッド内) ({file_path}): {e}")
        self.finished.emit()

    def stop(self):
        self._is_running = False
