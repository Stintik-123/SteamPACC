'''Цены игр Steam по регионам.

Модуль получает сведения о цене игры через публичный API магазина Steam
и разбирает ответ в структуру Price. Запрос сети и разбор ответа
разделены, поэтому разбор проверяется без подключения к интернету.

Используется только стандартная библиотека Python.
'''

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

#: Базовый адрес публичного API магазина Steam.
API_URL = 'https://store.steampowered.com/api/appdetails'

#: Страны, для которых показываются цены: код -> название на русском.
SUPPORTED_COUNTRIES: dict[str, str] = {
    'ru': 'Россия',
    'us': 'США',
    'gb': 'Великобритания',
    'de': 'Германия',
    'fr': 'Франция',
    'ua': 'Украина',
    'kz': 'Казахстан',
    'by': 'Беларусь',
    'pl': 'Польша',
    'tr': 'Турция',
    'jp': 'Япония',
    'kr': 'Южная Корея',
    'cn': 'Китай',
    'br': 'Бразилия',
    'in': 'Индия',
    'au': 'Австралия',
    'ca': 'Канада',
    'it': 'Италия',
    'es': 'Испания',
    'nl': 'Нидерланды',
    'se': 'Швеция',
}

#: Знаки валют: код -> символ.
CURRENCY_SYMBOLS: dict[str, str] = {
    'RUB': chr(8381),
    'USD': chr(36),
    'EUR': chr(8364),
    'GBP': chr(163),
    'JPY': chr(165),
    'KRW': chr(8361),
    'INR': chr(8377),
    'TRY': chr(8378),
    'UAH': chr(8372),
    'KZT': chr(8376),
    'PLN': 'z' + chr(322),
    'BRL': 'R' + chr(36),
}


class PriceError(ValueError):
    '''Ошибка получения или разбора сведений о цене.'''


@dataclass(frozen=True)
class Price:
    '''Цена игры в одном регионе.'''

    appid: int
    country: str
    currency: str
    final: int | None
    initial: int | None
    discount_percent: int
    title: str | None
    is_free: bool


def _as_int(value: Any) -> int | None:
    '''Приводит значение к целому числу; неподходящее значение даёт None.'''
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def fetch_app_details(appid: int, country: str, timeout: float = 10.0) -> dict[str, Any]:
    '''Запрашивает сведения о приложении у магазина Steam.

    Возвращает словарь с разобранным JSON. При сетевой ошибке или
    нечитаемом ответе поднимается PriceError с понятным текстом.
    '''
    url = API_URL + '?cc=' + country + '&appids=' + str(appid)
    request = urllib.request.Request(url, headers={'User-Agent': 'SteamPACC/0.1'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        raise PriceError('Магазин Steam вернул ошибку HTTP ' + str(error.code)) from error
    except urllib.error.URLError as error:
        raise PriceError('Не удалось получить цену: ' + str(error.reason)) from error
    except OSError as error:
        raise PriceError('Ошибка сети при запросе цены: ' + str(error)) from error
    try:
        data = json.loads(payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PriceError('Ответ магазина Steam не является корректным JSON') from error
    if not isinstance(data, dict):
        raise PriceError('Ответ магазина Steam имеет неожиданный формат')
    return data


def parse_price(appid: int, country: str, payload: dict[str, Any]) -> Price:
    '''Разбирает ответ магазина Steam в объект Price.

    Сеть не используется: на вход подаётся уже полученный словарь.
    '''
    entry = payload.get(str(appid))
    if not isinstance(entry, dict):
        raise PriceError('В ответе магазина нет игры с appid ' + str(appid))
    if not entry.get('success', False):
        raise PriceError('Магазин Steam не вернул сведений об игре ' + str(appid))
    data = entry.get('data')
    if not isinstance(data, dict):
        raise PriceError('В ответе магазина нет раздела data для игры ' + str(appid))
    title = data.get('name')
    if title is not None and not isinstance(title, str):
        title = str(title)
    is_free = bool(data.get('is_free', False))
    overview = data.get('price_overview')
    if not isinstance(overview, dict) or not overview:
        if is_free:
            return Price(
                appid=appid,
                country=country,
                currency='',
                final=0,
                initial=None,
                discount_percent=0,
                title=title,
                is_free=True,
            )
        return Price(
            appid=appid,
            country=country,
            currency='',
            final=None,
            initial=None,
            discount_percent=0,
            title=title,
            is_free=False,
        )
    currency = overview.get('currency', '')
    currency = currency if isinstance(currency, str) else str(currency)
    final = _as_int(overview.get('final'))
    initial = _as_int(overview.get('initial'))
    discount = _as_int(overview.get('discount_percent')) or 0
    if final is None and is_free:
        final = 0
    return Price(
        appid=appid,
        country=country,
        currency=currency,
        final=final,
        initial=initial,
        discount_percent=discount,
        title=title,
        is_free=is_free,
    )


def fetch_price(appid: int, country: str, timeout: float = 10.0) -> Price:
    '''Получает и разбирает цену игры в одном регионе.'''
    payload = fetch_app_details(appid, country, timeout)
    return parse_price(appid, country, payload)


def format_price(price: Price) -> str:
    '''Готовит цену к показу пользователю.'''
    if price.is_free:
        return 'Бесплатно'
    if price.final is None:
        return 'Цена неизвестна'
    symbol = CURRENCY_SYMBOLS.get(price.currency, price.currency)
    text = str(price.final) + ' ' + symbol
    if price.initial is not None and price.discount_percent > 0 and price.initial > price.final:
        text = text + ' (было ' + str(price.initial) + ' ' + symbol + ')'
    return text
