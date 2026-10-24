'''Подключение к интерфейсу клиента Steam по протоколу DevTools.

Современный клиент Steam рисует интерфейс через встроенный Chromium
(процесс steamwebhelper). Если Steam запущен с флагом
``-cef-enable-debugging``, steamwebhelper открывает отладочный порт
(по умолчанию 8080), и по нему можно подключиться к страницам клиента
и внедрить свой код — без изменения файлов Steam и без DLL-инъекций.

Модуль отвечает за поиск порта, перечисление страниц (целей) и работу
по WebSocket. Логика внедрения — в модуле :mod:`steampacc.inject`.
'''

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .inject import INJECTED_SCRIPT

#: Порт отладки steamwebhelper по умолчанию (флаг -cef-enable-debugging).
DEFAULT_DEBUG_PORT = 8080

#: Префиксы адресов страниц магазина Steam, в которые внедряемся.
STORE_URL_PREFIXES = ('https://store.steampowered.com', 'http://store.steampowered.com')


def http_base(port: int) -> str:
    '''Базовый адрес отладочного интерфейса.'''
    return 'http://127.0.0.1:' + str(int(port))


def debug_available(port: int = DEFAULT_DEBUG_PORT, timeout: float = 1.0) -> bool:
    '''True, если Steam запущен с отладочным портом и отвечает.'''
    try:
        request = urllib.request.Request(
            http_base(port) + '/json/version', headers={'User-Agent': 'SteamPACC/0.3'})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def fetch_targets(port: int = DEFAULT_DEBUG_PORT, timeout: float = 1.0) -> list[dict[str, Any]]:
    '''Возвращает список страниц клиента Steam (целей DevTools).

    Поднимает OSError, если Steam не запущен с отладочным портом.
    '''
    request = urllib.request.Request(
        http_base(port) + '/json/list', headers={'User-Agent': 'SteamPACC/0.3'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    data = json.loads(payload.decode('utf-8'))
    if not isinstance(data, list):
        raise OSError('Неожиданный формат ответа DevTools: ' + str(type(data)))
    return data


def store_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    '''Отбирает страницы магазина Steam из списка целей.

    Внутренние окна клиента (меню, уведомления) работают с адресом
    about:blank — их пропускаем, внедряемся только в страницы магазина.
    '''
    result: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        if target.get('type') != 'page':
            continue
        url = target.get('url') or ''
        if not isinstance(url, str):
            continue
        if url.startswith(STORE_URL_PREFIXES):
            result.append(target)
    return result


def settings_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    '''Отбирает окно настроек клиента Steam из списка целей.

    Окно настроек открывается как отдельное всплывающее окно с
    заголовком «Настройки» (или «Settings» в английской версии) и
    служебным адресом about:blank.
    '''
    result: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        if target.get('type') != 'page':
            continue
        if (target.get('title') or '') not in ('Настройки', 'Settings'):
            continue
        url = target.get('url') or ''
        if 'about:blank' in url:
            result.append(target)
    return result


def configure_expression(currencies: list[str]) -> str:
    '''Готовит выражение, передающее список валют в внедрённый код.'''
    payload = json.dumps({'currencies': currencies}, ensure_ascii=False)
    return 'window.SteamPACC_configure && window.SteamPACC_configure(' + payload + '); void 0;'


def settings_configure_expression(currencies: list[str]) -> str:
    '''Готовит выражение настройки панели в окне настроек Steam.'''
    payload = json.dumps({'currencies': currencies}, ensure_ascii=False)
    return ('window.SteamPACC_settings_configure && '
            'window.SteamPACC_settings_configure(' + payload + '); void 0;')


if __name__ == '__main__':  # pragma: no cover
    print('debug:', debug_available())
    for item in store_targets(fetch_targets()):
        print(item.get('title'), '|', item.get('url'))
