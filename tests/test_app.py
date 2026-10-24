'''Проверки графической части: расчёты оверлея и кэш цен.'''

from __future__ import annotations

import time
from pathlib import Path

from steampacc.app import (
    cached_price,
    format_price_lines,
    load_cache,
    overlay_position,
    panel_size,
    price_to_dict,
    save_cache,
    store_price,
    watch_currencies,
)
from steampacc.library import InstalledGame
from steampacc.config import Settings
from steampacc.prices import Price


def _price(appid: int = 440, country: str = 'ru') -> Price:
    '''Готовая цена для проверок.'''
    return Price(
        appid=appid,
        country=country,
        currency='RUB',
        final=12900,
        initial=19900,
        discount_percent=35,
        title='Test Game',
        is_free=False,
    )


def test_overlay_position_bottom_right() -> None:
    '''Панель прижимается к правому нижнему углу окна Steam.'''
    x, y = overlay_position((100, 100, 1100, 900), (200, 100))
    assert (x, y) == (1100 - 200 - 24, 900 - 100 - 24)


def test_overlay_position_gives_four_anchors() -> None:
    '''Четыре якоря дают четыре разных положения панели.'''
    rect = (0, 0, 1000, 1000)
    size = (200, 100)
    positions = {
        overlay_position(rect, size, anchor)
        for anchor in ('top_left', 'top_right', 'bottom_left', 'bottom_right')
    }
    assert len(positions) == 4


def test_overlay_position_rejects_unknown_anchor() -> None:
    '''Неизвестный якорь приводит к понятной ошибке.'''
    try:
        overlay_position((0, 0, 100, 100), (10, 10), 'center')
    except ValueError as error:
        assert 'якорь' in str(error)
    else:
        raise AssertionError('Ожидалась ошибка ValueError')


def test_panel_size_grows_with_text() -> None:
    '''Больше текста — больше панель.'''
    small = panel_size(['FPS'], 100)
    wide = panel_size(['Counter-Strike 2 — 129 USD — регион RU'], 100)
    tall = panel_size(['Dota 2', '129 USD', '60 FPS'], 100)
    assert wide[0] > small[0]
    assert tall[1] > small[1]


def test_panel_size_follows_scale() -> None:
    '''Масштаб увеличивает размер панели.'''
    assert panel_size(['строка'], 200)[0] > panel_size(['строка'], 100)[0]


def test_panel_size_rejects_bad_scale() -> None:
    '''Неположительный масштаб приводит к ошибке.'''
    try:
        panel_size(['строка'], 0)
    except ValueError:
        pass
    else:
        raise AssertionError('Ожидалась ошибка ValueError')


def test_format_price_lines_lists_prices() -> None:
    '''Строки панели содержат название игры и цену.'''
    lines = format_price_lines({'ru': _price()}, 'Test Game')
    assert lines[0] == 'Test Game'
    assert 'RUB' in lines[1]
    assert chr(8381) in lines[1]


def test_format_price_lines_without_data() -> None:
    '''Без цен панель показывает заглушку.'''
    assert format_price_lines({}) == ['Нет данных о ценах']


def test_cache_round_trip(tmp_path: Path) -> None:
    '''Кэш цен сохраняется и читается обратно.'''
    path = tmp_path / 'prices.json'
    data = {'440': {'RUB': {'appid': 440, 'time': 1}}}
    assert save_cache(path, data)
    assert load_cache(path) == data


def test_load_cache_survives_broken_file(tmp_path: Path) -> None:
    '''Повреждённый кэш не ломает программу.'''
    path = tmp_path / 'prices.json'
    path.write_text('не json {{', encoding='utf-8')
    assert load_cache(path) == {}


def test_load_cache_migrates_old_format(tmp_path: Path) -> None:
    '''Кэш старого формата (по валютам) переносится в новый (по играм).'''
    path = tmp_path / 'prices.json'
    path.write_text('{"ru": {"appid": 440, "time": 5, "price": {"appid": 440}}}', encoding='utf-8')
    assert load_cache(path) == {
        '440': {'ru': {'time': 5, 'price': {'appid': 440}}},
    }


