import sys
import json
import random
from pathlib import Path
from PyQt6.QtCore import Qt, QSettings, QElapsedTimer, QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout
from PyQt6.QtWidgets import QLabel, QPushButton, QMessageBox, QSizePolicy, QStackedWidget, QComboBox
from PyQt6.QtGui import QFont, QPixmap

MAX_ERRORS = 6
LETTERS = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
CATEGORIES_FILE = Path(__file__).parent / "categories.json"
IMAGES_DIR = Path(__file__).parent / "images"


def load_categories(path=CATEGORIES_FILE):
    with open(path, encoding="utf8") as f:
        return json.load(f)


def format_time(seconds):
    if seconds is None:
        return "-"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


class StatsManager:
    def __init__(self, organization="MyCompany", app="Hangman"):
        self.settings = QSettings(organization, app)

    def get(self):
        try:
            wins = int(self.settings.value(f"GlobalStats/wins", 0))
            losses = int(self.settings.value(f"GlobalStats/losses", 0))
            raw = self.settings.value(f"GlobalStats/best_time", None)
            best_time = float(raw) if raw is not None else None
            return wins, losses, best_time
        except Exception:
            return 0, 0, None

    def add_win(self):
        wins, _, _ = self.get()
        self.settings.setValue(f"GlobalStats/wins", wins + 1)

    def add_loss(self):
        _, losses, _ = self.get()
        self.settings.setValue(f"GlobalStats/losses", losses + 1)

    def try_update_best_time(self, seconds):
        _, _, best = self.get()
        if best is None or seconds < best:
            self.settings.setValue(f"GlobalStats/best_time", float(seconds))
            return True
        return False

    def reset_all(self):
        self.settings.remove("GlobalStats")


class CategoryScreen(QWidget):
    def __init__(self, on_start, stats, categories_data):
        super().__init__()
        self.on_start = on_start
        self.stats = stats
        self.categories_dict = categories_data
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        self.title = QLabel("Виселица")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title, stretch=1)

        self.subtitle = QLabel("Категории:")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle)

        self.combo_box = QComboBox()
        self.combo_box.addItems(self.categories_dict.keys())
        self.combo_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_box.setMinimumHeight(40)
        layout.addWidget(self.combo_box, stretch=0)

        self.start_btn = QPushButton("Начать игру")
        self.start_btn.setMinimumHeight(50)
        self.start_btn.clicked.connect(self._on_start_clicked)
        layout.addWidget(self.start_btn, stretch=0)

        self.total_label = QLabel()
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_label.setStyleSheet(
            "background-color: #2d3b4f; color: #e6edf3; border-radius: 8px; padding: 10px;")
        layout.addWidget(self.total_label, stretch=0)

        self.reset_btn = QPushButton("Сбросить всё")
        self.reset_btn.clicked.connect(self._confirm_reset)
        layout.addWidget(self.reset_btn, stretch=0)
        layout.addStretch(1)
        self.refresh()

    def _on_start_clicked(self):
        selecled_category = self.combo_box.currentText()
        if selecled_category:
            self.on_start(selecled_category)

    def refresh(self):
        wins, losses, best = self.stats.get()
        self.total_label.setText(
            f"Всего: {wins + losses}\n"
            f"Побед: {wins} | Проигрыши: {losses}\n"
            f"Рекорд: {format_time(best)}"
        )

    def _confirm_reset(self):
        if QMessageBox.question(
                self, "Сброс", "Удалить всю статистику?") == QMessageBox.StandardButton.Yes:
            self.stats.reset_all()
            self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.height()
        self.title.setFont(
            QFont("Arial", max(20, int(h * 0.08)), QFont.Weight.Bold))
        self.subtitle.setFont(QFont("Arial", max(12, int(h * 0.04))))
        self.combo_box.setFont(QFont("Arial", max(10, int(h * 0.03))))
        self.start_btn.setFont(
            QFont("Arial", max(12, int(h * 0.035)), QFont.Weight.Bold))
        self.total_label.setFont(QFont("Arial", max(10, int(h * 0.03))))
        self.reset_btn.setFont(QFont("Arial", max(9, int(h * 0.025))))


