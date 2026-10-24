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

#: Минимальная и максимальная прозрачность оверлея.
MIN_OPACITY = 0.1
MAX_OPACITY = 1.0

#: Минимальный и максимальный масштаб оверлея в процентах.
MIN_SCALE = 50
MAX_SCALE = 200

#: Минимальный и максимальный интервал обновления в секундах.
MIN_INTERVAL = 10
MAX_INTERVAL = 3600


@dataclass(frozen=True)
class Settings:
    '''Пользовательские настройки приложения.'''

    language: str = 'ru'
    country: str = 'ru'
    overlay_opacity: float = 0.9
    overlay_scale: int = 100
    show_fps: bool = True
    update_interval: int = 60
    launch_with_steam: bool = False
    currencies: tuple[str, ...] = ('RUB', 'USD', 'EUR')
    #: Внедрение цен в страницы магазина клиентa Steam (DevTools).
    integration_enabled: bool = True


def _clamp(value: float, low: float, high: float) -> float:
    '''Ограничивает число заданным диапазоном.'''
    return max(low, min(high, value))


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


def _as_int(value: Any, default: int) -> int:
    '''Приводит значение к целому числу, при неудаче берёт значение по умолчанию.'''
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _as_float(value: Any, default: float) -> float:
    '''Приводит значение к числу, при неудаче берёт значение по умолчанию.'''
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


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
    '''Приводит значение к списку строк; неподходящее значение даёт умолчание.'''
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
    return tuple(result) if result else default


def _from_mapping(data: dict) -> Settings:
    '''Собирает настройки из словаря, отбрасывая лишние и неверные значения.'''
    base = Settings()
    return Settings(
        language=_as_str(data.get('language'), base.language),
        country=_as_str(data.get('country'), base.country),
        overlay_opacity=_clamp(
            _as_float(data.get('overlay_opacity'), base.overlay_opacity), MIN_OPACITY, MAX_OPACITY),
        overlay_scale=int(_clamp(
            _as_int(data.get('overlay_scale'), base.overlay_scale), MIN_SCALE, MAX_SCALE)),
        show_fps=_as_bool(data.get('show_fps'), base.show_fps),
        update_interval=int(_clamp(
            _as_int(data.get('update_interval'), base.update_interval), MIN_INTERVAL, MAX_INTERVAL)),
        launch_with_steam=_as_bool(data.get('launch_with_steam'), base.launch_with_steam),
        currencies=_as_str_list(data.get('currencies'), base.currencies),
        integration_enabled=_as_bool(data.get('integration_enabled'), base.integration_enabled),
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
        'country': settings.country,
        'overlay_opacity': settings.overlay_opacity,
        'overlay_scale': settings.overlay_scale,
        'show_fps': settings.show_fps,
        'update_interval': settings.update_interval,
        'launch_with_steam': settings.launch_with_steam,
        'currencies': list(settings.currencies),
        'integration_enabled': settings.integration_enabled,
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return target


def apply_changes(settings: Settings, changes: dict) -> Settings:
    '''Применяет изменения к настройкам и проверяет значения.'''
    merged = {
        'language': settings.language,
        'country': settings.country,
        'overlay_opacity': settings.overlay_opacity,
        'overlay_scale': settings.overlay_scale,
        'show_fps': settings.show_fps,
        'update_interval': settings.update_interval,
        'launch_with_steam': settings.launch_with_steam,
        'currencies': list(settings.currencies),
        'integration_enabled': settings.integration_enabled,
    }
    merged.update(changes)
    return _from_mapping(merged)
