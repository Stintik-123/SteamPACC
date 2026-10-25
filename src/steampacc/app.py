"""Графическая часть SteamPACC: окно, трей и интеграция с магазином Steam.

Программа открывается окном со статусом и настройками и живёт в трее.
Цены регионов внедряются прямо в страницы магазина клиентa Steam
(модуль :mod:`steampacc.steam_integration`).
"""

from __future__ import annotations

import os
import sys
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
    CURRENCY_SYMBOLS,
)
from .steam_paths import find_steam_root

try:
    from .steam_integration import SteamIntegrator
    INTEGRATION_AVAILABLE = True
except ImportError:
    INTEGRATION_AVAILABLE = False

try:
    from PySide6.QtCore import QTimer, Qt, Signal, QObject
    from PySide6.QtGui import (
        QAction, QColor, QIcon, QPainter, QPen, QPixmap,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QDialog,
        QFileDialog,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMenu,
        QPushButton,
        QSystemTrayIcon,
        QVBoxLayout,
        QWidget,
    )
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

# Кэш настроек
CACHE_FILE_NAME = 'prices.json'

# Single instance mutex name
SINGLE_INSTANCE_MUTEX = 'SteamPACC.SingleInstance'

#: Надписи интерфейса на двух языках.
STRINGS: dict[str, dict[str, str]] = {
    'ru': {
        'title': 'SteamPACC — цены игр в магазине Steam',
        'ok': ('Всё работает: цены регионов видны на страницах игр\n'
               'в магазине Steam.'),
        'warn': ('Steam запущен без интеграции — цены в магазине не показываются.\n'
                 'Нажмите кнопку ниже: программа перезапустит Steam (~20 секунд).'),
        'off': 'Цены в магазине выключены (галочка ниже).',
        'restart': 'Перезапустить Steam с ценами',
        'regions': 'Регионы цен для показа',
        'look': 'Вид и поведение',
        'light': 'Светлая тема',
        'english': 'English interface',
        'integration': 'Показывать цены в магазине Steam',
        'autostart': 'Запускать вместе с Windows',
        'steam_path': 'Каталог Steam не найден автоматически',
        'steam_pick': 'Указать steam.exe…',
        'apply': 'Применить',
        'hide': 'Свернуть в трей',
        'exit': 'Выход',
        'open': 'Открыть SteamPACC',
        'restart_menu': 'Перезапустить Steam с ценами',
        'report': 'Отчёт о системе',
        'tray_tip': 'SteamPACC — цены игр в разных валютах',
        'tray_hidden': ('Программа продолжает работать в трее. '
                        'Полный выход — правый клик по значку → Выход.'),
        'restarting': 'Перезапускаю Steam с ценами в магазине…',
        'no_steam_dir': 'Не найден каталог Steam.',
        'no_steam_exe': 'Файл steam.exe не найден: ',
    },
    'en': {
        'title': 'SteamPACC — game prices in the Steam store',
        'ok': ('Everything works: regional prices are visible on game pages\n'
               'in the Steam store.'),
        'warn': ('Steam is running without integration — store prices are hidden.\n'
                 'Press the button below: the app will restart Steam (~20 seconds).'),
        'off': 'Store prices are disabled (checkbox below).',
        'restart': 'Restart Steam with prices',
        'regions': 'Price regions to show',
        'look': 'Look and behavior',
        'light': 'Light theme',
        'english': 'Русский интерфейс',
        'integration': 'Show prices in the Steam store',
        'autostart': 'Start with Windows',
        'steam_path': 'Steam directory was not found automatically',
        'steam_pick': 'Choose steam.exe…',
        'apply': 'Apply',
        'hide': 'Minimize to tray',
        'exit': 'Exit',
        'open': 'Open SteamPACC',
        'restart_menu': 'Restart Steam with prices',
        'report': 'System report',
        'tray_tip': 'SteamPACC — game prices in multiple currencies',
        'tray_hidden': ('The app keeps running in the tray. '
                        'To quit fully: right-click the tray icon → Exit.'),
        'restarting': 'Restarting Steam with store prices…',
        'no_steam_dir': 'Steam directory not found.',
        'no_steam_exe': 'steam.exe not found: ',
    },
}


def tr(settings: Settings, key: str) -> str:
    '''Надпись на текущем языке интерфейса.'''
    return STRINGS.get(settings.language, STRINGS['ru']).get(key, key)


