"""Графическая часть SteamPACC: оверлей поверх окна Steam.

Модуль отвечает за отображение цен игр в оверлее поверх окна Steam.
Стиль оверлея максимально приближен к нативному стилю Steam.

Основные функции:
- Автоматическое обнаружение активной игры
- Отображение цен в нативном стиле Steam
- Кэширование цен для быстрой работы
- Интеграция с треем Windows
- Настройки через контекстное меню
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import win_api
from . import diagnostics
from . import __version__ as app_version
from .config import Settings, load_settings, save_settings
from .diagnostics import (
    log_exception,
    log_message,
    show_error,
)
from .prices import (
    CURRENCY_COUNTRIES,
    CURRENCY_SYMBOLS,
    Price,
    PriceError,
    fetch_price,
    format_price,
)
from .steam_paths import find_steam_root, steam_paths
from .library import iter_library_games, read_library_folders

try:
    from PySide6.QtCore import QSize, QTimer, Qt, Signal, QObject
    from PySide6.QtGui import (
        QAction, QBrush, QColor, QFont, QIcon, QLinearGradient,
        QPainter, QPainterPath, QPen, QPixmap,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMenu,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QSystemTrayIcon,
        QVBoxLayout,
        QWidget,
    )
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


# Steam window classes to detect
STEAM_WINDOW_CLASSES = ('SteamMainWindow', 'SteamClient', 'vguiPopupWindow')

# Cache settings
CACHE_FILE_NAME = 'prices.json'
CACHE_TTL = 900  # 15 minutes in seconds

# Panel positioning
PANEL_MARGIN = 16
UPDATE_INTERVAL_MS = 300  # Update every 300ms

# Steam color palette
STEAM_DARK_BG = (27, 39, 56)    # #1b2838
STEAM_DARKER_BG = (20, 30, 45)  # #141e2d
STEAM_ACCENT = (102, 192, 244)  # #66c0f4
STEAM_TEXT = (200, 200, 200)    # Light gray
STEAM_TEXT_DIM = (120, 120, 120) # Dim text
STEAM_BORDER = (50, 60, 75)     # Border color

# Single instance mutex name
SINGLE_INSTANCE_MUTEX = 'SteamPACC.SingleInstance'


# =============================================================================
# Utility Functions
# =============================================================================

def overlay_position(
    steam_rect: tuple[int, int, int, int],
    panel_size: tuple[int, int],
    margin: int = PANEL_MARGIN,
) -> tuple[int, int]:
    """Calculate overlay position relative to Steam window."""
    left, top, right, bottom = steam_rect
    width, height = panel_size
    
    if right < left or bottom < top:
        return (0, 0)
    
    # Position at bottom-right corner of Steam window
    x = right - width - margin
    y = bottom - height - margin
    
    return int(x), int(y)


def panel_size(lines: list[str], scale: int = 100) -> tuple[int, int]:
    """Calculate panel size based on content and scale."""
    if scale <= 0:
        scale = 100
    
    if not lines:
        return 200, 80
    
    longest = max((len(line) for line in lines), default=0)
    char_width = max(8 * scale // 100, 1)
    line_height = max(20 * scale // 100, 1)
    
    width = max(longest * char_width + 32, 200)
    height = max(len(lines), 1) * line_height + 20
    
    return width, height


def format_price_lines(prices: dict[str, Price], game_name: str | None = None) -> list[str]:
    """Format price information into displayable lines."""
    lines: list[str] = []
    
    if game_name:
        # Truncate long game names
        if len(game_name) > 40:
            game_name = game_name[:37] + "..."
        lines.append(game_name)
        lines.append("-" * len(game_name))
    
    for code in sorted(prices):
        price = prices[code]
        label = price.currency or code.upper()
        price_text = format_price(price)
        lines.append(f"{label}: {price_text}")
    
    if not lines:
        lines.append("Цены недоступны")
    
    return lines


def cache_path() -> Path:
    """Get cache file path."""
    if os.name == 'nt':
        base = os.environ.get('APPDATA')
        if base:
            return Path(base) / 'SteamPACC' / CACHE_FILE_NAME
    return Path.home() / '.config' / 'SteamPACC' / CACHE_FILE_NAME


def load_cache(path: Path) -> dict[str, Any]:
    """Load price cache from file."""
    try:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_cache(path: Path, data: dict[str, Any]) -> bool:
    """Save price cache to file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        return True
    except OSError:
        return False
    return True


def cached_price(cache: dict[str, Any], appid: int, country: str, ttl: int = CACHE_TTL) -> Price | None:
    """Get price from cache if valid."""
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
    """Convert Price to dictionary for caching."""
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
    """Get list of currencies to display."""
    codes = [code.upper() for code in settings.currencies if code]
    return codes or ['RUB', 'USD', 'EUR']


