'''Журнал работы приложения и отчёт о состоянии.

Журнал нужен, чтобы пользователь мог прислать файл, и мы увидели, что
происходит у него на компьютере: где программа искала Steam, что показал
оверлей и были ли ошибки. Отчёт собирается из журнала и сведений о системе.

Модуль использует только стандартную библиотеку и не падает: ошибки записи
в файл никогда не прерывают работу приложения.
'''

from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path

#: Имя файла журнала работы.
LOG_FILE_NAME = 'steampacc.log'

#: Имя файла отчёта о состоянии.
REPORT_FILE_NAME = 'otchet.txt'

#: Максимальный размер журнала в байтах: при переполнении он очищается.
MAX_LOG_BYTES = 512 * 1024

#: Код значка ошибки в системном окне Windows.
ICON_ERROR = 0x00000010

#: Код значка информации в системном окне Windows.
ICON_INFORMATION = 0x00000040


def data_dir() -> Path:
    '''Каталог данных приложения: APPDATA/SteamPACC.'''
    base = os.environ.get('APPDATA') or os.environ.get('XDG_CONFIG_HOME')
    if base:
        return Path(base) / 'SteamPACC'
    return Path.home() / '.config' / 'SteamPACC'


def log_path() -> Path:
    '''Путь к файлу журнала работы.'''
    return data_dir() / LOG_FILE_NAME


def report_path() -> Path:
    '''Путь к файлу отчёта о состоянии.'''
    return data_dir() / REPORT_FILE_NAME


def log_message(text: str) -> None:
    '''Дописывает строку в журнал; ошибки записи не мешают работе.'''
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.write_text('', encoding='utf-8')
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with path.open('a', encoding='utf-8') as handle:
            handle.write(stamp + ' | ' + str(text) + chr(10))
    except OSError:
        pass


def log_exception(text: str) -> None:
    '''Записывает в журнал текст ошибки вместе с трассировкой.'''
    try:
        import traceback

        detail = traceback.format_exc().replace(chr(10), ' | ')
        log_message(str(text) + ': ' + detail)
    except Exception:
        log_message(str(text))


def read_log(limit: int = 200) -> list[str]:
    '''Возвращает последние строки журнала.'''
    try:
        lines = log_path().read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return []
    if limit <= 0:
        return []
    return lines[-limit:]


def system_info() -> list[str]:
    '''Собирает сведения о системе и о запуске программы.'''
    return [
        'Python: ' + sys.version.split()[0],
        'Система: ' + platform.platform(),
        'Каталог данных: ' + str(data_dir()),
        'Файл журнала: ' + str(log_path()),
        'Аргументы запуска: ' + (' '.join(sys.argv) if sys.argv else '-'),
    ]


def write_report(extra: list[str] | None = None) -> Path:
    '''Записывает отчёт о состоянии и возвращает путь к файлу.'''
    path = report_path()
    body = [
        'SteamPACC: отчёт о работе',
        'Создан: ' + time.strftime('%Y-%m-%d %H:%M:%S'),
        '',
    ]
    body.extend(system_info())
    body.append('')
    body.extend(extra or [])
    body.append('')
    body.append('--- Журнал (последние строки) ---')
    body.extend(read_log())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(chr(10).join(body), encoding='utf-8')
    except OSError:
        pass
    return path


def _message_box(title: str, text: str, icon: int) -> None:
    '''Показывает системное окно Windows; вне Windows — печатает в консоль.'''
    if os.name == 'nt':
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, str(text), str(title), icon)
            return
        except (AttributeError, OSError, ValueError):
            pass
    print(str(title) + ': ' + str(text), file=sys.stderr)


def show_error(title: str, text: str) -> None:
    '''Показывает пользователю окно с ошибкой.'''
    _message_box(title, text, ICON_ERROR)


def show_message(title: str, text: str) -> None:
    '''Показывает пользователю окно с сообщением.'''
    _message_box(title, text, ICON_INFORMATION)