#: Кэш проверки отладочного порта: проверка сетевая, из потока интерфейса
#: её надо делать не чаще пары раз в секунду, иначе окно подлагивает.
_PORT_CACHE: dict[str, Any] = {'at': 0.0, 'ok': False}


def port_available_cached() -> bool:
    '''Проверка порта отладки Steam с кэшем на 2 секунды.'''
    now = time.monotonic()
    if now - _PORT_CACHE['at'] >= 2.0:
        from . import cef as cef_module
        _PORT_CACHE['at'] = now
        _PORT_CACHE['ok'] = cef_module.is_steam_devtools(
            cef_module.DEFAULT_DEBUG_PORT, timeout=0.4)
    return bool(_PORT_CACHE['ok'])


def icon_path() -> Path | None:
    '''Путь к значку приложения; в сборке ищет его во временном каталоге.'''
    candidates: list[Path] = []
    base = getattr(sys, '_MEIPASS', None)
    if base:
        candidates.append(Path(base) / 'assets' / 'steampacc.ico')
    here = Path(__file__).parent
    candidates.append(here / 'assets' / 'steampacc.ico')
    candidates.append(here / 'assets' / 'steampacc.png')
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


# =============================================================================
# Кэш цен (используется консольными командами)
# =============================================================================

def cache_path() -> Path:
    '''Возвращает путь к файлу кэша цен в каталоге данных приложения.'''
    return diagnostics.data_dir() / CACHE_FILE_NAME


def watch_currencies(settings: Settings) -> list[str]:
    '''Список валют для показа из настроек; может быть пустым.'''
    return [code.upper() for code in settings.currencies if code]


# =============================================================================
# Single Instance
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


def is_autostart_launch(arguments: list[str] | None = None) -> bool:
    '''True, если программа запущена из автозапуска Windows (флаг --autostart).'''
    items = list(sys.argv if arguments is None else arguments)
    return any(item.strip().lower() == '--autostart' for item in items)


# =============================================================================
# Qt: настройки и контроллер
# =============================================================================

#: Палитры тем окна: тёмная (тёмный фон, белый текст) и светлая
#: (белый фон, чёрный текст).
THEMES: dict[str, dict[str, str]] = {
    'dark': {
        'bg': '#1b2838', 'text': '#ffffff', 'border': '#2a475e',
        'btn': '#2a475e', 'ok': '#3fbf6f', 'warn': '#8fcbee',
    },
    'light': {
        'bg': '#ffffff', 'text': '#000000', 'border': '#d0d7de',
        'btn': '#e8eef4', 'ok': '#1f8f4f', 'warn': '#1a6fb0',
    },
}