# =============================================================================
# Window Detection
# =============================================================================

def find_steam_window() -> tuple[int, int, int, int] | None:
    """Find Steam window and return its rectangle."""
    for class_name in STEAM_WINDOW_CLASSES:
        try:
            hwnd = win_api.find_window_by_class(class_name)
        except win_api.WinApiError:
            return None
        if not hwnd:
            continue
        rect = win_api.window_rect(hwnd)
        if rect is not None:
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
            
            # Steam-like styling
            self.setWindowOpacity(float(settings.overlay_opacity))
            
            # Fonts
            self._font = QFont("Segoe UI", 10)
            self._bold_font = QFont("Segoe UI", 11, QFont.Weight.Bold)
            
            # Corner radius
            self._corner_radius = 8
            
            # Colors
            self._colors = {
                'dark_bg': QColor(*STEAM_DARK_BG),
                'darker_bg': QColor(*STEAM_DARKER_BG),
                'accent': QColor(*STEAM_ACCENT),
                'text': QColor(*STEAM_TEXT),
                'text_dim': QColor(*STEAM_TEXT_DIM),
                'border': QColor(*STEAM_BORDER),
            }
        
        def set_lines(self, lines: list[str], game_name: str | None = None) -> None:
            """Set lines to display."""
            self._lines = list(lines)
            self._game_name = game_name
            self.update()
            self.updateGeometry()
        
        def sizeHint(self) -> QSize:
            """Calculate size based on content."""
            if not self._lines:
                return QSize(200, 80)
            
            scale = self._settings.overlay_scale
            char_width = max(8 * scale // 100, 1)
            line_height = max(20 * scale // 100, 1)
            
            # Calculate width
            fm = QFontMetrics(self._font)
            max_width = max(fm.horizontalAdvance(line) for line in self._lines)
            
            if self._game_name:
                fm_bold = QFontMetrics(self._bold_font)
                game_width = fm_bold.horizontalAdvance(self._game_name)
                max_width = max(max_width, game_width)
            
            width = max(max_width + 32, 200)
            height = len(self._lines) * line_height + 40
            
            if self._game_name:
                height += line_height + 10
            
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
            
            # Draw content
            painter.setPen(QPen(self._colors['text']))
            
            x = 16
            y = 14
            
            # Draw game name (bold)
            if self._game_name:
                painter.setFont(self._bold_font)
                painter.drawText(x, y + self._bold_font.pointSize() + 2, self._game_name)
                y += self._bold_font.pointSize() + 8
                
                # Draw separator line
                painter.setPen(QPen(self._colors['border'], 1))
                painter.drawLine(x, y, self.width() - 16, y)
                y += 8
            
            # Draw price lines
            painter.setFont(self._font)
            line_height = QFontMetrics(self._font).height()
            
            for line in self._lines:
                painter.drawText(x, y + line_height, line)
                y += line_height
            
            painter.end()

    class SettingsDialog(QDialog):
        """Settings dialog."""
        
        def __init__(self, settings: Settings, parent: QWidget | None = None):
            super().__init__(parent)
            self._settings = settings
            self.setWindowTitle("SteamPACC - Настройки")
            self.setMinimumWidth(450)
            
            layout = QVBoxLayout()
            
            # ===== General Settings =====
            general_group = QGroupBox("Отображение")
            general_form = QFormLayout()
            
            # Currencies
            self.currency_combo = QComboBox()
            currency_presets = [
                ("Русский (RUB, USD, EUR)", ("RUB", "USD", "EUR")),
                ("Английский (USD, EUR, GBP)", ("USD", "EUR", "GBP")),
                ("Турецкий (TRY, USD, EUR)", ("TRY", "USD", "EUR")),
                ("Казахстанский (KZT, RUB, USD)", ("KZT", "RUB", "USD")),
                ("Все валюты", tuple(SUPPORTED_COUNTRIES.keys())),
            ]
            
            for text, codes in currency_presets:
                self.currency_combo.addItem(text, codes)
            
            # Find current preset
            current = list(settings.currencies)
            for i, (text, codes) in enumerate(currency_presets):
                if list(codes) == current:
                    self.currency_combo.setCurrentIndex(i)
                    break
            
            general_form.addRow("Валюты:", self.currency_combo)
            
            # Opacity
            self.opacity_spin = QDoubleSpinBox()
            self.opacity_spin.setRange(0.5, 1.0)
            self.opacity_spin.setSingleStep(0.1)
            self.opacity_spin.setValue(settings.overlay_opacity)
            general_form.addRow("Прозрачность:", self.opacity_spin)
            
            # Scale
            self.scale_spin = QSpinBox()
            self.scale_spin.setRange(75, 150)
            self.scale_spin.setValue(settings.overlay_scale)
            general_form.addRow("Масштаб:", self.scale_spin)
            
            general_group.setLayout(general_form)
            layout.addWidget(general_group)
            
            # ===== Behavior Settings =====
            behavior_group = QGroupBox("Поведение")
            behavior_layout = QVBoxLayout()
            
            self.autostart_check = QCheckBox("Запускать с Windows")
            self.autostart_check.setChecked(settings.launch_with_steam)
            behavior_layout.addWidget(self.autostart_check)
            
            self.show_on_game_check = QCheckBox("Показывать только на страницах игр")
            self.show_on_game_check.setChecked(True)
            behavior_layout.addWidget(self.show_on_game_check)
            
            behavior_group.setLayout(behavior_layout)
            layout.addWidget(behavior_group)
            
            # ===== Buttons =====
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            
            save_btn = QPushButton("Сохранить")
            save_btn.clicked.connect(self.accept)
            button_layout.addWidget(save_btn)
            
            cancel_btn = QPushButton("Отмена")
            cancel_btn.clicked.connect(self.reject)
            button_layout.addWidget(cancel_btn)
            
            layout.addLayout(button_layout)
            self.setLayout(layout)
        
        def get_settings(self) -> dict:
            """Get updated settings."""
            currencies = self.currency_combo.currentData()
            if not currencies:
                currencies = ("RUB", "USD", "EUR")
            
            return {
                'currencies': list(currencies),
                'overlay_opacity': self.opacity_spin.value(),
                'overlay_scale': self.scale_spin.value(),
                'launch_with_steam': self.autostart_check.isChecked(),
            }


# =============================================================================
# Main Application Controller
# =============================================================================

if QT_AVAILABLE:
    class AppController(QObject):
        """Main application controller."""
        
        settings_changed = Signal()
        
        def __init__(self, application: QApplication):
            super().__init__()
            self._app = application
            self._settings = load_settings()
            self._cache: dict[str, Any] = {}
            self._cache_file = cache_path()
            self._games: dict[str, int] = {}  # name.lower() -> appid
            
            # Load cache
            self._cache = load_cache(self._cache_file)
            
            # Create overlay window
            self._window = NativeOverlayWindow(self._settings)
            
            # Tray icon
            self._tray_icon = None
            self._setup_tray()
            
            # Update timer
            self._timer = QTimer()
            self._timer.timeout.connect(self._update_overlay)
            self._timer.start(UPDATE_INTERVAL_MS)
            
            # State
            self._last_appid: int | None = None
            self._last_show_time: float = 0
            self._min_show_interval: float = 0.5  # Don't update too frequently
        
        def _setup_tray(self) -> None:
            """Setup system tray icon."""
            self._tray_icon = QSystemTrayIcon()
            self._tray_icon.setToolTip("SteamPACC - Показ цен игр")
            
            # Create menu
            menu = QMenu()
            
            show_action = QAction("Показать оверлей")
            show_action.triggered.connect(self._force_show_overlay)
            menu.addAction(show_action)
            
            settings_action = QAction("Настройки")
            settings_action.triggered.connect(self._show_settings)
            menu.addAction(settings_action)
            
            menu.addSeparator()
            
            exit_action = QAction("Выход")
            exit_action.triggered.connect(self._app.quit)
            menu.addAction(exit_action)
            
            self._tray_icon.setContextMenu(menu)
            self._tray_icon.show()
        
        def _force_show_overlay(self) -> None:
            """Force show overlay."""
            self._update_overlay(force_show=True)
        
        def _show_settings(self) -> None:
            """Show settings dialog."""
            dialog = SettingsDialog(self._settings)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                changes = dialog.get_settings()
                self._settings = Settings(
                    language=self._settings.language,
                    country=self._settings.country,
                    overlay_opacity=changes['overlay_opacity'],
                    overlay_scale=changes['overlay_scale'],
                    show_fps=self._settings.show_fps,
                    update_interval=self._settings.update_interval,
                    launch_with_steam=changes['launch_with_steam'],
                    currencies=tuple(changes['currencies']),
                )
                save_settings(self._settings)
                self._window.setWindowOpacity(float(self._settings.overlay_opacity))
                self.settings_changed.emit()
        
        def _load_games(self) -> None:
            """Load installed games from Steam library."""
            try:
                root = find_steam_root()
                if root is None:
                    return
                
                roots: list[Path] = [root]
                try:
                    folders_file = steam_paths(root).libraryfolders_vdf
                    if folders_file.is_file():
                        text = folders_file.read_text(encoding='utf-8', errors='ignore')
                        roots.extend(read_library_folders(text))
                except OSError:
                    pass
                
                # Remove duplicates
                unique: list[Path] = []
                for item in roots:
                    if item not in unique:
                        unique.append(item)
                
                # Load games
                games = list(iter_library_games(unique))
                self._games = {game.name.lower(): game.appid for game in games}
                log_message(f"Загружено {len(self._games)} игр из библиотеки Steam")
            except Exception as e:
                log_message(f"Ошибка загрузки игр: {e}")
                self._games = {}
        
        def _detect_appid(self, title: str) -> int | None:
            """Detect game appid from window title."""
            if not title:
                return None
            
            # Try to extract appid directly from title
            match = re.search(r'App (\d+)', title)
            if match:
                return int(match.group(1))
            
            # Match game name
            if not self._games:
                self._load_games()
            
            needle = title.lower()
            best: tuple[int, int] | None = None
            for name, appid in self._games.items():
                if name and name in needle and (best is None or len(name) > best[0]):
                    best = (len(name), appid)
            
            return best[1] if best else None
        
        def _get_cached_price(self, appid: int, country: str) -> Price | None:
            """Get price from cache."""
            return cached_price(self._cache, appid, country)
        
        def _fetch_prices(self, appid: int) -> dict[str, Price]:
            """Fetch prices for a game."""
            result: dict[str, Price] = {}
            changed = False
            
            for code in watch_currencies(self._settings):
                price = self._get_cached_price(appid, code)
                
                if price is None:
                    try:
                        country = CURRENCY_COUNTRIES.get(code, code.lower())
                        price = fetch_price(appid, country)
                        
                        self._cache[code] = {
                            'appid': appid,
                            'time': int(time.time()),
                            'price': price_to_dict(price),
                        }
                        changed = True
                    except PriceError:
                        continue
                
                result[code] = price
            
            if changed:
                save_cache(self._cache_file, self._cache)
            
            return result
        
        def _format_price_lines(self, prices: dict[str, Price], game_name: str | None = None) -> list[str]:
            """Format prices for display."""
            return format_price_lines(prices, game_name)
        
        def _update_overlay(self, force_show: bool = False) -> None:
            """Update overlay with current game prices."""
            try:
                # Rate limiting
                now = time.time()
                if not force_show and now - self._last_show_time < self._min_show_interval:
                    return
                self._last_show_time = now
                
                # Get foreground window info
                info = foreground_window()
                if info is None:
                    self._window.hide()
                    return
                
                hwnd, rect, title, class_name = info
                
                # Check if minimized
                if is_minimized(hwnd):
                    self._window.hide()
                    return
                
                # Detect appid
                appid = self._detect_appid(title)
                game_name = title if title else None
                
                # If it's Steam main window, show hint
                if class_name in STEAM_WINDOW_CLASSES and appid is None:
                    lines = [
                        "SteamPACC работает",
                        "Наведите на игру, чтобы",
                        "увидеть цены в разных валютах"
                    ]
                    self._window.set_lines(lines, "Steam")
                    self._position_window(rect)
                    self._window.show()
                    return
                
                # If no appid detected, hide overlay
                if appid is None and not force_show:
                    self._window.hide()
                    return
                
                # Fetch and display prices
                prices = self._fetch_prices(appid) if appid else {}
                lines = self._format_price_lines(prices, game_name)
                
                self._window.set_lines(lines, game_name)
                self._position_window(rect)
                self._window.show()
                self._window.raise_()
                
            except Exception as e:
                log_exception(f"Ошибка обновления оверлея: {e}")
                self._window.hide()
        
        def _position_window(self, steam_rect: tuple[int, int, int, int]) -> None:
            """Position overlay window relative to Steam window."""
            x, y = overlay_position(steam_rect, self._window.sizeHint())
            size = self._window.sizeHint()
            self._window.resize(size)
            self._window.move(x, y)
        
        def start(self) -> None:
            """Start the controller."""
            # Load games
            self._load_games()
            
            # Initial update
            self._update_overlay()
        
        def stop(self) -> None:
            """Stop the controller."""
            self._timer.stop()
            if self._window:
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


def is_autostart_launch(self, arguments: list[str] | None = None) -> bool:
    """Check if launched from autostart."""
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
        log_message('Тест дымом: графическая часть работает')
        return result
    except Exception as error:
        log_exception('Тест дымом: ошибка графической части')
        show_error('SteamPACC - ошибка', f'Ошибка теста: {error}')
        return 1


def run() -> int:
    """Run the main application."""
    log_message('Запуск SteamPACC, версия ' + app_version())
    
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
        application.setApplicationName("SteamPACC")
        
        # Create and start controller
        controller = AppController(application)
        controller.start()
        
        return int(application.exec())
        
    except Exception as error:
        log_exception('Ошибка при запуске приложения')
        show_error(
            'SteamPACC - ошибка',
            'Не удалось запустить приложение: ' + str(error) + chr(10) +
            'Подробности в файле: ' + str(diagnostics.log_path())
        )
        return 1
