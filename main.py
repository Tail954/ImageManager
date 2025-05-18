import sys
import logging # Add logging import
from PyQt6.QtWidgets import QApplication
from src.main_window import MainWindow # Import MainWindow from the src package

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, # Revert to INFO
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr), # Log to console
            logging.FileHandler("imagemanager.log", mode='w', encoding='utf-8') # Log to file, mode 'w' to overwrite
        ]
    )
    logger = logging.getLogger(__name__)

    # Configure Pillow's logger to be less verbose
    pil_modules_to_quiet = [
        'PIL', 
        'PIL.Image',
        'PIL.PngImagePlugin',
        'PIL.TiffImagePlugin',
        'PIL.JpegImagePlugin',
        'PIL.WebPImagePlugin',
        'PIL.PsdImagePlugin', # Added PsdImagePlugin as an example, can add others
        # Add other specific Pillow plugin loggers if they are still too verbose
    ]
    for module_name in pil_modules_to_quiet:
        pil_module_logger = logging.getLogger(module_name)
        # It's possible getLogger returns a placeholder if the logger hasn't been created by Pillow yet.
        # Setting level on this placeholder should still apply when Pillow creates it.
        pil_module_logger.setLevel(logging.WARNING)

    # Ensure our application's loggers are at DEBUG if needed
    # (already covered by basicConfig if its level is DEBUG)
    # logging.getLogger('src.thumbnail_loader').setLevel(logging.DEBUG)
    # logging.getLogger('src.main_window').setLevel(logging.DEBUG)

    app = QApplication(sys.argv)
    try:
        logger.info("アプリケーションを起動します...")
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"アプリケーションの起動中に致命的なエラーが発生しました: {e}", exc_info=True)
        sys.exit(1)