if QT_AVAILABLE:
    class MainWindow(QDialog):
        """Главное окно: статус интеграции, регионы цен, автозапуск.

        Программа открывается как обычное приложение с окном; закрытие
        окна сворачивает её в трей, полный выход — через «Выход».
        """

        def __init__(self, controller: 'AppController', parent: QWidget | None = None):
            super().__init__(parent)
            self._controller = controller
            self.setMinimumWidth(520)

            layout = QVBoxLayout()

            # Строка статуса + маленькая кнопка смены языка справа.
            status_row = QHBoxLayout()
            self.status_label = QLabel()
            self.status_label.setWordWrap(True)
            status_row.addWidget(self.status_label, 1)

            self.lang_btn = QPushButton()
            self.lang_btn.setFixedWidth(52)
            self.lang_btn.setToolTip('Русский / English')
            self.lang_btn.clicked.connect(self._toggle_language)
            status_row.addWidget(self.lang_btn, 0)
            layout.addLayout(status_row)

            self.restart_btn = QPushButton()
            self.restart_btn.clicked.connect(controller._restart_steam)
            layout.addWidget(self.restart_btn)

            # Строка пути к Steam, если он не найден автоматически.
            self.steam_path_label = QLabel()
            self.steam_path_label.setWordWrap(True)
            self.steam_path_label.setVisible(False)
            layout.addWidget(self.steam_path_label)
            self.steam_pick_btn = QPushButton()
            self.steam_pick_btn.setVisible(False)
            self.steam_pick_btn.clicked.connect(self._pick_steam_exe)
            layout.addWidget(self.steam_pick_btn)

            # Ретионы цен.
            self.currency_group = QGroupBox()
            currency_grid = QGridLayout()
            settings = controller.settings
            current = {code.upper() for code in settings.currencies}
            self.currency_checks: dict[str, QCheckBox] = {}
            for index, code in enumerate(sorted(CURRENCY_SYMBOLS)):
                box = QCheckBox(code + '  ' + CURRENCY_SYMBOLS[code])
                box.setChecked(code in current)
                self.currency_checks[code] = box
                currency_grid.addWidget(box, index // 4, index % 4)
            self.currency_group.setLayout(currency_grid)
            layout.addWidget(self.currency_group)

            # Вид и поведение.
            self.behavior_group = QGroupBox()
            behavior_layout = QVBoxLayout()

            self.light_theme_check = QCheckBox()
            self.light_theme_check.setChecked(settings.theme == 'light')
            behavior_layout.addWidget(self.light_theme_check)

            self.integration_check = QCheckBox()
            self.integration_check.setChecked(settings.integration_enabled)
            behavior_layout.addWidget(self.integration_check)

            self.autostart_check = QCheckBox()
            self.autostart_check.setChecked(settings.launch_with_steam)
            behavior_layout.addWidget(self.autostart_check)

            self.behavior_group.setLayout(behavior_layout)
            layout.addWidget(self.behavior_group)

            # Кнопки.
            button_layout = QHBoxLayout()
            self.hide_btn = QPushButton()
            self.hide_btn.clicked.connect(self.hide)
            button_layout.addWidget(self.hide_btn)

            self.exit_btn = QPushButton()
            self.exit_btn.clicked.connect(QApplication.instance().quit)
            button_layout.addWidget(self.exit_btn)

            layout.addLayout(button_layout)
            self.setLayout(layout)
            self.retranslate()
            self.apply_theme()

            # Все изменения применяются сами: небольшая пауза собирает
            # серию переключений в одно сохранение.
            self._apply_timer = QTimer(self)
            self._apply_timer.setSingleShot(True)
            self._apply_timer.setInterval(350)
            self._apply_timer.timeout.connect(self._apply)
            for box in list(self.currency_checks.values()) + [
                self.light_theme_check, self.integration_check, self.autostart_check,
            ]:
                box.toggled.connect(self._apply_timer.start)

            # Статус обновляется сам: Steam могли перезапустить в любой момент.
            self._status_timer = QTimer(self)
            self._status_timer.timeout.connect(self.refresh_status)
            self._status_timer.start(3000)
            self.refresh_status()

        def retranslate(self) -> None:
            '''Обновляет все надписи по текущему языку.'''
            settings = self._controller.settings
            self.setWindowTitle(tr(settings, 'title'))
            self.restart_btn.setText(tr(settings, 'restart'))
            self.currency_group.setTitle(tr(settings, 'regions'))
            self.behavior_group.setTitle(tr(settings, 'look'))
            self.light_theme_check.setText(tr(settings, 'light'))
            self.integration_check.setText(tr(settings, 'integration'))
            self.autostart_check.setText(tr(settings, 'autostart'))
            self.hide_btn.setText(tr(settings, 'hide'))
            self.exit_btn.setText(tr(settings, 'exit'))
            self.steam_pick_btn.setText(tr(settings, 'steam_pick'))
            self.steam_path_label.setText(tr(settings, 'steam_path'))
            # Кнопка языка показывает язык, на который переключит.
            self.lang_btn.setText('EN' if settings.language == 'ru' else 'RU')

        def _toggle_language(self) -> None:
            '''Переключает русский/английский и сразу применяет.'''
            new_lang = 'en' if self._controller.settings.language == 'ru' else 'ru'
            self._controller.apply_changes({'language': new_lang})
            self.retranslate()
            self.apply_theme()

        def _theme(self) -> dict[str, str]:
            '''Палитра текущей темы.'''
            name = 'light' if self.light_theme_check.isChecked() else 'dark'
            return THEMES.get(name, THEMES['dark'])

        def apply_theme(self) -> None:
            '''Красит окно по текущей теме.

            Индикатор галочки рисуется явно: на некоторых системах в
            светлой теме он оставался белым на белом и был невидим.
            '''
            t = self._theme()
            self.setStyleSheet(
                'QDialog {{ background-color: {bg}; color: {text}; }}'
                'QGroupBox {{ border: 1px solid {border}; border-radius: 4px;'
                ' margin-top: 10px; padding-top: 6px; }}'
                'QGroupBox::title {{ color: {text}; }}'
                'QCheckBox {{ color: {text}; spacing: 8px; }}'
                'QCheckBox::indicator {{ width: 15px; height: 15px;'
                ' border: 1px solid {border}; border-radius: 3px;'
                ' background-color: {bg}; }}'
                'QCheckBox::indicator:checked {{ background-color: #66c0f4;'
                ' border-color: #66c0f4; image: none; }}'
                'QLabel {{ color: {text}; }}'
                'QPushButton {{ background-color: {btn}; color: {text};'
                ' padding: 6px 14px; border-radius: 3px; }}'
                .format(**t))
            self.restart_btn.setStyleSheet(
                'background-color: #66c0f4; color: #1b2838; font-size: 14px;'
                ' padding: 8px; border-radius: 3px;')
            self.refresh_status()

        def refresh_status(self) -> None:
            '''Обновляет строку состояния и видимость кнопки перезапуска.'''
            settings = self._controller.settings
            t = self._theme()
            steam_found = self._controller.steam_exe_path() is not None
            self.steam_path_label.setVisible(not steam_found)
            self.steam_pick_btn.setVisible(not steam_found)
            if not settings.integration_enabled:
                self.status_label.setText(tr(settings, 'off'))
                self.status_label.setStyleSheet('font-size: 14px; color: %s;' % t['text'])
                self.restart_btn.setVisible(False)
                return
            if port_available_cached():
                self.status_label.setText(tr(settings, 'ok'))
                self.status_label.setStyleSheet('font-size: 14px; color: %s;' % t['ok'])
                self.restart_btn.setVisible(False)
            else:
                self.status_label.setText(tr(settings, 'warn'))
                self.status_label.setStyleSheet('font-size: 14px; color: %s;' % t['warn'])
                self.restart_btn.setVisible(True)

        def _pick_steam_exe(self) -> None:
            '''Диалог выбора steam.exe для нестандартной установки Steam.'''
            path, _ = QFileDialog.getOpenFileName(
                self, 'steam.exe', '', 'steam.exe (steam.exe)')
            if path:
                self._controller.apply_changes({'steam_exe': path})
                self.refresh_status()

        def _apply(self) -> None:
            '''Применяет регионы, тему и галочки (вызывается автоматически).'''
            currencies = [
                code for code, box in self.currency_checks.items() if box.isChecked()
            ]
            self._controller.apply_changes({
                'currencies': currencies,
                'launch_with_steam': self.autostart_check.isChecked(),
                'integration_enabled': self.integration_check.isChecked(),
                'theme': 'light' if self.light_theme_check.isChecked() else 'dark',
            })
            self.retranslate()
            self.apply_theme()

        def closeEvent(self, event) -> None:
            '''Закрытие окна сворачивает программу в трей, а не завершает.'''
            event.ignore()
            self.hide()
            self._controller.notify_hidden_to_tray()

    class AppController(QObject):
        """Контроллер: значок в трее и интеграция с магазином Steam."""

        def __init__(self, application: QApplication):
            super().__init__()
            self._app = application
            self._settings = load_settings()

            self._integrator = None
            if INTEGRATION_AVAILABLE:
                try:
                    self._integrator = SteamIntegrator(self)
                    self._integrator.status_changed.connect(log_message)
                    self._integrator.set_enabled(self._settings.integration_enabled)
                    self._integrator.set_currencies(
                        watch_currencies(self._settings), self._settings.language)
                except Exception as error:
                    log_exception('Интеграция с магазином не запустилась: ' + str(error))

            self._tray_icon = None
            self._window = MainWindow(self)
            self._tray_tip_shown = False
            self._setup_tray()

        @property
        def settings(self) -> Settings:
            '''Текущие настройки.'''
            return self._settings

        def open_window(self) -> None:
            '''Показывает главное окно поверх остальных.'''
            self._window.refresh_status()
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()

        def notify_hidden_to_tray(self) -> None:
            '''Подсказка при первом сворачивании окна в трей.'''
            if self._tray_tip_shown:
                return
            self._tray_tip_shown = True
            self._tray_icon.showMessage(
                'SteamPACC', tr(self._settings, 'tray_hidden'),
                QSystemTrayIcon.MessageIcon.Information, 5000)

        def apply_changes(self, changes: dict) -> None:
            '''Применяет изменения настроек и сразу обновляет интеграцию.'''
            self._settings = apply_changes(self._settings, changes)
            save_settings(self._settings)
            autostart.set_enabled(self._settings.launch_with_steam)
            if self._integrator is not None:
                self._integrator.set_enabled(self._settings.integration_enabled)
                self._integrator.set_currencies(
                    watch_currencies(self._settings), self._settings.language)
            self._setup_tray()

        def steam_exe_path(self) -> Path | None:
            '''Путь к steam.exe: из настроек или найденный автоматически.'''
            if self._settings.steam_exe:
                candidate = Path(self._settings.steam_exe)
                if candidate.is_file():
                    return candidate
            root = find_steam_root()
            if root is None:
                return None
            candidate = Path(root) / 'steam.exe'
            return candidate if candidate.is_file() else None

        def _on_tray_activated(self, reason) -> None:
            '''Левый клик по значку открывает главное окно.'''
            if reason == QSystemTrayIcon.ActivationReason.Trigger:
                self.open_window()

        def _make_icon(self) -> QIcon:
            '''Значок трея: файл из ресурсов, иначе простая окружность.'''
            path = icon_path()
            if path is not None:
                icon = QIcon(str(path))
                if not icon.isNull():
                    return icon
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(QColor(102, 192, 244))
            painter.setPen(QPen(QColor(27, 40, 56), 2))
            painter.drawEllipse(2, 2, 28, 28)
            painter.end()
            return QIcon(pixmap)

        def _setup_tray(self) -> None:
            """Значок в трее с меню управления (пересобирается при смене языка)."""
            if self._tray_icon is None:
                self._tray_icon = QSystemTrayIcon()
                self._tray_icon.activated.connect(self._on_tray_activated)
                self._tray_icon.show()
            self._tray_icon.setIcon(self._make_icon())
            self._tray_icon.setToolTip(tr(self._settings, 'tray_tip'))

            # Ссылка обязательна: без неё PySide6 удаляет меню сразу после
            # настройки, и клики по значку перестают работать.
            self._menu = QMenu()

            open_action = QAction(tr(self._settings, 'open'))
            open_action.triggered.connect(self.open_window)
            self._menu.addAction(open_action)

            if self._integrator is not None:
                restart_action = QAction(tr(self._settings, 'restart_menu'))
                restart_action.triggered.connect(self._restart_steam)
                self._menu.addAction(restart_action)

            report_action = QAction(tr(self._settings, 'report'))
            report_action.triggered.connect(self._write_report)
            self._menu.addAction(report_action)

            self._menu.addSeparator()

            exit_action = QAction(tr(self._settings, 'exit'))
            exit_action.triggered.connect(self._app.quit)
            self._menu.addAction(exit_action)

            self._tray_icon.setContextMenu(self._menu)

        def _restart_steam(self) -> None:
            '''Перезапускает Steam с отладочным портом для интеграции.'''
            if self._integrator is None:
                return
            steam_exe = self.steam_exe_path()
            if steam_exe is None:
                show_error('SteamPACC', tr(self._settings, 'no_steam_dir'))
                self.open_window()
                return
            self._tray_icon.showMessage(
                'SteamPACC', tr(self._settings, 'restarting'),
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

        def start(self) -> None:
            """Запуск контроллера."""
            if self._settings.launch_with_steam:
                # Обновляем путь автозапуска: программа могла переехать.
                autostart.set_enabled(True)
            # Обычный запуск открывает окно; автозапуск молча сидит в трее.
            if not is_autostart_launch():
                self.open_window()

        def stop(self) -> None:
            """Остановка контроллера."""
            if self._integrator is not None:
                self._integrator.set_enabled(False)


# =============================================================================
# Запуск
# =============================================================================

def smoke_test() -> int:
    """Проверка графической части для CI: трей и интегратор создаются."""
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
    """Запуск программы: значок в трее и интеграция с магазином."""
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
        if not claim_single_instance():
            log_message('SteamPACC уже запущен: второй экземпляр завершает работу')
            show_error(
                'SteamPACC',
                'SteamPACC уже запущен: значок в трее рядом с часами'
                + chr(10) + '(в Windows 11 может прятаться под стрелкой ^).'
                + chr(10) + 'Если значок не реагирует — завершите SteamPACC.exe'
                + chr(10) + 'в Диспетчере задач (Ctrl+Shift+Esc) и запустите заново.')
            return 0

        win_api.set_dpi_awareness()

        application = QApplication(sys.argv)
        application.setQuitOnLastWindowClosed(False)
        application.setApplicationName('SteamPACC')
        icon = icon_path()
        if icon is not None:
            application.setWindowIcon(QIcon(str(icon)))

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
