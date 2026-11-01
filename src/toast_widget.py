from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect

class ToastWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        self.label = QLabel("")
        self.label.setStyleSheet("""
            QLabel {
                background-color: rgba(50, 50, 50, 200);
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-family: Arial;
                font-size: 14px;
            }
        """)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(500)
        self.animation.finished.connect(self._on_animation_finished)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._start_fade_out)
        
        self.is_fading_out = False

    def show_message(self, text, duration_ms=2000, target_widget=None):
        self.label.setText(text)
        self.adjustSize()

        if target_widget:
            # target_widgetの中央に配置
            parent_rect = target_widget.geometry()
            global_pos = target_widget.mapToGlobal(parent_rect.topLeft())
            x = global_pos.x() + (target_widget.width() - self.width()) // 2
            y = global_pos.y() + (target_widget.height() - self.height()) // 2
            # 画面端にはみ出さないよう調整することは省略(基本的にアプリの中心に出す)
            self.move(x, y)

        self.is_fading_out = False
        self.setWindowOpacity(1.0)
        self.show()
        self.timer.start(duration_ms)

    def _start_fade_out(self):
        self.is_fading_out = True
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.start()

    def _on_animation_finished(self):
        if self.is_fading_out:
            self.hide()
