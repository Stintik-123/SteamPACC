'''Проверки модуля цен по регионам.'''

from __future__ import annotations

import pytest

from steampacc.prices import (
    CURRENCY_SYMBOLS,
    MINOR_UNITS,
    SUPPORTED_COUNTRIES,
    PriceError,
    format_amount,
    format_price,
    parse_price,
)

#: Ответ магазина Steam для игры со скидкой.
#: Значения - в минорных единицах, как их отдаёт Steam:
#: 12900 копеек - это 129 рублей.
PAID_RESPONSE: dict = {
    '440': {
        'success': True,
        'data': {
            'name': 'Team Fortress 2',
            'is_free': False,
            'price_overview': {
                'currency': 'RUB',
                'initial': 19900,
                'final': 12900,
                'discount_percent': 35,
                'initial_formatted': '199 руб.',
                'final_formatted': '129 руб.',
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


def _usd(final: int, initial: int | None = None) -> dict:
    '''Ответ магазина с ценой в долларах США.'''
    return {
        '440': {
            'success': True,
            'data': {
                'name': 'Test',
                'is_free': False,
                'price_overview': {
                    'currency': 'USD',
                    'initial': initial if initial is not None else final,
                    'final': final,
                    'discount_percent': 0,
                },
            },
        }
    }


def test_parse_price_reads_overview() -> None:
    '''Данные из price_overview попадают в объект Price.'''
    price = parse_price(440, 'ru', PAID_RESPONSE)
    assert price.currency == 'RUB'
    assert price.final == 12900
    assert price.initial == 19900
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


def test_format_amount_divides_minor_units() -> None:
    '''Минорные единицы делятся на сто: 999 - это 9,99.'''
    assert format_amount(999) == '9,99'
    assert format_amount(975) == '9,75'
    assert format_amount(100) == '1'
    assert format_amount(0) == '0'


def test_format_amount_drops_zero_kopecks() -> None:
    '''Целые суммы показываются без нулей после запятой.'''
    assert format_amount(38500) == '385'
    assert format_amount(12900) == '129'


def test_format_amount_splits_thousands() -> None:
    '''Большие суммы разделяются по разрядам.'''
    assert format_amount(539900) == '5' + chr(160) + '399'
    assert format_amount(1100000) == '11' + chr(160) + '000'


def test_minor_units_constant() -> None:
    '''В одной основной единице валюты сто минорных.'''
    assert MINOR_UNITS == 100


def test_format_price_plain() -> None:
    '''Обычная цена показывается со знаком валюты.'''
    price = parse_price(440, 'us', _usd(999))
    assert format_price(price) == '9,99 ' + chr(36)


def test_format_price_with_discount() -> None:
    '''Цена со скидкой показывается вместе с прежней ценой.'''
    price = parse_price(440, 'ru', PAID_RESPONSE)
    assert format_price(price) == '129 ' + chr(8381) + ' (было 199 ' + chr(8381) + ')'


def test_format_price_free() -> None:
    '''Бесплатная игра показывается словом.'''
    price = parse_price(440, 'ru', FREE_RESPONSE)
    assert format_price(price) == 'Бесплатно'


def test_format_price_without_value() -> None:
    '''Если цены нет, показывается понятный текст.'''
    price = parse_price(440, 'ru', NO_PRICE_RESPONSE)
    assert format_price(price) == 'Цена неизвестна'


def test_format_price_krw_uses_won_sign() -> None:
    '''У корейской воны свой знак, а не знак рубля.'''
    price = parse_price(
        440,
        'kr',
        {
            '440': {
                'success': True,
                'data': {
                    'name': 'Test',
                    'is_free': False,
                    'price_overview': {
                        'currency': 'KRW',
                        'initial': 1100000,
                        'final': 1100000,
                        'discount_percent': 0,
                    },
                },
            }
        },
    )
    assert CURRENCY_SYMBOLS['KRW'] == chr(8361)
    assert CURRENCY_SYMBOLS['KRW'] != CURRENCY_SYMBOLS['RUB']
    assert format_price(price) == '11' + chr(160) + '000 ' + chr(8361)


def test_currency_symbols_do_not_repeat() -> None:
    '''У каждой валюты свой знак: два разных кода не делят один знак.'''
    assert len(set(CURRENCY_SYMBOLS.values())) == len(CURRENCY_SYMBOLS)


def test_supported_countries_contains_base_regions() -> None:
    '''В списке стран есть Россия и США с русскими названиями.'''
    assert 'ru' in SUPPORTED_COUNTRIES
    assert 'us' in SUPPORTED_COUNTRIES
    assert SUPPORTED_COUNTRIES['ru'] == 'Россия'
    assert len(SUPPORTED_COUNTRIES) >= 15


def test_currency_symbols_have_ruble_sign() -> None:
    '''Для рубля задан знак рубля.'''
    assert CURRENCY_SYMBOLS['RUB'] == chr(8381)
