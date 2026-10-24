'''Проверки логики приложения: автозапуск, валюты, страны.'''

from __future__ import annotations

from steampacc.app import (
    is_autostart_launch,
    watch_currencies,
)
from steampacc.config import Settings
from steampacc.prices import CURRENCY_COUNTRIES, CURRENCY_SYMBOLS


def test_autostart_launch_detected_by_flag() -> None:
    '''Флаг --autostart означает запуск из автозагрузки Windows.'''
    assert is_autostart_launch(['SteamPACC.exe', '--autostart']) is True
    assert is_autostart_launch(['SteamPACC.exe', '--AUTOSTART']) is True
    assert is_autostart_launch(['SteamPACC.exe']) is False
    assert is_autostart_launch([]) is False


def test_default_currencies_have_countries() -> None:
    '''У каждой валюты по умолчанию есть страна Steam.'''
    for code in watch_currencies(Settings()):
        assert code in CURRENCY_COUNTRIES


def test_every_currency_symbol_has_a_country() -> None:
    '''Для всех валют известна страна запроса цены.'''
    for code in CURRENCY_SYMBOLS:
        assert code in CURRENCY_COUNTRIES


def test_currency_countries_are_lowercase() -> None:
    '''Коды стран Steam пишутся строчными буквами.'''
    for country in CURRENCY_COUNTRIES.values():
        assert country == country.lower()


def test_watch_currencies_uses_settings() -> None:
    '''Список валют берётся из настроек.'''
    assert watch_currencies(Settings(currencies=('USD', 'EUR'))) == ['USD', 'EUR']
