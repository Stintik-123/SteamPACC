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
from typing import Any

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


def _show_dialog(title: str, text: str, icon: int, blocking: bool) -> bool:
    '''Показывает системное окно Windows; True, если окно было показано.

    Окно модальное: пока его не закрыли, программа ждёт. Поэтому в
    автоматической сборке (переменная CI) и при blocking=False диалог
    не показывается вовсе, а текст печатается в консоль.
    '''
    if os.name != 'nt':
        return False
    automatic = os.environ.get('CI', '').strip().lower() in ('1', 'true', 'yes')
    if not blocking or automatic:
        return False
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), icon)
        return True
    except (AttributeError, OSError, ValueError):
        return False


def configure_console() -> None:
    '''Настраивает консоль, чтобы русский текст печатался без ошибок.

    В консоли Windows по умолчанию кодировка cp866 или cp1251, а Python
    печатает в ней кракозябры. Здесь включается кодовая страница UTF-8
    (65001) и потоки переводятся на UTF-8 с заменой непечатаемых
    символов: вывод читается и в cmd, и в PowerShell, и в Git Bash.
    '''
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except (AttributeError, OSError):
            pass
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding='utf-8', errors='replace')
        except (OSError, ValueError):
            pass


def safe_print(text: str, stream: Any | None = None) -> None:
    '''Печатает текст в консоль, не падая ни в какой кодировке.

    В сборке --windowed у процесса нет консоли: sys.stdout и sys.stderr
    равны None, и обычный print завершает программу ошибкой. Здесь
    отсутствие потока не вызывает исключения, а текст пишется с заменой
    непечатаемых символов.
    '''
    target = stream if stream is not None else sys.stdout
    if target is None:
        return
    try:
        target.write(str(text) + chr(10))
        flush = getattr(target, 'flush', None)
        if flush is not None:
            flush()
    except (AttributeError, OSError, UnicodeEncodeError, ValueError):
        pass


def show_error(title: str, text: str, blocking: bool = True) -> None:
    '''Показывает пользователю окно с ошибкой.'''
    if not _show_dialog(title, text, ICON_ERROR, blocking):
        safe_print(str(title) + ': ' + str(text), sys.stderr)


def show_message(title: str, text: str, blocking: bool = True) -> None:
    '''Показывает пользователю окно с сообщением.'''
    if not _show_dialog(title, text, ICON_INFORMATION, blocking):
        safe_print(str(title) + ': ' + str(text), sys.stderr)