def test_cached_price_returns_fresh_entry() -> None:
    '''Свежая запись кэша возвращает цену.'''
    price = _price()
    cache = {'440': {'RUB': {'time': int(time.time()), 'price': price_to_dict(price)}}}
    result = cached_price(cache, 440, 'RUB')
    assert result is not None
    assert result.final == 12900
    assert result.discount_percent == 35


def test_cached_price_ignores_old_entry() -> None:
    '''Старая запись кэша не используется.'''
    price = _price()
    cache = {'440': {'RUB': {'time': 0, 'price': price_to_dict(price)}}}
    assert cached_price(cache, 440, 'RUB') is None


def test_cached_price_ignores_other_appid() -> None:
    '''Запись другой игры не используется: ключ кэша — appid.'''
    price = _price()
    cache = {'999': {'RUB': {'time': int(time.time()), 'price': price_to_dict(price)}}}
    assert cached_price(cache, 440, 'RUB') is None


def test_store_price_keeps_games_apart() -> None:
    '''Цены двух игр в одной валюте не затирают друг друга.'''
    cache: dict = {}
    store_price(cache, 440, 'RUB', _price(440))
    store_price(cache, 570, 'RUB', _price(570))
    assert cached_price(cache, 440, 'RUB') is not None
    assert cached_price(cache, 570, 'RUB') is not None


def test_build_exe_map_matches_executables(tmp_path: Path) -> None:
    '''Имена исполняемых файлов игр сопоставляются с appid.'''
    from steampacc.app import build_exe_map

    folder_a = tmp_path / 'game_a'
    folder_b = tmp_path / 'game_b'
    (folder_a / 'steamapps' / 'common').mkdir(parents=True)
    folder_b.mkdir()
    (folder_a / 'steamapps' / 'common' / 'GameA.exe').write_text('a')
    (folder_b / 'launcher.exe').write_text('b')

    def make(appid: int, install_dir: Path) -> InstalledGame:
        return InstalledGame(
            appid=appid,
            name='Игра ' + str(appid),
            install_dir=install_dir,
            library_root=tmp_path,
            size_on_disk=0,
            last_updated=0,
            manifest_path=tmp_path / 'manifest.acf',
        )

    games = [
        make(440, folder_a / 'steamapps' / 'common' / 'GameA'),
        make(570, folder_b),
    ]
    # Каталог первой игры не существует: её exe не попадает в карту.
    result = build_exe_map(games)
    assert result == {'launcher.exe': 570}


def test_game_by_title_picks_longest_match() -> None:
    '''Из нескольких совпадений выбирается самое длинное имя игры.'''
    from steampacc.app import game_by_title

    names = {'dota': 1, 'dota 2': 2, 'team fortress': 3}
    assert game_by_title('Dota 2 - Main Menu', names) == 2
    assert game_by_title('Team Fortress Classics', names) == 3


def test_game_by_title_skips_short_names() -> None:
    '''Короткие имена не дают ложных срабатываний.'''
    from steampacc.app import game_by_title

    assert game_by_title('Подготовка Windows', {'go': 1, ' Windows': 2}) is None


def test_is_steam_window_by_sdl_title() -> None:
    '''Окно SDL_app с заголовком Steam — это клиент Steam.'''
    from steampacc.app import is_steam_window

    assert is_steam_window('SDL_app', 'Steam') is True
    assert is_steam_window('sdl_app', 'steam ') is True


def test_is_steam_window_rejects_sdl_game() -> None:
    '''Окно SDL_app без заголовка Steam и без hwnd — не Steam.'''
    from steampacc.app import is_steam_window

    assert is_steam_window('SDL_app', 'SuperTuxKart') is False
    assert is_steam_window('SDL_app', '') is False


def test_is_steam_window_by_known_classes() -> None:
    '''Классы старого клиента распознаются без учёта регистра.'''
    from steampacc.app import is_steam_window

    assert is_steam_window('SteamMainWindow', '') is True
    assert is_steam_window('vguiPopupWindow', '') is True
    assert is_steam_window('Notepad', 'Steam') is False
    assert is_steam_window('', '') is False


def test_watch_currencies_uses_settings() -> None:
    '''Список валют берётся из настроек.'''
    assert watch_currencies(Settings(currencies=('USD', 'EUR'))) == ['USD', 'EUR']
