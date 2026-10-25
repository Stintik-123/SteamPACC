'''Пользовательские настройки приложения SteamPACC.

Модуль хранит настройки приложения в файле JSON в каталоге данных
пользователя. Файлы Steam при этом не изменяются и используются
только для чтения.
'''

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Имя каталога с данными приложения.
APP_DIR_NAME = 'SteamPACC'

#: Имя файла настроек.
SETTINGS_FILE_NAME = 'config.json'

#: Поддерживаемые языки интерфейса.
LANGUAGES = ('ru', 'en')

#: Поддерживаемые темы окна.
THEMES = ('dark', 'light')


@dataclass(frozen=True)
class Settings:
    '''Пользовательские настройки приложения.'''

    language: str = 'ru'
    currencies: tuple[str, ...] = ('RUB', 'USD', 'EUR')
    integration_enabled: bool = True
    theme: str = 'dark'
    launch_with_steam: bool = False
    #: Путь к steam.exe, если Steam стоит в нестандартном месте.
    steam_exe: str = ''


def _as_bool(value: Any, default: bool) -> bool:
    '''Приводит значение к логическому, при неудаче берёт значение по умолчанию.'''
    if isinstance(value, bool):
        return value
    return default


def _as_str(value: Any, default: str) -> str:
    '''Приводит значение к строке, при неудаче берёт значение по умолчанию.'''
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _as_choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    '''Выбирает значение из списка разрешённых; мусор даёт умолчание.'''
    text = value if isinstance(value, str) else ''
    return text.strip().lower() if text.strip().lower() in allowed else default


def settings_path() -> Path:
    '''Возвращает путь к файлу настроек; сам файл при этом не создаётся.'''
    if os.name == 'nt':
        base = os.environ.get('APPDATA')
        if base:
            return Path(base) / APP_DIR_NAME / SETTINGS_FILE_NAME
    base = os.environ.get('XDG_CONFIG_HOME')
    if base:
        return Path(base) / APP_DIR_NAME / SETTINGS_FILE_NAME
    return Path.home() / '.config' / APP_DIR_NAME / SETTINGS_FILE_NAME


def _as_str_list(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    '''Приводит значение к списку строк; пустой список разрешён.

    Пустой список — осмысленный выбор: пользователь выключил все
    регионы, и блок цен в магазине показываться не должен.
    '''
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        return default
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            code = item.strip().upper()
            if code and code not in result:
                result.append(code)
        if len(result) >= 8:
            break
    return tuple(result)


def _from_mapping(data: dict) -> Settings:
    '''Собирает настройки из словаря, отбрасывая лишние и неверные значения.'''
    base = Settings()
    return Settings(
        language=_as_choice(data.get('language'), LANGUAGES, base.language),
        currencies=_as_str_list(data.get('currencies'), base.currencies),
        integration_enabled=_as_bool(data.get('integration_enabled'), base.integration_enabled),
        theme=_as_choice(data.get('theme'), THEMES, base.theme),
        launch_with_steam=_as_bool(data.get('launch_with_steam'), base.launch_with_steam),
        steam_exe=_as_str(data.get('steam_exe'), base.steam_exe),
    )


def load_settings(path: Path | None = None) -> Settings:
    '''Читает настройки; при отсутствии или повреждении файла берутся умолчания.'''
    target = Path(path) if path is not None else settings_path()
    try:
        text = target.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return Settings()
    try:
        data = json.loads(text)
    except ValueError:
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    return _from_mapping(data)


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    '''Записывает настройки в JSON-файл и возвращает путь к нему.'''
    target = Path(path) if path is not None else settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'language': settings.language,
        'currencies': list(settings.currencies),
        'integration_enabled': settings.integration_enabled,
        'theme': settings.theme,
        'launch_with_steam': settings.launch_with_steam,
        'steam_exe': settings.steam_exe,
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return target


def apply_changes(settings: Settings, changes: dict) -> Settings:
    '''Применяет изменения к настройкам и проверяет значения.'''
    merged = {
        'language': settings.language,
        'currencies': list(settings.currencies),
        'integration_enabled': settings.integration_enabled,
        'theme': settings.theme,
        'launch_with_steam': settings.launch_with_steam,
        'steam_exe': settings.steam_exe,
    }
    merged.update(changes)
    return _from_mapping(merged)
