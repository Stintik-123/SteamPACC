'''Установленные игры и библиотеки Steam.

Модуль читает файлы appmanifest_*.acf и libraryfolders.vdf из каталогов
библиотек Steam и собирает сведения об установленных играх. Файлы
открываются только для чтения, на диск модуль ничего не записывает.
'''

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .vdf import VdfError, parse_keyvalues

#: Обратный слэш; собирается через chr, чтобы не полагаться на escape.
BACKSLASH = chr(92)

#: Имя секции с состоянием игры в файле appmanifest_*.acf.
APP_STATE_SECTION = 'AppState'

#: Имя секции с перечнем библиотек в файле libraryfolders.vdf.
LIBRARY_FOLDERS_SECTION = 'libraryfolders'

#: Имя каталога с установленными играми внутри библиотеки.
COMMON_DIR = 'common'


@dataclass(frozen=True)
class InstalledGame:
    '''Сведения об одной установленной игре Steam.'''

    appid: int
    name: str
    install_dir: Path
    library_root: Path
    size_on_disk: int
    last_updated: int
    manifest_path: Path


def _first(value: Any) -> Any:
    '''Возвращает первое значение, если ключ повторился и стал списком.'''
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _pick(state: dict, *names: str) -> Any:
    '''Ищет значение по первому подходящему имени ключа.'''
    for name in names:
        if name in state:
            value = _first(state[name])
            if value is not None:
                return value
    return None


def _as_int(value: Any, default: int = 0) -> int:
    '''Приводит значение к целому числу, при неудаче берёт значение по умолчанию.'''
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_str(value: Any, default: str = '') -> str:
    '''Приводит значение к строке, при неудаче берёт значение по умолчанию.'''
    if value is None:
        return default
    return str(value)


def _section(parsed: dict, name: str) -> dict:
    '''Достаёт секцию верхнего уровня по имени, иначе первый вложенный словарь.'''
    value = parsed.get(name)
    if isinstance(value, dict):
        return value
    for item in parsed.values():
        if isinstance(item, dict):
            return item
    return parsed


def _normalize_path(raw: str) -> str:
    '''Убирает двойные обратные слеши, которыми Steam экранирует пути в VDF.'''
    double = BACKSLASH + BACKSLASH
    while double in raw:
        raw = raw.replace(double, BACKSLASH)
    return raw


def parse_appmanifest(text: str) -> dict:
    '''Разбирает текст appmanifest_*.acf и возвращает сведения об игре.

    Ключи результата: appid, name, installdir, size_on_disk, last_updated,
    buildid. При повреждённом файле возвращается пустой словарь.
    '''
    try:
        parsed = parse_keyvalues(text)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    state = _section(parsed, APP_STATE_SECTION)
    return {
        'appid': _as_int(_pick(state, 'appid')),
        'name': _as_str(_pick(state, 'name')),
        'installdir': _as_str(_pick(state, 'installdir')),
        'size_on_disk': _as_int(_pick(state, 'SizeOnDisk', 'size_on_disk')),
        'last_updated': _as_int(_pick(state, 'LastUpdated', 'last_updated')),
        'buildid': _as_int(_pick(state, 'buildid', 'BuildID')),
    }


def read_installed_games(library_root: Path) -> list[InstalledGame]:
    '''Собирает список установленных игр из каталога библиотеки.

    Битые и чужие файлы appmanifest_*.acf пропускаются молча, при
    отсутствии каталога steamapps возвращается пустой список.
    '''
    games: list[InstalledGame] = []
    steamapps = Path(library_root) / 'steamapps'
    if not steamapps.is_dir():
        return games
    for manifest in sorted(steamapps.glob('appmanifest_*.acf')):
        try:
            text = manifest.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        info = parse_appmanifest(text)
        if not info or not info['appid'] or not info['name']:
            continue
        games.append(InstalledGame(
            appid=info['appid'],
            name=info['name'],
            install_dir=steamapps / COMMON_DIR / info['installdir'],
            library_root=Path(library_root),
            size_on_disk=info['size_on_disk'],
            last_updated=info['last_updated'],
            manifest_path=manifest,
        ))
    games.sort(key=lambda game: (game.name.lower(), game.appid))
    return games


def read_library_folders(text: str) -> list[Path]:
    '''Достаёт пути библиотек из текста файла libraryfolders.vdf.'''
    try:
        parsed = parse_keyvalues(text)
    except Exception:
        return []
    if not isinstance(parsed, dict):
        return []
    section = _section(parsed, LIBRARY_FOLDERS_SECTION)
    result: list[Path] = []
    seen: set[str] = set()
    for item in section.values():
        if not isinstance(item, dict):
            continue
        raw = _first(item.get('path'))
        if not isinstance(raw, str) or not raw.strip():
            continue
        path = Path(_normalize_path(raw.strip()))
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def iter_library_games(roots: list[Path]) -> Iterator[InstalledGame]:
    '''Обходит корни библиотек и отдаёт все найденные установленные игры.'''
    seen: set[int] = set()
    for root in roots:
        for game in read_installed_games(Path(root)):
            key = game.appid
            if key in seen:
                continue
            seen.add(key)
            yield game
