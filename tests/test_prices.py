'''Проверки модуля цен по регионам.'''

from __future__ import annotations

import pytest

from steampacc.prices import (
    CURRENCY_SYMBOLS,
    SUPPORTED_COUNTRIES,
    PriceError,
    format_price,
    parse_price,
)

#: Ответ магазина Steam для игры со скидкой.
PAID_RESPONSE: dict = {
    '440': {
        'success': True,
        'data': {
            'name': 'Team Fortress 2',
            'is_free': False,
            'price_overview': {
                'currency': 'RUB',
                'initial': 199,
                'final': 129,
                'discount_percent': 35,
                'initial_formatted': '199 руб',
                'final_formatted': '129 руб',
            },
        },
    }
}

#: Ответ магазина Steam для бесплатной игры без блока с ценой.
FREE_RESPONSE: dict = {
    '440': {
        'success': True,
        'data': {'name': 'Team Fortress 2', 'is_free': True},
    }
}

#: Ответ магазина Steam для платной игры без блока с ценой.
NO_PRICE_RESPONSE: dict = {
    '440': {
        'success': True,
        'data': {'name': 'Half-Life', 'is_free': False},
    }
}


def test_parse_price_reads_overview() -> None:
    '''Данные из price_overview попадают в объект Price.'''
    price = parse_price(440, 'ru', PAID_RESPONSE)
    assert price.currency == 'RUB'
    assert price.final == 129
    assert price.initial == 199
    assert price.discount_percent == 35
    assert price.title == 'Team Fortress 2'
    assert price.is_free is False


def test_parse_price_free_game() -> None:
    '''У бесплатной игры итоговая цена равна нулю.'''
    price = parse_price(440, 'ru', FREE_RESPONSE)
    assert price.is_free is True
    assert price.final == 0
    assert price.currency == ''


def test_parse_price_without_price_overview() -> None:
    '''У платной игры без блока с ценой цена неизвестна.'''
    price = parse_price(440, 'ru', NO_PRICE_RESPONSE)
    assert price.final is None
    assert price.initial is None
    assert price.discount_percent == 0
    assert price.is_free is False


def test_parse_price_unknown_appid() -> None:
    '''Ответ без запрошенной игры приводит к ошибке.'''
    with pytest.raises(PriceError):
        parse_price(999, 'ru', PAID_RESPONSE)


def test_parse_price_failed_request() -> None:
    '''Ответ с success равным false приводит к ошибке.'''
    with pytest.raises(PriceError):
        parse_price(440, 'ru', {'440': {'success': False, 'data': {}}})


def test_format_price_plain() -> None:
    '''Обычная цена показывается со знаком валюты.'''
    price = parse_price(
        440,
        'us',
        {
            '440': {
                'success': True,
                'data': {
                    'name': 'Test',
                    'is_free': False,
                    'price_overview': {
                        'currency': 'USD',
                        'initial': 999,
                        'final': 999,
                        'discount_percent': 0,
                    },
                },
            }
        },
    )
    assert format_price(price) == '999 ' + chr(36)


def test_format_price_with_discount() -> None:
    '''Цена со скидкой показывается вместе с прежней ценой.'''
    price = parse_price(440, 'ru', PAID_RESPONSE)
    assert format_price(price) == '129 ' + chr(8381) + ' (было 199 ' + chr(8381) + ')'


def test_format_price_free() -> None:
    '''Бесплатная игра показывается словом.'''
    price = parse_price(440, 'ru', FREE_RESPONSE)
    assert format_price(price) == 'Бесплатно'


def test_supported_countries_contains_base_regions() -> None:
    '''В списке стран есть Россия и США с русскими названиями.'''
    assert 'ru' in SUPPORTED_COUNTRIES
    assert 'us' in SUPPORTED_COUNTRIES
    assert SUPPORTED_COUNTRIES['ru'] == 'Россия'
    assert len(SUPPORTED_COUNTRIES) >= 15


def test_currency_symbols_have_ruble_sign() -> None:
    '''Для рубля задан знак рубля.'''
    assert CURRENCY_SYMBOLS['RUB'] == chr(8381)
