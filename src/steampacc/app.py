"""Графическая часть SteamPACC: значок в трее и интеграция с магазином Steam.

Постоянного окна у программы нет: она живёт в трее и внедряет цены
регионов прямо в страницы магазина клиентa Steam (модуль
:mod:`steampacc.steam_integration`). Оверлей над окнами игр убран —
все цены теперь видны в самом магазине.
"""

from __future__ import annotations

import os
import sys
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
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QMenu,
        QMessageBox,
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
    '''Список валют для показа из настроек.'''
    codes = [code.upper() for code in settings.currencies if code]
    return codes or ['RUB', 'USD', 'EUR']


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

if QT_AVAILABLE:
    class SettingsDialog(QDialog):
        """Окно настроек: регионы цен, интеграция, автозапуск."""

        def __init__(self, settings: Settings, parent: QWidget | None = None):
            super().__init__(parent)
            self._settings = settings
            self.setWindowTitle('SteamPACC — Настройки')
            self.setMinimumWidth(480)

            layout = QVBoxLayout()

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
            """Собирает изменённые настройки."""
            currencies = [
                code for code, box in self.currency_checks.items() if box.isChecked()
            ]
            return {
                'currencies': currencies or ['RUB', 'USD', 'EUR'],
                'launch_with_steam': self.autostart_check.isChecked(),
                'integration_enabled': self.integration_check.isChecked(),
            }

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
                    self._integrator.page_currencies_received.connect(self._on_page_currencies)
                    self._integrator.set_enabled(self._settings.integration_enabled)
                    self._integrator.set_currencies(watch_currencies(self._settings))
                except Exception as error:
                    log_exception('Интеграция с магазином не запустилась: ' + str(error))

            self._tray_icon = None
            self._setup_tray()
            self._tray_icon.activated.connect(self._on_tray_activated)

        def _offer_steam_restart(self) -> None:
            '''Понятное окно с кнопкой: Steam без интеграции, перезапустить?'''
            if self._integrator is None or not self._settings.integration_enabled:
                return
            from . import cef as cef_module
            if cef_module.debug_available():
                return
            box = QMessageBox()
            box.setWindowTitle('SteamPACC — включение цен')
            box.setIcon(QMessageBox.Icon.Information)
            box.setText(
                'Цены в магазине отключены, потому что Steam запущен без интеграции.\n\n'
                'Нажмите кнопку ниже — программа сама перезапустит Steam (~20 секунд), '
                'и цены других регионов появятся на страницах игр в магазине.')
            restart = box.addButton(
                'Перезапустить Steam сейчас', QMessageBox.ButtonRole.AcceptRole)
            box.addButton('Позже', QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is restart:
                self._restart_steam()

        def _on_tray_activated(self, reason) -> None:
            '''Левый клик по значку: то же окно включения цен.'''
            if reason == QSystemTrayIcon.ActivationReason.Trigger:
                self._offer_steam_restart()

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
            """Значок в трее с меню управления."""
            self._tray_icon = QSystemTrayIcon()
            self._tray_icon.setIcon(self._make_icon())
            self._tray_icon.setToolTip('SteamPACC — цены игр в разных валютах')

            # Ссылка обязательна: без неё PySide6 удаляет меню сразу после
            # настройки, и клики по значку перестают работать.
            self._menu = QMenu()

            if self._integrator is not None:
                restart_action = QAction('Перезапустить Steam с ценами')
                restart_action.triggered.connect(self._restart_steam)
                self._menu.addAction(restart_action)

            settings_action = QAction('Настройки')
            settings_action.triggered.connect(self._show_settings)
            self._menu.addAction(settings_action)

            report_action = QAction('Отчёт о системе')
            report_action.triggered.connect(self._write_report)
            self._menu.addAction(report_action)

            self._menu.addSeparator()

            exit_action = QAction('Выход')
            exit_action.triggered.connect(self._app.quit)
            self._menu.addAction(exit_action)

            self._tray_icon.setContextMenu(self._menu)
            self._tray_icon.show()

        def _on_page_currencies(self, currencies: list) -> None:
            '''Выбор регионов, отмеченный в панели настроек внутри Steam.'''
            self._settings = apply_changes(self._settings, {'currencies': list(currencies)})
            save_settings(self._settings)
            log_message('Регионы изменены в окне Steam: ' + ', '.join(currencies))

        def _restart_steam(self) -> None:
            '''Перезапускает Steam с отладочным портом для интеграции.'''
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
            """Окно настроек."""
            dialog = SettingsDialog(self._settings)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                changes = dialog.get_settings()
                self._settings = apply_changes(self._settings, changes)
                save_settings(self._settings)
                autostart.set_enabled(self._settings.launch_with_steam)
                if self._integrator is not None:
                    self._integrator.set_enabled(self._settings.integration_enabled)
                    self._integrator.set_currencies(watch_currencies(self._settings))

        def start(self) -> None:
            """Запуск контроллера."""
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
