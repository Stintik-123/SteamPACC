'''Дисковый кэш цен игр.

Кэш хранится по играм: {appid: {валюта: {time, price}}}. Используется
консольными командами (steampacc price), чтобы повторные запросы не
били в API Steam, и живёт в каталоге данных приложения.
'''

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .diagnostics import data_dir
from .prices import Price

#: Имя файла кэша цен.
CACHE_FILE_NAME = 'prices.json'

#: Жизнь записи кэша, секунд (15 минут).
CACHE_TTL = 900

#: Сколько игр хранится в кэше; старые вытесняются.
CACHE_MAX_GAMES = 256


def cache_path() -> Path:
    '''Путь к файлу кэша цен в каталоге данных приложения.'''
    return data_dir() / CACHE_FILE_NAME


def load_cache(path: Path) -> dict[str, Any]:
    '''Читает кэш цен; повреждённый или старый файл не ломает программу.

    Записи старого формата (по валютам, одна игра на файл) переносятся
    в новый.
    '''
    try:
        if not path.exists():
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        if str(key).isdigit():
            result[str(key)] = value
            continue
        # Старый формат: ключ — валюта, внутри одна запись с appid.
        appid = value.get('appid')
        record = value.get('price')
        if isinstance(appid, int) and isinstance(record, dict):
            bucket = result.setdefault(str(appid), {})
            if isinstance(bucket, dict) and key not in bucket:
                bucket[key] = {'time': value.get('time'), 'price': record}
    return result


def save_cache(path: Path, data: dict[str, Any]) -> bool:
    '''Сохраняет кэш цен в файл; ошибка записи не прерывает работу.'''
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        return True
    except OSError:
        return False


def price_to_dict(price: Price) -> dict[str, Any]:
    '''Сводит цену к словарю для хранения.'''
    return {
        'appid': price.appid,
        'currency': price.currency,
        'final': price.final,
        'initial': price.initial,
        'discount_percent': price.discount_percent,
        'title': price.title,
        'is_free': price.is_free,
    }


def cached_price(cache: dict[str, Any], appid: int, currency: str, ttl: int = CACHE_TTL) -> Price | None:
    '''Возвращает цену из кэша, если запись свежая и относится к той же игре.'''
    bucket = cache.get(str(appid))
    if not isinstance(bucket, dict):
        return None
    entry = bucket.get(currency)
    if not isinstance(entry, dict):
        return None

    stamp = entry.get('time')
    if not isinstance(stamp, int) or int(time.time()) - stamp > ttl:
        return None

    data = entry.get('price')
    if not isinstance(data, dict):
        return None

    try:
        return Price(
            appid=int(data.get('appid', appid)),
            country=currency.lower(),
            currency=str(data.get('currency', '')),
            final=data.get('final') if isinstance(data.get('final'), int) else None,
            initial=data.get('initial') if isinstance(data.get('initial'), int) else None,
            discount_percent=int(data.get('discount_percent', 0)),
            title=data.get('title') if isinstance(data.get('title'), str) else None,
            is_free=bool(data.get('is_free', False)),
        )
    except (TypeError, ValueError):
        return None


def store_price(cache: dict[str, Any], appid: int, currency: str, price: Price) -> None:
    '''Кладёт цену в кэш; размер кэша ограничен, старые игры вытесняются.'''
    bucket = cache.setdefault(str(appid), {})
    if not isinstance(bucket, dict):
        bucket = {}
        cache[str(appid)] = bucket
    bucket[currency] = {
        'time': int(time.time()),
        'price': price_to_dict(price),
    }
    if len(cache) > CACHE_MAX_GAMES:
        oldest = min(
            (key for key in cache if str(key).isdigit()),
            key=lambda key: max(
                (item.get('time', 0) for item in cache[key].values()
                 if isinstance(item, dict)),
                default=0,
            ),
        )
        cache.pop(oldest, None)
