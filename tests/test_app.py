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
    watch_currencies,
)
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
    assert save_cache(path, {'ru': {'appid': 440}})
    assert load_cache(path) == {'ru': {'appid': 440}}


def test_load_cache_survives_broken_file(tmp_path: Path) -> None:
    '''Повреждённый кэш не ломает программу.'''
    path = tmp_path / 'prices.json'
    path.write_text('не json {{', encoding='utf-8')
    assert load_cache(path) == {}


def test_cached_price_returns_fresh_entry() -> None:
    '''Свежая запись кэша возвращает цену.'''
    price = _price()
    cache = {'ru': {'appid': 440, 'time': int(time.time()), 'price': price_to_dict(price)}}
    result = cached_price(cache, 440, 'ru')
    assert result is not None
    assert result.final == 12900
    assert result.discount_percent == 35


def test_cached_price_ignores_old_entry() -> None:
    '''Старая запись кэша не используется.'''
    price = _price()
    cache = {'ru': {'appid': 440, 'time': 0, 'price': price_to_dict(price)}}
    assert cached_price(cache, 440, 'ru') is None


def test_cached_price_ignores_other_appid() -> None:
    '''Запись другой игры не используется.'''
    price = _price()
    cache = {'ru': {'appid': 999, 'time': int(time.time()), 'price': price_to_dict(price)}}
    assert cached_price(cache, 440, 'ru') is None


def test_watch_currencies_uses_settings() -> None:
    '''Список валют берётся из настроек.'''
    assert watch_currencies(Settings(currencies=('USD', 'EUR'))) == ['USD', 'EUR']
