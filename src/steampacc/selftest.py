'''Самопроверка SteamPACC: сведения о системе и отчёт на диске.

Модуль нужен, чтобы понять, на каком шаге программа
останавливается на чужом
компьютере. Он не зависит ни от PySide6, ни от сети и
работает на любой системе.
'''

from __future__ import annotations

import importlib.util
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

#: Имя файла отчёта самопроверки.
SELFTEST_FILE_NAME = 'samoproverka.txt'

#: Названия полей отчёта: ключ в словаре и заголовок в тексте.
REPORT_FIELDS: tuple[tuple[str, str], ...] = (
    ('os', 'ОС'),
    ('python', 'Python'),
    ('qt_available', 'PySide6 установлена'),
    ('frozen', 'Собрано PyInstaller'),
    ('executable', 'Исполняемый файл'),
    ('executable_exists', 'Исполняемый файл на месте'),
    ('data_dir', 'Каталог данных'),
    ('data_dir_writable', 'Каталог данных доступен для записи'),
    ('steam_root', 'Каталог Steam'),
    ('ci', 'Переменная CI'),
    ('args', 'Аргументы запуска'),
    ('time', 'Время проверки'),
)


def _qt_available() -> bool:
    '''True, если PySide6 установлена; сама библиотека не импортируется.'''
    try:
        return importlib.util.find_spec('PySide6') is not None
    except (ImportError, ValueError):
        return False


def _steam_root() -> str:
    '''Возвращает путь к каталогу Steam, если он найден.'''
    try:
        from .steam_paths import find_steam_root

        root = find_steam_root()
        if root is not None:
            return str(root)
    except Exception:
        pass
    return 'не найден'


def _data_dir() -> Path:
    '''Возвращает каталог данных программы.'''
    try:
        from .diagnostics import data_dir

        return Path(data_dir())
    except Exception:
        return Path.home() / '.config' / 'SteamPACC'


def _can_write(folder: Path) -> bool:
    '''True, если в каталог удаётся записать файл.'''
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / 'proba_zapisi.tmp'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
        return True
    except OSError:
        return False


def collect_info() -> dict[str, Any]:
    '''Собирает сведения о системе и о запуске программы.'''
    executable = Path(sys.executable)
    data = _data_dir()
    return {
        'os': platform.system() + ' ' + platform.release() + ' (' + platform.machine() + ')',
        'python': sys.version.split()[0],
        'qt_available': _qt_available(),
        'frozen': bool(getattr(sys, 'frozen', False)),
        'executable': str(executable),
        'executable_exists': executable.exists(),
        'data_dir': str(data),
        'data_dir_writable': _can_write(data),
        'steam_root': _steam_root(),
        'ci': os.environ.get('CI', '-'),
        'args': ' '.join(sys.argv),
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    }


def format_report(info: dict[str, Any]) -> str:
    '''Собирает текст отчёта по сведениям о системе.'''
    lines = [
        'SteamPACC: отчёт самопроверки',
        'Создан: ' + time.strftime('%Y-%m-%d %H:%M:%S'),
        '',
    ]
    for key, title in REPORT_FIELDS:
        lines.append(title + ': ' + str(info.get(key, '-')))
    lines.append('')
    return chr(10).join(lines)


def run_selftest(out_path: Path | None = None) -> Path:
    '''Собирает отчёт о системе и записывает его в файл; возвращает путь.'''
    info = collect_info()
    text = format_report(info)
    target = Path(out_path) if out_path is not None else _data_dir() / SELFTEST_FILE_NAME
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    except OSError as error:
        try:
            target.write_text(
                text + chr(10) + 'Ошибка записи: ' + str(error),
                encoding='utf-8',
            )
        except OSError:
            pass
    return target
