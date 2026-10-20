'''Поиск установки Steam и путей к его файлам.

Модуль только читает реестр Windows и вычисляет пути к каталогам и файлам
Steam: ничего не создаёт, не изменяет и не удаляет на диске. На системах,
отличных от Windows, реестр не читается, а импорт модуля остаётся
безопасным.
'''

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.platform == 'win32':
    import winreg
else:
    winreg = None  # type: ignore[assignment]

#: Ветка реестра, в которой Steam хранит путь к установке.
_REGISTRY_KEY = 'Software' + chr(92) + 'Valve' + chr(92) + 'Steam'

#: Значения внутри ветки реестра, которые проверяются по очереди.
_REGISTRY_VALUES = ('SteamPath', 'InstallPath')

#: Переменные среды с каталогами, в которых по умолчанию стоит Steam.
_DEFAULT_VARIABLES = ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')


@dataclass(frozen=True)
class SteamPaths:
    '''Пути к каталогам и файлам установки Steam.'''

    root: Path
    steamapps: Path
    appcache: Path
    appinfo_vdf: Path
    config_vdf: Path
    libraryfolders_vdf: Path
    userdata: Path


def _from_registry() -> Path | None:
    '''Читает путь к Steam из реестра Windows; вне Windows возвращает None.'''
    if winreg is None:
        return None
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for value_name in _REGISTRY_VALUES:
            try:
                with winreg.OpenKey(hive, _REGISTRY_KEY) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
            except OSError:
                continue
            if isinstance(value, str) and value.strip():
                candidate = Path(value)
                if candidate.is_dir():
                    return candidate
    return None


def _default_candidates() -> list[Path]:
    '''Собирает стандартные пути установки Steam из переменных среды.'''
    candidates: list[Path] = []
    for variable in _DEFAULT_VARIABLES:
        base = os.environ.get(variable)
        if not base:
            continue
        candidates.append(Path(base) / 'Steam')
    return candidates


def find_steam_root() -> Path | None:
    '''Возвращает корневой каталог Steam или None, если найти не удалось.

    Сначала проверяется реестр Windows, затем стандартные каталоги, собранные
    из переменных среды. Вне Windows реестр пропускается, поэтому функция
    не падает и возвращает None.
    '''
    registry_root = _from_registry()
    if registry_root is not None:
        return registry_root
    for candidate in _default_candidates():
        if candidate.is_dir():
            return candidate
    return None


def steam_paths(root: Path) -> SteamPaths:
    '''Строит набор путей Steam от известного корневого каталога.

    Функция только вычисляет пути и ничего не создаёт на диске.
    '''
    root = Path(root)
    steamapps = root / 'steamapps'
    appcache = root / 'appcache'
    return SteamPaths(
        root=root,
        steamapps=steamapps,
        appcache=appcache,
        appinfo_vdf=appcache / 'appinfo.vdf',
        config_vdf=root / 'config' / 'config.vdf',
        libraryfolders_vdf=steamapps / 'libraryfolders.vdf',
        userdata=root / 'userdata',
    )
