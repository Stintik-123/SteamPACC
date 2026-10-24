'''Автозапуск SteamPACC вместе с Windows.

Модуль управляет записью в ветке автозагрузки реестра текущего
пользователя (HKCU). Больше ничего в системе не меняется: файлы Steam
и Windows не затрагиваются. Вне Windows функции возвращают False и не
падают.
'''

from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == 'win32':
    import winreg
else:
    winreg = None  # type: ignore[assignment]

#: Ветка реестра автозапуска текущего пользователя.
RUN_KEY = 'Software' + chr(92) + 'Microsoft' + chr(92) + 'Windows' + chr(92) + 'CurrentVersion' + chr(92) + 'Run'

#: Имя значения в ветке автозагрузки.
VALUE_NAME = 'SteamPACC'

#: Ключ запуска, по которому программа понимает, что стартовала из автозагрузки.
AUTOSTART_FLAG = '--autostart'


def _command() -> str:
    '''Собирает командную строку автозапуска для текущего способа запуска.'''
    if getattr(sys, 'frozen', False):
        return '"' + sys.executable + '" ' + AUTOSTART_FLAG
    python = Path(sys.executable).with_name('pythonw.exe')
    if not python.is_file():
        python = Path(sys.executable)
    return '"' + str(python) + '" -m steampacc ' + AUTOSTART_FLAG


def is_enabled() -> bool:
    '''True, если автозапуск включён для текущего пользователя.'''
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
        return isinstance(value, str) and AUTOSTART_FLAG in value
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    '''Включает или выключает автозапуск; True, если изменение удалось.

    Повторное включение обновляет путь: программа может переехать в
    другой каталог, и старая запись перестала бы работать.
    '''
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    return True
        return True
    except OSError:
        return False
