"""Графическая часть SteamPACC: оверлей поверх окна Steam.

Модуль отвечает за отображение цен игр в оверлее поверх активного окна.
Стиль оверлея приближен к нативному стилю Steam.

Как это работает:

- каждые полторы секунды программа смотрит, какое окно активно;
- если активна игра из библиотеки Steam, оверлей показывает цены этой
  игры в выбранных валютах (по углу окна игры);
- если активно само окно Steam, показываются цены последней открытой
  игры, а если игр ещё не было — короткая подсказка;
- сеть и чтение библиотеки работают в фоновых потоках: интерфейс не
  замирает;
- оверлей прозрачен для мыши: клики проходят сквозь него.
"""

from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import win_api
from . import diagnostics
from . import __version__ as app_version
from . import autostart
from .config import Settings, apply_changes, load_settings, save_settings
from .diagnostics import (
    log_exception,
    log_message,
    show_error,
)
from .prices import (
    CURRENCY_COUNTRIES,
    CURRENCY_SYMBOLS,
    SUPPORTED_COUNTRIES,
    Price,
    PriceError,
    fetch_price,
    format_price,
)
from .steam_paths import find_steam_root, steam_paths
from .library import InstalledGame, iter_library_games, read_library_folders

try:
    from .steam_integration import SteamIntegrator
    INTEGRATION_AVAILABLE = True
except ImportError:
    INTEGRATION_AVAILABLE = False

try:
    from PySide6.QtCore import QSize, QTimer, Qt, Signal, QObject
    from PySide6.QtGui import (
        QAction, QBrush, QColor, QFont, QFontMetrics, QIcon, QLinearGradient,
        QPainter, QPainterPath, QPen, QPixmap,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QMenu,
        QPushButton,
        QSpinBox,
        QSystemTrayIcon,
        QVBoxLayout,
        QWidget,
    )
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


# Классы окон Steam: сравнение ведётся без учёта регистра.
STEAM_WINDOW_CLASSES = ('STEAMMAINWINDOW', 'STEAMCLIENT', 'VGUIPOPUPWINDOW')

#: Класс окна клиента Steam новой версии. Его используют и игры на SDL,
#: поэтому окно Steam по нему опознаётся дополнительно: по заголовку
#: «Steam» или по процессу steam.exe.
STEAM_SDL_CLASS = 'sdl_app'

# Кэш настроек
CACHE_FILE_NAME = 'prices.json'
CACHE_TTL = 900  # 15 минут
CACHE_MAX_GAMES = 256  # столько игр хранится в кэше цен

# Позиционирование панели
PANEL_MARGIN = 24
UPDATE_INTERVAL_MS = 1500
FETCH_RETRY_SECONDS = 120  # повтор запроса после неудачи не раньше, чем через 2 минуты

#: Якоря положения панели оверлея.
ANCHORS = ('top_left', 'top_right', 'bottom_left', 'bottom_right')

# Steam color palette
STEAM_DARK_BG = (27, 39, 56)    # #1b2838
STEAM_DARKER_BG = (20, 30, 45)  # #141e2d
STEAM_ACCENT = (102, 192, 244)  # #66c0f4
STEAM_TEXT = (200, 200, 200)    # Light gray
STEAM_TEXT_DIM = (120, 120, 120) # Dim text
STEAM_BORDER = (50, 60, 75)     # Border color

# Single instance mutex name
SINGLE_INSTANCE_MUTEX = 'SteamPACC.SingleInstance'

#: Системные процессы, которые не считаются играми.
NON_GAME_PROCESSES = frozenset({
    'steam.exe', 'steamwebhelper.exe', 'steampacc.exe', 'python.exe',
    'pythonw.exe', 'explorer.exe', 'applicationframehost.exe',
    'searchhost.exe', 'shellexperiencehost.exe', 'textinputhost.exe',
})


# =============================================================================
# Utility Functions
# =============================================================================

def overlay_position(
    steam_rect: tuple[int, int, int, int],
    panel_size: tuple[int, int],
    anchor: str = 'bottom_right',
    margin: int = PANEL_MARGIN,
) -> tuple[int, int]:
    '''Вычисляет положение панели оверлея относительно окна Steam.'''
    if anchor not in ANCHORS:
        raise ValueError('Неизвестный якорь панели: ' + str(anchor))
    left, top, right, bottom = steam_rect
    width, height = panel_size
    if right < left or bottom < top:
        raise ValueError('Некорректный прямоугольник окна Steam')
    if anchor == 'top_left':
        x, y = left + margin, top + margin
    elif anchor == 'top_right':
        x, y = right - width - margin, top + margin
    elif anchor == 'bottom_left':
        x, y = left + margin, bottom - height - margin
    else:
        x, y = right - width - margin, bottom - height - margin
    return int(x), int(y)