class GameScreen(QWidget):
    def __init__(self, on_back, stats, categories_data):
        super().__init__()
        self.on_back = on_back
        self.stats = stats
        self.categories_dict = categories_data
        self.current_category = None
        self.secret_word = ""
        self.guessed_letters = set()
        self.wrong_attempts = 0
        self.buttons = {}
        self.timer = QElapsedTimer()
        self.is_round_active = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.back_btn = QPushButton("Меню")
        self.back_btn.clicked.connect(self._exit_to_menu)
        top.addWidget(self.back_btn, stretch=1)

        self.category_label = QLabel()
        self.category_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self.category_label, stretch=4)
        top.addStretch(1)
        layout.addLayout(top)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setMinimumHeight(150)
        layout.addWidget(self.image_label, stretch=3)

        self.word_label = QLabel()
        self.word_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.word_label, stretch=2)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label, stretch=1)

        self.time_label = QLabel("0:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.time_label, stretch=0)

        kb_widget = QWidget()
        self.grid = QGridLayout(kb_widget)
        self.grid.setSpacing(4)
        self._build_keyboard()
        layout.addWidget(kb_widget, stretch=4)
        bottom_layout = QVBoxLayout()
        layout.addLayout(bottom_layout)
        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.hide()
        bottom_layout.addWidget(self.result_label)

        self.new_game_btn = QPushButton("Новая игра")
        self.new_game_btn.clicked.connect(self.start_new_round)
        bottom_layout.addWidget(self.new_game_btn)

        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(250)
        self.ui_timer.timeout.connect(self._tick)
        self.ui_timer.start()

    def _exit_to_menu(self):
        self.is_round_active = False
        self.timer.invalidate()
        self.on_back()

    def _build_keyboard(self):
        cols = 11
        for i, letter in enumerate(LETTERS):
            row, col = divmod(i, cols)
            btn = QPushButton(letter)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding,
                              QSizePolicy.Policy.Expanding)
            btn.setMaximumSize(28, 28)
            btn.clicked.connect(lambda _, l=letter: self.guess_letter(l))
            self.grid.addWidget(btn, row, col)
            self.buttons[letter] = btn
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        rows = (len(LETTERS) + cols - 1) // cols
        for r in range(rows):
            self.grid.setRowStretch(r, 1)

    def _update_image(self):
        img_path = IMAGES_DIR / f"{self.wrong_attempts}.png"
        if img_path.exists():
            pixmap = QPixmap(str(img_path))
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)

    def start_category(self, category_name):
        self.current_category = category_name
        self.category_label.setText(f"Категория: {category_name}")
        self.start_new_round()

    def start_new_round(self):
        if not self.current_category:
            return
        words = self.categories_dict[self.current_category]
        self.secret_word = random.choice(words).upper()
        self.guessed_letters.clear()
        self.wrong_attempts = 0
        self.is_round_active = True
        self.result_label.hide()
        self.result_label.setText("")
        self.new_game_btn.setText("Новая игра")
        for btn in self.buttons.values():
            btn.setEnabled(True)
        self._update_image()
        self.timer.start()
        self.update_display()

    def update_display(self):
        display = " ".join(
            ch if ch in self.guessed_letters else "_" for ch in self.secret_word)
        self.word_label.setText(display)
        self.status_label.setText(
            f"Осталось попыток: {MAX_ERRORS - self.wrong_attempts}")

    def _tick(self):
        if self.timer.isValid() and self.is_round_active:
            self.time_label.setText(format_time(self.timer.elapsed() / 1000.0))

    def guess_letter(self, letter):
        if not self.is_round_active:
            return
        btn = self.buttons[letter]
        if not btn.isEnabled():
            return
        btn.setEnabled(False)
        self.guessed_letters.add(letter)
        if letter not in self.secret_word:
            self.wrong_attempts += 1
            self._update_image()
        self.update_display()
        self.check_win_or_lose()

    def _block_keyboard(self, block: bool):
        for btn in self.buttons.values():
            btn.setEnabled(not block)

    def check_win_or_lose(self):
        if not self.is_round_active:
            return
        if all(ch in self.guessed_letters for ch in self.secret_word):
            self.is_round_active = False
            elapsed = self.timer.elapsed() / 1000.0
            self.timer.invalidate()
            self.stats.add_win()
            new_record = self.stats.try_update_best_time(elapsed)
            msg = f"ПОБЕДА! Слово: {self.secret_word} | Время: {format_time(elapsed)}"
            if new_record:
                msg += " | Новый рекорд!"
            self._show_result(msg, "green")
            self.new_game_btn.setText("Играть ещё")

        elif self.wrong_attempts >= MAX_ERRORS:
            self.is_round_active = False
            self.timer.invalidate()
            self.stats.add_loss()
            msg = f"ПОРАЖЕНИЕ. Слово: {self.secret_word}"
            self._show_result(msg, "red")
            self.new_game_btn.setText("Попробовать снова")

    def _show_result(self, text, color):
        self._block_keyboard(True)
        self.result_label.setText(text)
        self.result_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.result_label.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.height()
        self.word_label.setFont(
            QFont("Arial", max(14, int(h * 0.07)), QFont.Weight.Bold))
        self.status_label.setFont(QFont("Arial", max(9, int(h * 0.03))))
        self.time_label.setFont(QFont("Arial", max(9, int(h * 0.03))))
        self.category_label.setFont(QFont("Arial", max(9, int(h * 0.03))))
        self.result_label.setFont(QFont("Arial", max(10, int(h * 0.03))))
        btn_font = QFont("Arial", max(8, int(h * 0.025)))
        for btn in self.buttons.values():
            btn.setFont(btn_font)
        self.new_game_btn.setFont(QFont("Arial", max(9, int(h * 0.025))))
        self.back_btn.setFont(QFont("Arial", max(9, int(h * 0.025))))
        self._update_image()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Виселица")
        self.setMinimumSize(500, 550)
        self.resize(800, 700)
        self.categories_dict = load_categories()
        self.stats = StatsManager()
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.game_screen = GameScreen(
            on_back=self.show_menu,
            stats=self.stats,
            categories_data=self.categories_dict,
        )
        self.category_screen = CategoryScreen(
            on_start=self.start_game,
            stats=self.stats,
            categories_data=self.categories_dict,
        )
        self.stack.addWidget(self.category_screen)
        self.stack.addWidget(self.game_screen)
        self.stack.setCurrentIndex(0)

    def start_game(self, category_name):
        self.game_screen.start_category(category_name)
        self.stack.setCurrentIndex(1)

    def show_menu(self):
        self.category_screen.refresh()
        self.stack.setCurrentIndex(0)

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Выход",
            "Точно хотите закрыть приложение?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
