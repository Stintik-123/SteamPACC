'''Консольные команды SteamPACC: игры и цены без графики.

Команды удобны, когда интерфейс не нужен или графика недоступна:

    python -m steampacc games              — список установленных игр;
    python -m steampacc price 570          — цены игры по appid;
    python -m steampacc price "Dota 2"     — цены игры по имени.

Команды не открывают окон, печатают текст в консоль и работают на
любой системе. Цены берутся из кэша, а при отсутствии в кэше — из
интернета, после чего кэш пополняется.
'''

from __future__ import annotations

import sys
from typing import Sequence

from .pricecache import cached_price, cache_path, load_cache, save_cache, store_price
from .config import load_settings
from .diagnostics import safe_print
from .library import InstalledGame, iter_library_games, read_library_folders
from .prices import (
    CURRENCY_COUNTRIES,
    PriceError,
    fetch_price,
    format_price,
)
from .steam_paths import find_steam_root, steam_paths

#: Во сколько раз байт больше гигабайта (приблизительно, как в Steam).
GIGABYTE = 1024 * 1024 * 1024


def list_library() -> list[InstalledGame]:
    '''Собирает список установленных игр по всем каталогам библиотек.'''
    root = find_steam_root()
    if root is None:
        return []
    roots: list[object] = [root]
    try:
        folders_file = steam_paths(root).libraryfolders_vdf
        text = folders_file.read_text(encoding='utf-8', errors='ignore')
        roots.extend(read_library_folders(text))
    except OSError:
        pass
    unique: list[object] = []
    for item in roots:
        if item not in unique:
            unique.append(item)
    return list(iter_library_games(unique))  # type: ignore[arg-type]


def resolve_game(query: str, games: Sequence[InstalledGame]) -> InstalledGame | None:
    '''Находит игру по числовому appid или по подстроке имени.'''
    text = query.strip()
    if not text:
        return None
    if text.isdigit():
        for game in games:
            if game.appid == int(text):
                return game
        return None
    needle = text.lower()
    matches = [game for game in games if needle in game.name.lower()]
    if not matches:
        return None
    # Точное совпадение имени ценнее частичного.
    for game in matches:
        if game.name.lower() == needle:
            return game
    return matches[0]


def _size_text(size_on_disk: int) -> str:
    '''Переводит размер в гигабайты: 7308388352 -> "6,81 ГБ".'''
    value = size_on_disk / GIGABYTE
    if value < 0.01:
        return '-'
    return ('{:.2f}'.format(value)).replace('.', ',') + ' ГБ'


def print_games(games: Sequence[InstalledGame]) -> int:
    '''Печатает список игр в консоль и возвращает код выхода.'''
    if not games:
        safe_print('Установленные игры не найдены. Steam установлен?')
        return 1
    safe_print('Установленных игр: ' + str(len(games)))
    for game in games:
        line = str(game.appid).rjust(7) + '  ' + game.name
        size = _size_text(game.size_on_disk)
        if size != '-':
            line = line + '  (' + size + ')'
        safe_print(line)
    return 0


def print_prices(game: InstalledGame) -> int:
    '''Печатает цены игры во всех валютах из настроек.'''
    settings = load_settings()
    currencies = [code.upper() for code in settings.currencies if code] or ['RUB', 'USD', 'EUR']
    cache_file = cache_path()
    cache = load_cache(cache_file)

    safe_print(game.name + ' (appid ' + str(game.appid) + ')')
    failures: list[str] = []
    for code in currencies:
        price = cached_price(cache, game.appid, code)
        if price is None:
            country = CURRENCY_COUNTRIES.get(code, code.lower())
            try:
                price = fetch_price(game.appid, country)
            except PriceError as error:
                failures.append(code + ': ' + str(error))
                continue
            store_price(cache, game.appid, code, price)
            save_cache(cache_file, cache)
        safe_print('  ' + code + ': ' + format_price(price))
    for line in failures:
        safe_print('  ' + line, sys.stderr)
    return 0 if not failures else 1


def main(args: Sequence[str]) -> int:
    '''Запускает консольную команду и возвращает код выхода.

    args — аргументы после имени программы: первое слово задаёт команду
    (games или price), остальное передаётся ей.
    '''
    items = [str(item) for item in args]
    if not items or items[0] in ('help', '--help', '-h'):
        safe_print('Консольные команды SteamPACC:')
        safe_print('  steampacc games            список установленных игр')
        safe_print('  steampacc price <appid|имя> цены игры в разных валютах')
        return 0

    command, rest = items[0], items[1:]
    if command == 'games':
        return print_games(list_library())

    if command == 'price':
        if not rest:
            safe_print('Укажите игру: appid или часть имени.', sys.stderr)
            safe_print('Пример: steampacc price 570', sys.stderr)
            return 2
        games = list_library()
        if not games and not rest[0].isdigit():
            safe_print('Библиотека Steam не найдена, но можно указать appid напрямую.', sys.stderr)
            return 1
        game = resolve_game(' '.join(rest), games)
        if game is None:
            if rest[0].isdigit():
                from .library import InstalledGame
                from pathlib import Path
                game = InstalledGame(
                    appid=int(rest[0]),
                    name='Игра ' + rest[0],
                    install_dir=Path(),
                    library_root=Path(),
                    size_on_disk=0,
                    last_updated=0,
                    manifest_path=Path(),
                )
            else:
                safe_print('Игра не найдена: ' + ' '.join(rest), sys.stderr)
                return 1
        return print_prices(game)

    safe_print('Неизвестная команда: ' + command, sys.stderr)
    safe_print('Доступны: games, price. Справка: steampacc help', sys.stderr)
    return 2