def panel_size(lines: list[str], scale: int = 100) -> tuple[int, int]:
    '''Оценивает размер панели по строкам текста и масштабу в процентах.'''
    if scale <= 0:
        raise ValueError('Масштаб должен быть положительным')
    longest = max((len(line) for line in lines), default=0)
    char_width = max(8 * scale // 100, 1)
    line_height = max(20 * scale // 100, 1)
    width = max(longest * char_width + 32 * scale // 100, 160 * scale // 100)
    height = max(len(lines), 1) * line_height + 20 * scale // 100
    return width, height


def format_price_lines(prices: dict[str, Price], game_name: str | None = None) -> list[str]:
    '''Собирает строки панели: название игры и цены по валютам.'''
    lines: list[str] = []
    if game_name:
        if len(game_name) > 40:
            game_name = game_name[:37] + '...'
        lines.append(game_name)
    for code in sorted(prices):
        price = prices[code]
        if price is None:
            continue
        label = price.currency or code.upper()
        lines.append(label + ': ' + format_price(price))
    if not lines:
        lines.append('Нет данных о ценах')
    return lines


def cache_path() -> Path:
    '''Возвращает путь к файлу кэша цен в каталоге данных приложения.'''
    base = os.environ.get('APPDATA') or os.environ.get('XDG_CONFIG_HOME')
    if base:
        return Path(base) / 'SteamPACC' / CACHE_FILE_NAME
    return Path.home() / '.config' / 'SteamPACC' / CACHE_FILE_NAME


def load_cache(path: Path) -> dict[str, Any]:
    '''Читает кэш цен; повреждённый или старый файл не ломает программу.

    Кэш хранится по играм: {appid: {валюта: {time, price}}}. Записи
    старого формата (по валютам, одна игра на файл) переносятся в новый.
    '''
    try:
        if not path.exists():
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        if str(key).isdigit():
            result[str(key)] = value
            continue
        # Старый формат: ключ — валюта, внутри одна запись с appid.
        appid = value.get('appid')
        record = value.get('price')
        if isinstance(appid, int) and isinstance(record, dict):
            bucket = result.setdefault(str(appid), {})
            if isinstance(bucket, dict) and key not in bucket:
                bucket[key] = {'time': value.get('time'), 'price': record}
    return result


def save_cache(path: Path, data: dict[str, Any]) -> bool:
    '''Сохраняет кэш цен в файл; ошибка записи не прерывает работу.'''
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        return True
    except OSError:
        return False


def cached_price(cache: dict[str, Any], appid: int, currency: str, ttl: int = CACHE_TTL) -> Price | None:
    '''Возвращает цену из кэша, если запись свежая и относится к той же игре.'''
    bucket = cache.get(str(appid))
    if not isinstance(bucket, dict):
        return None
    entry = bucket.get(currency)
    if not isinstance(entry, dict):
        return None

    stamp = entry.get('time')
    if not isinstance(stamp, int) or int(time.time()) - stamp > ttl:
        return None

    data = entry.get('price')
    if not isinstance(data, dict):
        return None

    try:
        return Price(
            appid=int(data.get('appid', appid)),
            country=currency.lower(),
            currency=str(data.get('currency', '')),
            final=data.get('final') if isinstance(data.get('final'), int) else None,
            initial=data.get('initial') if isinstance(data.get('initial'), int) else None,
            discount_percent=int(data.get('discount_percent', 0)),
            title=data.get('title') if isinstance(data.get('title'), str) else None,
            is_free=bool(data.get('is_free', False)),
        )
    except (TypeError, ValueError):
        return None


def store_price(cache: dict[str, Any], appid: int, currency: str, price: Price) -> None:
    '''Кладёт цену в кэш; размер кэша ограничен, старые игры вытесняются.'''
    bucket = cache.setdefault(str(appid), {})
    if not isinstance(bucket, dict):
        bucket = {}
        cache[str(appid)] = bucket
    bucket[currency] = {
        'time': int(time.time()),
        'price': price_to_dict(price),
    }
    if len(cache) > CACHE_MAX_GAMES:
        oldest = min(
            (key for key in cache if str(key).isdigit()),
            key=lambda key: max(
                (item.get('time', 0) for item in cache[key].values()
                 if isinstance(item, dict)),
                default=0,
            ),
        )
        cache.pop(oldest, None)


def price_to_dict(price: Price) -> dict[str, Any]:
    '''Convert Price to dictionary for caching.'''
    return {
        'appid': price.appid,
        'currency': price.currency,
        'final': price.final,
        'initial': price.initial,
        'discount_percent': price.discount_percent,
        'title': price.title,
        'is_free': price.is_free,
    }


def watch_currencies(settings: Settings) -> list[str]:
    '''Get list of currencies to display.'''
    codes = [code.upper() for code in settings.currencies if code]
    return codes or ['RUB', 'USD', 'EUR']


def build_exe_map(games: Any) -> dict[str, int]:
    '''Сопоставляет имена исполняемых файлов игр с их appid.

    Обходятся каталоги установки без вложенности: большинство игр
    держит запускаемый файл прямо в папке игры. Имена приводятся к
    нижнему регистру, первая встреченная игра закрепляет имя за собой.
    '''
    result: dict[str, int] = {}
    for game in games:
        folder = Path(game.install_dir)
        if not folder.is_dir():
            continue
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            name = entry.name.lower()
            if not name.endswith('.exe'):
                continue
            try:
                if not entry.is_file():
                    continue
            except OSError:
                continue
            result.setdefault(name, game.appid)
    return result


def game_by_title(title: str, names: dict[str, int], min_length: int = 4) -> int | None:
    '''Ищет игру по подстроке в заголовке окна.

    Совпадает самое длинное имя игры, целиком вошедшее в заголовок.
    Короткие имена пропускаются, чтобы «GOA» или « preparation» не
    давали ложных срабатываний.
    '''
    if not title or not names:
        return None
    needle = title.lower()
    best: tuple[int, int] | None = None
    for name, appid in names.items():
        if len(name) >= min_length and name in needle:
            if best is None or len(name) > best[0]:
                best = (len(name), appid)
    return best[1] if best else None


# =============================================================================
# Window Detection
# =============================================================================

def is_steam_window(class_name: str, title: str, hwnd: int = 0) -> bool:
    '''True, если окно принадлежит клиенту Steam.

    Главный класс новой версии клиента — SDL_app: с тем же классом
    выходят и игры на SDL, поэтому окно Steam опознаётся по заголовку
    «Steam» или по процессу steam.exe. Остальные классы сверяются со
    списком STEAM_WINDOW_CLASSES без учёта регистра.
    '''
    cls = (class_name or '').strip().lower()
    if cls == STEAM_SDL_CLASS:
        if (title or '').strip().lower() == 'steam':
            return True
        if not hwnd:
            return False
        try:
            image = win_api.window_process_image(hwnd)
        except win_api.WinApiError:
            return False
        return image.lower().endswith(chr(92) + 'steam.exe')
    return cls in {name.lower() for name in STEAM_WINDOW_CLASSES}


def find_steam_window() -> tuple[int, int, int, int] | None:
    '''Ищет видимое окно Steam и возвращает его прямоугольник.

    Окна перебираются целиком: у Steam несколько окон одного класса
    (служебные окна steamwebhelper), и FindWindowW находит первое
    попавшееся, часто невидимое.
    '''
    try:
        windows = win_api.enum_windows()
    except win_api.WinApiError:
        return None
    for hwnd in windows:
        try:
            if not win_api.is_window_visible(hwnd):
                continue
            class_name = win_api.window_class(hwnd)
            title = win_api.window_title(hwnd)
        except win_api.WinApiError:
            continue
        if not is_steam_window(class_name, title, hwnd):
            continue
        rect = win_api.window_rect(hwnd)
        if rect is not None and rect[2] > rect[0] and rect[3] > rect[1]:
            return rect
    return None


def foreground_window() -> tuple[int, tuple[int, int, int, int], str, str] | None:
    """Get information about the foreground window."""
    hwnd = win_api.foreground_window()
    if not hwnd:
        return None
    try:
        rect = win_api.window_rect(hwnd)
        title = win_api.window_title(hwnd)
        class_name = win_api.window_class(hwnd)
    except win_api.WinApiError:
        return None
    if rect is None:
        return None
    return hwnd, rect, title, class_name


def is_minimized(hwnd: int) -> bool:
    """Check if window is minimized."""
    try:
        return win_api.is_minimized(hwnd)
    except win_api.WinApiError:
        return False


# =============================================================================
# Qt Widgets
# =============================================================================

if QT_AVAILABLE:
    class NativeOverlayWindow(QWidget):
        """Overlay window with Steam-like styling."""

        def __init__(self, settings: Settings):
            super().__init__(None)
            self._settings = settings
            self._lines: list[str] = []
            self._game_name: str | None = None
            self._click_through_done = False

            # Window flags for overlay
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.WindowTransparentForInput
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

            self._apply_fonts()
            self.setWindowOpacity(float(settings.overlay_opacity))

            self._corner_radius = 8

            self._colors = {
                'dark_bg': QColor(*STEAM_DARK_BG),
                'darker_bg': QColor(*STEAM_DARKER_BG),
                'accent': QColor(*STEAM_ACCENT),
                'text': QColor(*STEAM_TEXT),
                'text_dim': QColor(*STEAM_TEXT_DIM),
                'border': QColor(*STEAM_BORDER),
            }

        def _apply_fonts(self) -> None:
            '''Строит шрифты панели с учётом масштаба из настроек.'''
            scale = max(50, min(200, int(self._settings.overlay_scale))) / 100.0
            self._font = QFont('Segoe UI', max(8, round(10 * scale)))
            self._bold_font = QFont('Segoe UI', max(9, round(11 * scale)), QFont.Weight.Bold)

        def apply_settings(self, settings: Settings) -> None:
            '''Применяет новые настройки прозрачности и масштаба.'''
            self._settings = settings
            self._apply_fonts()
            self.setWindowOpacity(float(settings.overlay_opacity))
            self.update()

        def set_lines(self, lines: list[str], game_name: str | None = None) -> None:
            """Set lines to display."""
            self._lines = list(lines)
            self._game_name = game_name
            self.update()

        def show_overlay(self) -> None:
            '''Показывает оверлей, не перехватывая фокус и клики.'''
            if not self.isVisible():
                self.show()
                if not self._click_through_done:
                    try:
                        win_api.make_click_through(int(self.winId()))
                        self._click_through_done = True
                    except win_api.WinApiError:
                        pass
            self.raise_()

        def sizeHint(self) -> QSize:
            """Calculate size based on content."""
            if not self._lines:
                return QSize(200, 80)

            fm = QFontMetrics(self._font)
            max_width = max(fm.horizontalAdvance(line) for line in self._lines)

            if self._game_name:
                fm_bold = QFontMetrics(self._bold_font)
                game_width = fm_bold.horizontalAdvance(self._game_name)
                max_width = max(max_width, game_width)

            width = max(max_width + 32, 200)
            height = 14 + fm.height() * len(self._lines) + 14
            if self._game_name:
                height += QFontMetrics(self._bold_font).height() + 12
            return QSize(width, height)

        def paintEvent(self, event: Any) -> None:
            """Paint overlay with Steam-like styling."""
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Draw background with rounded corners
            rect = self.rect()
            path = QPainterPath()
            path.addRoundedRect(rect, self._corner_radius, self._corner_radius)

            # Gradient background
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gradient.setColorAt(0, self._colors['dark_bg'])
            gradient.setColorAt(1, self._colors['darker_bg'])

            painter.fillPath(path, QBrush(gradient))

            # Draw border
            painter.setPen(QPen(self._colors['border'], 1))
            painter.drawPath(path)

            x = 16
            fm = QFontMetrics(self._font)

            # Draw game name (bold) and separator
            if self._game_name:
                bold_fm = QFontMetrics(self._bold_font)
                painter.setFont(self._bold_font)
                painter.setPen(QPen(self._colors['accent']))
                y = 14 + bold_fm.ascent()
                painter.drawText(x, y, self._game_name)
                y += bold_fm.descent() + 6
                painter.setPen(QPen(self._colors['border'], 1))
                painter.drawLine(x, y, self.width() - 16, y)
                y += 8
            else:
                y = 14

            # Draw price lines
            painter.setFont(self._font)
            painter.setPen(QPen(self._colors['text']))

            for line in self._lines:
                painter.drawText(x, y + fm.ascent(), line)
                y += fm.height()

            painter.end()

    class SettingsDialog(QDialog):
        """Settings dialog."""

        def __init__(self, settings: Settings, parent: QWidget | None = None):
            super().__init__(parent)
            self._settings = settings
            self.setWindowTitle('SteamPACC — Настройки')
            self.setMinimumWidth(480)

            layout = QVBoxLayout()

            # ===== Currencies =====
            currency_group = QGroupBox('Валюты для показа')
            currency_grid = QGridLayout()
            current = {code.upper() for code in settings.currencies}
            self.currency_checks: dict[str, QCheckBox] = {}
            for index, code in enumerate(sorted(CURRENCY_SYMBOLS)):
                symbol = CURRENCY_SYMBOLS[code]
                box = QCheckBox(code + '  ' + symbol)
                box.setChecked(code in current)
                self.currency_checks[code] = box
                currency_grid.addWidget(box, index // 4, index % 4)
            currency_group.setLayout(currency_grid)
            layout.addWidget(currency_group)

            # ===== Appearance =====
            general_group = QGroupBox('Отображение')
            general_form = QFormLayout()

            self.opacity_spin = QDoubleSpinBox()
            self.opacity_spin.setRange(0.3, 1.0)
            self.opacity_spin.setSingleStep(0.1)
            self.opacity_spin.setValue(settings.overlay_opacity)
            general_form.addRow('Прозрачность:', self.opacity_spin)

            self.scale_spin = QSpinBox()
            self.scale_spin.setRange(75, 150)
            self.scale_spin.setValue(settings.overlay_scale)
            general_form.addRow('Масштаб, %:', self.scale_spin)

            general_group.setLayout(general_form)
            layout.addWidget(general_group)

            # ===== Behavior =====
            behavior_group = QGroupBox('Поведение')
            behavior_layout = QVBoxLayout()

            self.integration_check = QCheckBox(
                'Цены прямо в магазине Steam (нужен перезапуск Steam с ценами)')
            self.integration_check.setChecked(settings.integration_enabled)
            behavior_layout.addWidget(self.integration_check)

            self.autostart_check = QCheckBox('Запускать вместе с Windows')
            self.autostart_check.setChecked(settings.launch_with_steam)
            behavior_layout.addWidget(self.autostart_check)

            behavior_group.setLayout(behavior_layout)
            layout.addWidget(behavior_group)

            # ===== Buttons =====
            button_layout = QHBoxLayout()
            button_layout.addStretch()

            save_btn = QPushButton('Сохранить')
            save_btn.clicked.connect(self.accept)
            button_layout.addWidget(save_btn)

            cancel_btn = QPushButton('Отмена')
            cancel_btn.clicked.connect(self.reject)
            button_layout.addWidget(cancel_btn)

            layout.addLayout(button_layout)
            self.setLayout(layout)

        def get_settings(self) -> dict:
            """Get updated settings."""
            currencies = [
                code for code, box in self.currency_checks.items() if box.isChecked()
            ]
            return {
                'currencies': currencies or ['RUB', 'USD', 'EUR'],
                'overlay_opacity': self.opacity_spin.value(),
                'overlay_scale': self.scale_spin.value(),
                'launch_with_steam': self.autostart_check.isChecked(),
                'integration_enabled': self.integration_check.isChecked(),
            }


# =============================================================================
# Main Application Controller
# =============================================================================

if QT_AVAILABLE:
    class AppController(QObject):
        """Main application controller: оверлей, трей, фоновая сеть."""

        _prices_ready = Signal(int, dict)

        def __init__(self, application: QApplication):
            super().__init__()
            self._app = application
            self._settings = load_settings()
            self._cache_file = cache_path()
            self._cache: dict[str, Any] = load_cache(self._cache_file)
            self._cache_lock = threading.Lock()

            # Библиотека игр: appid -> имя, имя -> appid, exe -> appid.
            self._names: dict[int, str] = {}
            self._games: dict[str, int] = {}
            self._exe_map: dict[str, int] = {}

            # Состояние показа.
            self._shown_appid: int | None = None
            self._last_appid: int | None = None
            self._last_name: str | None = None

            # Фоновые потоки.
            self._stop_event = threading.Event()
            self._fetch_queue: queue.Queue[tuple[int, tuple[str, ...]]] = queue.Queue()
            self._in_flight: set[int] = set()
            self._in_flight_lock = threading.Lock()
            self._fail_times: dict[int, float] = {}

            self._window = NativeOverlayWindow(self._settings)

            # Интеграция с магазином Steam: цены прямо в карточках покупки.
            self._integrator = None
            if INTEGRATION_AVAILABLE:
                try:
                    self._integrator = SteamIntegrator(self)
                    self._integrator.status_changed.connect(log_message)
                    self._integrator.page_currencies_received.connect(self._on_page_currencies)
                    self._integrator.set_enabled(self._settings.integration_enabled)
                    self._integrator.set_currencies(watch_currencies(self._settings))
                except Exception as error:
                    log_exception('Интеграция с магазином не запустилась: ' + str(error))

            self._tray_icon = None
            self._setup_tray()

            self._prices_ready.connect(self._on_prices_ready)

            self._worker = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker.start()
            self._library_thread = threading.Thread(target=self._load_games, daemon=True)
            self._library_thread.start()

            self._timer = QTimer()
            self._timer.timeout.connect(self._update_overlay)
            self._timer.start(UPDATE_INTERVAL_MS)

        # ----- Фоновые потоки -----

        def _worker_loop(self) -> None:
            '''Фоновый цикл: берёт игры из очереди и качает цены без блокировки GUI.'''
            while not self._stop_event.is_set():
                try:
                    appid, currencies = self._fetch_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                result: dict[str, Price] = {}
                for code in currencies:
                    if self._stop_event.is_set():
                        break
                    with self._cache_lock:
                        price = cached_price(self._cache, appid, code)
                    if price is None:
                        country = CURRENCY_COUNTRIES.get(code, code.lower())
                        try:
                            price = fetch_price(appid, country)
                        except PriceError as error:
                            log_message('Цена ' + code + ' для ' + str(appid)
                                        + ' не получена: ' + str(error))
                            continue
                        with self._cache_lock:
                            store_price(self._cache, appid, code, price)
                            save_cache(self._cache_file, self._cache)
                    result[code] = price
                with self._in_flight_lock:
                    self._in_flight.discard(appid)
                if result:
                    self._prices_ready.emit(appid, result)

        def _load_games(self) -> None:
            '''Читает библиотеку Steam в фоновом потоке.'''
            try:
                root = find_steam_root()
                if root is None:
                    log_message('Каталог Steam не найден: определение игр по библиотеке отключено')
                    return

                roots: list[Path] = [root]
                try:
                    folders_file = steam_paths(root).libraryfolders_vdf
                    if folders_file.is_file():
                        text = folders_file.read_text(encoding='utf-8', errors='ignore')
                        roots.extend(read_library_folders(text))
                except OSError:
                    pass

                unique: list[Path] = []
                for item in roots:
                    if item not in unique:
                        unique.append(item)

                games = list(iter_library_games(unique))
                exe_map = build_exe_map(games)
                names: dict[int, str] = {}
                by_name: dict[str, int] = {}
                for game in games:
                    names[game.appid] = game.name
                    by_name[game.name.lower()] = game.appid
                self._names = names
                self._games = by_name
                self._exe_map = exe_map
                log_message('Загружено игр из библиотеки Steam: ' + str(len(names))
                            + ', исполняемых файлов: ' + str(len(exe_map)))
            except Exception as error:
                log_exception('Ошибка загрузки библиотеки Steam: ' + str(error))

        # ----- Определение игры -----

        def _name_for(self, appid: int) -> str | None:
            return self._names.get(appid)

        def _detect_game(self, title: str, hwnd: int) -> tuple[int | None, str | None]:
            '''Определяет игру по процессу активного окна, затем по заголовку.'''
            try:
                image = win_api.window_process_image(hwnd)
            except win_api.WinApiError:
                image = ''
            if image:
                exe = image.replace('/', chr(92)).rsplit(chr(92), 1)[-1].lower()
                if exe and exe not in NON_GAME_PROCESSES:
                    appid = self._exe_map.get(exe)
                    if appid:
                        return appid, self._name_for(appid)

            if title:
                match = re.search(r'App\s+(\d+)', title)
                if match:
                    appid = int(match.group(1))
                    return appid, self._name_for(appid)
                appid = game_by_title(title, self._games)
                if appid:
                    return appid, self._name_for(appid)
            return None, None

        # ----- Цены -----

        def _prices_from_cache(self, appid: int) -> dict[str, Price]:
            '''Читает цены из кэша, не трогая сеть.'''
            result: dict[str, Price] = {}
            with self._cache_lock:
                for code in watch_currencies(self._settings):
                    price = cached_price(self._cache, appid, code)
                    if price is not None:
                        result[code] = price
            return result

        def _request_prices(self, appid: int) -> None:
            '''Ставит игру в очередь фоновой загрузки, если это нужно.'''
            with self._in_flight_lock:
                if appid in self._in_flight:
                    return
                failed_at = self._fail_times.get(appid, 0)
                if time.time() - failed_at < FETCH_RETRY_SECONDS:
                    return
                missing = [
                    code for code in watch_currencies(self._settings)
                    if code not in self._prices_from_cache(appid)
                ]
                if not missing:
                    return
                self._in_flight.add(appid)
            self._fetch_queue.put((appid, tuple(missing)))

        def _on_prices_ready(self, appid: int, prices: dict[str, Price]) -> None:
            '''Приём цен из фонового потока и обновление панели.'''
            if not prices:
                self._fail_times[appid] = time.time()
                return
            self._fail_times.pop(appid, None)
            if appid == self._shown_appid:
                lines = format_price_lines(prices)
                self._window.set_lines(lines, self._last_name)

        # ----- Показ оверлея -----

        def _hide_overlay(self) -> None:
            if self._window.isVisible():
                self._window.hide()
            self._shown_appid = None

        def _update_overlay(self, force_show: bool = False) -> None:
            """Update overlay with current game prices."""
            try:
                info = foreground_window()
                if info is None:
                    if not force_show:
                        self._hide_overlay()
                        return
                    info = find_steam_window()
                    if info is None:
                        return
                    rect = info
                    hwnd, title, class_name = 0, '', ''
                else:
                    hwnd, rect, title, class_name = info

                if hwnd and is_minimized(hwnd):
                    if not force_show:
                        self._hide_overlay()
                        return

                is_steam = is_steam_window(class_name, title, hwnd)

                if is_steam:
                    # Steam сам в фокусе: цены уже внедрены в страницы
                    # магазина, оверлей только мешает. Показываем что-то
                    # только по явной просьбе (значок в трее).
                    if not force_show:
                        self._hide_overlay()
                        return
                    if self._last_appid is not None:
                        appid = self._last_appid
                        name = self._last_name
                        prices = self._prices_from_cache(appid)
                    else:
                        lines = [
                            'SteamPACC работает',
                            'Цены видны прямо в магазине;',
                            'этот оверлей — для окон игр',
                        ]
                        self._window.set_lines(lines, 'SteamPACC')
                        self._position_window(rect)
                        self._window.show_overlay()
                        self._shown_appid = None
                        return
                else:
                    appid, name = self._detect_game(title, hwnd)
                    if appid is None:
                        if not force_show:
                            self._hide_overlay()
                            return
                        lines = ['Нет данных о ценах']
                        self._window.set_lines(lines, None)
                        self._position_window(rect)
                        self._window.show_overlay()
                        return
                    self._last_appid = appid
                    self._last_name = name
                    prices = self._prices_from_cache(appid)
                    self._request_prices(appid)

                self._shown_appid = appid
                # Имя игры рисуется в заголовке панели, поэтому в строки
                # цен оно не дублируется.
                lines = format_price_lines(prices)
                self._window.set_lines(lines, name)
                self._position_window(rect)
                self._window.show_overlay()

            except Exception as error:
                log_exception('Ошибка обновления оверлея: ' + str(error))
                self._hide_overlay()

        def _position_window(self, window_rect: tuple[int, int, int, int]) -> None:
            """Position overlay window relative to active window."""
            size = self._window.sizeHint()
            x, y = overlay_position(window_rect, (size.width(), size.height()))
            self._window.resize(size)
            self._window.move(x, y)

        # ----- Трей и настройки -----

        def _make_icon(self) -> QIcon:
            '''Рисует простой значок для трея.'''
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(QColor(*STEAM_ACCENT))
            painter.setPen(QPen(QColor(*STEAM_DARKER_BG), 2))
            painter.drawEllipse(2, 2, 28, 28)
            painter.end()
            return QIcon(pixmap)

        def _setup_tray(self) -> None:
            """Setup system tray icon."""
            self._tray_icon = QSystemTrayIcon()
            self._tray_icon.setIcon(self._make_icon())
            self._tray_icon.setToolTip('SteamPACC — цены игр в разных валютах')

            menu = QMenu()

            show_action = QAction('Показать оверлей')
            show_action.triggered.connect(lambda: self._update_overlay(force_show=True))
            menu.addAction(show_action)

            settings_action = QAction('Настройки')
            settings_action.triggered.connect(self._show_settings)
            menu.addAction(settings_action)

            if self._integrator is not None:
                restart_action = QAction('Перезапустить Steam с ценами')
                restart_action.triggered.connect(self._restart_steam)
                menu.addAction(restart_action)

            report_action = QAction('Отчёт о системе')
            report_action.triggered.connect(self._write_report)
            menu.addAction(report_action)

            menu.addSeparator()

            exit_action = QAction('Выход')
            exit_action.triggered.connect(self._app.quit)
            menu.addAction(exit_action)

            self._tray_icon.setContextMenu(menu)
            self._tray_icon.show()

        def _on_page_currencies(self, currencies: list) -> None:
            '''Выбор регионов, отмеченный в панели настроек внутри Steam.'''
            self._settings = apply_changes(self._settings, {'currencies': list(currencies)})
            save_settings(self._settings)
            log_message('Регионы изменены в окне Steam: ' + ', '.join(currencies))

        def _restart_steam(self) -> None:
            '''Перезапускает Steam с отладочным портом, чтобы цены появились в магазине.'''
            if self._integrator is None:
                return
            root = find_steam_root()
            if root is None:
                show_error('SteamPACC', 'Не найден каталог Steam.')
                return
            steam_exe = Path(root) / 'steam.exe'
            if not steam_exe.is_file():
                show_error('SteamPACC', 'Файл steam.exe не найден: ' + str(steam_exe))
                return
            self._tray_icon.showMessage(
                'SteamPACC', 'Перезапускаю Steam с ценами в магазине…',
                QSystemTrayIcon.MessageIcon.Information, 4000)
            self._integrator.restart_steam_with_debug(str(steam_exe))

        def _write_report(self) -> None:
            '''Пишет отчёт о системе и открывает папку с ним.'''
            from .diagnostics import write_report
            path = write_report()
            log_message('Отчёт о системе создан: ' + str(path))
            try:
                os.startfile(str(path.parent))  # type: ignore[attr-defined]
            except (OSError, AttributeError):
                pass

        def _show_settings(self) -> None:
            """Show settings dialog."""
            dialog = SettingsDialog(self._settings)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                changes = dialog.get_settings()
                self._settings = apply_changes(self._settings, changes)
                save_settings(self._settings)
                self._window.apply_settings(self._settings)
                autostart.set_enabled(self._settings.launch_with_steam)
                if self._integrator is not None:
                    self._integrator.set_enabled(self._settings.integration_enabled)
                    self._integrator.set_currencies(watch_currencies(self._settings))
                # Новые валюты могли появиться: обновляем показ.
                if self._shown_appid is not None:
                    self._request_prices(self._shown_appid)
                self._update_overlay(force_show=True)

        def start(self) -> None:
            """Start the controller."""
            if self._settings.launch_with_steam:
                # Обновляем путь автозапуска: программа могла переехать.
                autostart.set_enabled(True)
            if self._integrator is not None and self._settings.integration_enabled:
                from . import cef as cef_module
                if not cef_module.debug_available():
                    self._tray_icon.showMessage(
                        'SteamPACC',
                        'Цены в магазине включены. Steam запущен без отладки — '
                        'нажмите правой кнопкой по значку и выберите '
                        '«Перезапустить Steam с ценами».',
                        QSystemTrayIcon.MessageIcon.Information, 8000)
            self._update_overlay()

        def stop(self) -> None:
            """Stop the controller."""
            self._timer.stop()
            if self._integrator is not None:
                self._integrator.set_enabled(False)
            self._stop_event.set()
            self._window.hide()


# =============================================================================
# Single Instance and Helper Functions
# =============================================================================

def claim_single_instance() -> bool:
    """Claim single instance mutex."""
    try:
        handle, is_first = win_api.create_named_mutex(SINGLE_INSTANCE_MUTEX)
    except win_api.WinApiError:
        return True
    if is_first:
        return True
    try:
        win_api.close_handle(handle)
    except win_api.WinApiError:
        pass
    return False


def is_first_launch() -> bool:
    """Check if this is the first launch."""
    try:
        from .diagnostics import data_dir
        marker = data_dir() / 'first_launch.marker'
        if marker.exists():
            return False
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('ok', encoding='utf-8')
        return True
    except OSError:
        return False


def is_autostart_launch(arguments: list[str] | None = None) -> bool:
    '''True, если программа запущена из автозапуска Windows (флаг --autostart).'''
    items = list(sys.argv if arguments is None else arguments)
    return any(item.strip().lower() == '--autostart' for item in items)


# =============================================================================
# Test and Main Functions
# =============================================================================

def smoke_test() -> int:
    """Run smoke test for CI."""
    log_message('Старт теста дымом: графическая часть')
    if not QT_AVAILABLE:
        log_message('Тест дымом: PySide6 недоступен')
        return 1

    try:
        win_api.set_dpi_awareness()
        application = QApplication(sys.argv)
        application.setQuitOnLastWindowClosed(False)

        controller = AppController(application)
        log_message('Тест дымом: контроллер создан')

        QTimer.singleShot(2000, application.quit)
        result = int(application.exec())
        controller.stop()
        log_message('Тест дымом: графическая часть работает')
        return result
    except Exception as error:
        log_exception('Тест дымом: ошибка графической части')
        show_error('SteamPACC - ошибка', 'Ошибка теста: ' + str(error))
        return 1


def run() -> int:
    """Run the main application."""
    log_message('Запуск SteamPACC, версия ' + str(app_version))

    if not QT_AVAILABLE:
        log_message('PySide6 недоступен: графическая часть не будет работать')
        show_error(
            'SteamPACC',
            'Не установлена библиотека PySide6.' + chr(10) +
            'Установите её, чтобы программа работала.' + chr(10) +
            'Команда: pip install PySide6'
        )
        return 1

    try:
        # Check single instance
        if not claim_single_instance():
            log_message('SteamPACC уже запущен: второй экземпляр завершает работу')
            return 0

        # Set DPI awareness
        win_api.set_dpi_awareness()

        # Create application
        application = QApplication(sys.argv)
        application.setQuitOnLastWindowClosed(False)
        application.setApplicationName('SteamPACC')

        # Create and start controller
        controller = AppController(application)
        controller.start()

        result = int(application.exec())
        controller.stop()
        return result

    except Exception as error:
        log_exception('Ошибка при запуске приложения')
        show_error(
            'SteamPACC - ошибка',
            'Не удалось запустить приложение: ' + str(error) + chr(10) +
            'Подробности в файле: ' + str(diagnostics.log_path())
        )
        return 1
