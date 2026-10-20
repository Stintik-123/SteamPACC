'''Графическая часть SteamPACC: оверлей поверх клиента Steam и значок в трее.

Модуль собирает окно оверлея, следит за окном Steam, определяет игру по
заголовку активного окна и показывает цены в выбранных валютах. Qt
подключается лениво: без PySide6 модуль всё равно импортируется, чтобы
работали чистые функции и тесты.

Цены кэшируются на диске, файлы Steam только читаются.
'''

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .config import Settings, load_settings, save_settings
from .prices import Price, PriceError, fetch_price, format_price

try:
    from PySide6.QtCore import QSize, QTimer, Qt
    from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

#: Классы окон клиента Steam: большое окно и надстройка.
STEAM_WINDOW_CLASSES = ('SteamMainWindow', 'SteamClient')

#: Имя файла с кэшем цен.
CACHE_FILE_NAME = 'prices.json'

#: Время жизни записи кэша в секундах.
CACHE_TTL = 900

#: Отступ панели от края окна Steam в пикселях.
PANEL_MARGIN = 24

#: Якоря положения панели оверлея.
ANCHORS = ('top_left', 'top_right', 'bottom_left', 'bottom_right')


def overlay_position(
    steam_rect: tuple[int, int, int, int],
    panel_size: tuple[int, int],
    anchor: str = 'bottom_right',
    margin: int = PANEL_MARGIN,
) -> tuple[int, int]:
    '''Вычисляет положение панели оверлея относительно окна Steam.

    steam_rect — прямоугольник окна Steam (left, top, right, bottom),
    panel_size — размер панели (ширина, высота). Возвращает координаты
    левого верхнего угла панели.
    '''
    if anchor not in ANCHORS:
        raise ValueError('Неизвестный якорь панели: ' + str(anchor))
    left, top, right, bottom = steam_rect
    width, height = panel_size
    if right < left or bottom < top:
        raise ValueError('Некорректный прямоугольник окна Steam')
    if anchor == 'top_left':
        x = left + margin
        y = top + margin
    elif anchor == 'top_right':
        x = right - width - margin
        y = top + margin
    elif anchor == 'bottom_left':
        x = left + margin
        y = bottom - height - margin
    else:
        x = right - width - margin
        y = bottom - height - margin
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


def format_price_lines(prices: dict[str, Price], title: str | None = None) -> list[str]:
    '''Собирает строки панели: название игры и цены по валютам.'''
    lines: list[str] = []
    if title:
        lines.append(title)
    for code in sorted(prices):
        price = prices[code]
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
    '''Читает кэш цен; повреждённый или отсутствующий файл даёт пустой кэш.'''
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(path: Path, data: dict[str, Any]) -> bool:
    '''Сохраняет кэш цен; ошибка записи не прерывает работу программы.'''
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    except OSError:
        return False
    return True


def cached_price(cache: dict[str, Any], appid: int, country: str, ttl: int = CACHE_TTL) -> Price | None:
    '''Достаёт цену из кэша, если запись свежая.'''
    entry = cache.get(country)
    if not isinstance(entry, dict):
        return None
    if entry.get('appid') != appid:
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
            country=country,
            currency=str(data.get('currency', '')),
            final=data.get('final') if isinstance(data.get('final'), int) else None,
            initial=data.get('initial') if isinstance(data.get('initial'), int) else None,
            discount_percent=int(data.get('discount_percent', 0)),
            title=data.get('title') if isinstance(data.get('title'), str) else None,
            is_free=bool(data.get('is_free', False)),
        )
    except (TypeError, ValueError):
        return None


def price_to_dict(price: Price) -> dict[str, Any]:
    '''Превращает цену в словарь для записи в кэш.'''
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
    '''Список валют для показа: из настроек, с запасным вариантом.'''
    codes = [code.upper() for code in settings.currencies if code]
    return codes or ['RUB', 'USD', 'EUR']


def find_steam_window() -> tuple[int, int, int, int] | None:
    '''Ищет окно клиента Steam и возвращает его прямоугольник.

    На системах, отличных от Windows, всегда возвращает None.
    '''
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    try:
        user32 = ctypes.windll.user32
        hwnd = 0
        for class_name in STEAM_WINDOW_CLASSES:
            hwnd = user32.FindWindowW(ctypes.c_wchar_p(class_name), None)
            if hwnd:
                break
        if not hwnd:
            return None
        rect = wintypes.RECT()
        if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return None
    except (AttributeError, OSError, ValueError):
        return None
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def foreground_title() -> str:
    '''Возвращает заголовок активного окна; вне Windows возвращает пустую строку.'''
    if os.name != 'nt':
        return ''
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ''
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
    except (AttributeError, OSError, ValueError):
        return ''
    return buffer.value


