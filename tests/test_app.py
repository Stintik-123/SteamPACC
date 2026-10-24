'''Проверки кэша цен и утилит приложения.'''

from __future__ import annotations

import time
from pathlib import Path

from steampacc.pricecache import (
    cached_price,
    load_cache,
    price_to_dict,
    save_cache,
    store_price,
)
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
