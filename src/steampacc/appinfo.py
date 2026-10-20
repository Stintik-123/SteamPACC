'''Сведения об играх из файла appinfo.vdf Steam.

Модуль читает бинарный файл appinfo.vdf и превращает его записи в
структуры AppInfo: имя игры, тип приложения, каталог установки и размер
на диске. Файл только читается, на диск ничего не записывается.
'''

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .vdf import VdfError, iter_appinfo_entries


@dataclass(frozen=True)
class AppInfo:
    '''Сведения об одной игре из appinfo.vdf.'''

    appid: int
    name: str
    type: str
    installdir: str
    is_installed: bool
    size_on_disk: int


def _text(value: Any) -> str:
    '''Приводит значение к строке; отсутствующее значение даёт пустую строку.'''
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    return str(value)


def sizes_from_games(games: Iterable[Any]) -> dict[int, int]:
    '''Собирает сопоставление appid -> размер на диске по установленным играм.'''
    result: dict[int, int] = {}
    for game in games:
        appid = getattr(game, 'appid', None)
        if not isinstance(appid, int):
            continue
        size = getattr(game, 'size_on_disk', 0)
        result[appid] = size if isinstance(size, int) else 0
    return result


def load_appinfo(
    path: Path,
    installed_sizes: Mapping[int, int] | None = None,
) -> list[AppInfo]:
    '''Читает appinfo.vdf и возвращает список сведений об играх.

    Битые записи и записи без имени пропускаются молча, отсутствующий
    файл даёт пустой список. Параметр installed_sizes сопоставляет appid
    с размером установленной игры: по нему определяется признак
    установки.
    '''
    try:
        data = path.read_bytes()
    except OSError:
        return []
    try:
        entries = list(iter_appinfo_entries(data))
    except VdfError:
        return []
    result: list[AppInfo] = []
    for entry in entries:
        appid = entry.get('appid')
        name = _text(entry.get('name'))
        if not isinstance(appid, int) or not name:
            continue
        info = entry.get('info')
        info = info if isinstance(info, dict) else {}
        common = info.get('common')
        common = common if isinstance(common, dict) else {}
        type_name = _text(common.get('type'))
        install_dir = _text(entry.get('install_dir'))
        size = 0
        installed = False
        if installed_sizes is not None:
            size = int(installed_sizes.get(appid, 0))
            installed = appid in installed_sizes
        result.append(
            AppInfo(
                appid=appid,
                name=name,
                type=type_name,
                installdir=install_dir,
                is_installed=installed,
                size_on_disk=size,
            )
        )
    return result


def find_apps(apps: list[AppInfo], query: str) -> list[AppInfo]:
    '''Ищет игры по подстроке имени без учёта регистра.'''
    needle = query.strip().lower()
    if not needle:
        return list(apps)
    return [app for app in apps if needle in app.name.lower()]


def filter_by_type(apps: list[AppInfo], type_name: str) -> list[AppInfo]:
    '''Оставляет только игры указанного типа.'''
    wanted = type_name.strip().lower()
    return [app for app in apps if app.type.lower() == wanted]


def installed_apps(apps: list[AppInfo]) -> list[AppInfo]:
    '''Оставляет только установленные игры.'''
    return [app for app in apps if app.is_installed]