if QT_AVAILABLE:

    class OverlayWindow(QWidget):
        '''Прозрачная панель оверлея поверх окна Steam.'''

        def __init__(self, settings: Settings) -> None:
            super().__init__(None)
            self._settings = settings
            self._lines: list[str] = []
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowTransparentForInput
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setWindowOpacity(float(settings.overlay_opacity))

        def set_lines(self, lines: list[str]) -> None:
            '''Заменяет содержимое панели и перерисовывает её.'''
            self._lines = list(lines)
            self.update()
            self.updateGeometry()

        def sizeHint(self) -> QSize:  # type: ignore[override]
            '''Рекомендуемый размер панели по текущему тексту.'''
            width, height = panel_size(self._lines, self._settings.overlay_scale)
            return QSize(width, height)

        def paintEvent(self, event: Any) -> None:
            '''Рисует скруглённую рамку и строки текста.'''
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            scale = self._settings.overlay_scale
            path = QPainterPath()
            path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
            painter.fillPath(path, QColor(18, 18, 18, 200))
            painter.setPen(QPen(QColor(120, 190, 255), 2))
            painter.drawPath(path)
            font = QFont('Segoe UI')
            font.setPixelSize(max(16 * scale // 100, 10))
            painter.setFont(font)
            painter.setPen(QColor(235, 235, 235))
            step = font.pixelSize() + max(6 * scale // 100, 4)
            y = max(12 * scale // 100, 8) + font.pixelSize()
            for line in self._lines:
                painter.drawText(max(12 * scale // 100, 8), y, line)
                y += step

    class AppController:
        '''Управляет оверлеем, значком в трее и обновлением цен.'''

        def __init__(self, application: QApplication) -> None:
            self._app = application
            self._settings = load_settings()
            self._cache_file = cache_path()
            self._cache = load_cache(self._cache_file)
            self._window = OverlayWindow(self._settings)
            self._games: dict[str, int] = {}
            self._appid: int | None = None
            self._timer = QTimer()
            self._timer.timeout.connect(self._tick)
            self._tray = QSystemTrayIcon(self._make_icon(), application)
            menu = QMenu()
            action_refresh = QAction('Обновить цены', menu)
            action_refresh.triggered.connect(self._tick)
            action_show = QAction('Показать оверлей', menu)
            action_show.triggered.connect(self._window.show)
            action_hide = QAction('Скрыть оверлей', menu)
            action_hide.triggered.connect(self._window.hide)
            action_quit = QAction('Выход', menu)
            action_quit.triggered.connect(application.quit)
            menu.addAction(action_refresh)
            menu.addSeparator()
            menu.addAction(action_show)
            menu.addAction(action_hide)
            menu.addSeparator()
            menu.addAction(action_quit)
            self._tray.setContextMenu(menu)
            self._tray.setToolTip('SteamPACC')
            self._tray.show()

        def _make_icon(self) -> QIcon:
            '''Рисует простой значок для трея.'''
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(QColor(120, 190, 255))
            painter.setPen(QPen(QColor(30, 60, 90), 2))
            painter.drawEllipse(2, 2, 28, 28)
            painter.end()
            return QIcon(pixmap)

        def start(self) -> None:
            '''Запускает обновление оверлея и показывает его.'''
            self._tick()
            self._timer.start(2000)

        def _tick(self) -> None:
            '''Обновляет содержимое оверлея; ошибки не прерывают работу.'''
            try:
                self._update_overlay()
            except (OSError, ValueError, RuntimeError, PriceError):
                pass

        def _update_overlay(self) -> None:
            '''Находит окно Steam, определяет игру и обновляет панель.'''
            rect = find_steam_window()
            if rect is None:
                self._window.hide()
                return
            appid = self._detect_appid(foreground_title())
            if appid is None:
                self._window.hide()
                return
            prices = self._prices_for(appid)
            lines = format_price_lines(prices, self._game_name(appid))
            self._window.set_lines(lines)
            width, height = panel_size(lines, self._settings.overlay_scale)
            self._window.resize(width, height)
            x, y = overlay_position(rect, (width, height))
            self._window.move(x, y)
            self._window.show()
            self._window.raise_()

        def _load_games(self) -> None:
            '''Загружает список установленных игр для определения активной.'''
            from .library import read_installed_games
            from .steam_paths import find_steam_root

            root = find_steam_root()
            if root is None:
                return
            try:
                games = read_installed_games(root)
            except OSError:
                return
            self._games = {game.name.lower(): game.appid for game in games}

        def _detect_appid(self, title: str) -> int | None:
            '''Определяет игру по заголовку активного окна.'''
            if not title:
                return None
            if not self._games:
                self._load_games()
            needle = title.lower()
            best: tuple[int, int] | None = None
            for name, appid in self._games.items():
                if name and name in needle and (best is None or len(name) > best[0]):
                    best = (len(name), appid)
            return best[1] if best else None

        def _game_name(self, appid: int) -> str | None:
            '''Возвращает название игры по её идентификатору.'''
            for name, value in self._games.items():
                if value == appid:
                    return name
            return None

        def _prices_for(self, appid: int) -> dict[str, Price]:
            '''Возвращает цены по валютам, пользуясь кэшем.'''
            result: dict[str, Price] = {}
            changed = False
            for code in watch_currencies(self._settings):
                price = cached_price(self._cache, appid, code)
                if price is None:
                    try:
                        price = fetch_price(appid, code.lower())
                    except PriceError:
                        continue
                    self._cache[code] = {
                        'appid': appid,
                        'time': int(time.time()),
                        'price': price_to_dict(price),
                    }
                    changed = True
                result[code] = price
            if changed:
                save_cache(self._cache_file, self._cache)
            return result


def run() -> int:
    '''Запускает графическую часть приложения и возвращает код возврата.'''
    if not QT_AVAILABLE:
        print(
            'SteamPACC: не установлена библиотека PySide6, программа завершает работу.',
            file=sys.stderr,
        )
        return 1
    application = QApplication(sys.argv)
    application.setQuitOnLastWindowClosed(False)
    controller = AppController(application)
    controller.start()
    return int(application.exec())
