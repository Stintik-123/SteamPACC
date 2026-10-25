'''Проверки внедрения цен в магазин Steam.

Модули cef и inject зависят от сети и живого Steam, поэтому проверяются
чистые части: отбор страниц, форматирование команд и самодостаточность
внедряемого сценария.
'''

from __future__ import annotations

import re

from steampacc import cef
from steampacc.inject import INJECTED_SCRIPT


def _target(url: str, type_name: str = 'page', title: str = 'Магазин') -> dict:
    '''Готовая цель DevTools для проверок.'''
    return {
        'type': type_name,
        'title': title,
        'url': url,
        'webSocketDebuggerUrl': 'ws://127.0.0.1:8080/devtools/page/1',
    }


def test_store_targets_keeps_store_pages() -> None:
    '''Отбираются только страницы магазина Steam.'''
    targets = [
        _target('https://store.steampowered.com/app/570/'),
        _target('about:blank?createflags=1', title='Library Supernav'),
        _target('https://steamcommunity.com/chat', title='Чат'),
        _target('http://store.steampowered.com/news/', title='Новости'),
    ]
    result = cef.store_targets(targets)
    assert len(result) == 2
    assert '/app/570' in result[0]['url']


def test_store_targets_ignores_non_pages() -> None:
    '''Служебные цели DevTools (не page) пропускаются.'''
    targets = [_target('https://store.steampowered.com/app/570/', type_name='service_worker')]
    assert cef.store_targets(targets) == []


def test_configure_expression_embeds_currencies_and_lang() -> None:
    '''Команда настройки содержит валюты и язык.'''
    expression = cef.configure_expression(['USD', 'EUR'], 'en')
    assert 'SteamPACC_configure' in expression
    assert 'USD' in expression and 'EUR' in expression
    assert '"lang": "en"' in expression


def test_version_is_steam_detects_agent() -> None:
    '''Порт опознаётся как Steam по User-Agent.'''
    assert cef.version_is_steam({'User-Agent': 'Mozilla ... Valve Steam Client'})
    assert cef.version_is_steam({'Browser': 'Chrome/126 Steam'})
    assert not cef.version_is_steam({'User-Agent': 'Mozilla Chrome/120'})
    assert not cef.version_is_steam({})


def test_injected_script_finds_appid_by_url() -> None:
    '''Сценарий вычисляет appid из адреса страницы магазина.'''
    assert "location.href.match(/\\/app\\/(\\d+)/)" in INJECTED_SCRIPT
    assert '/api/appdetails?appids=' in INJECTED_SCRIPT


def test_injected_script_has_no_leftover_placeholders() -> None:
    '''Все плейсхолдеры стилей заменены при сборке сценария.'''
    leftovers = re.findall(r'__[A-Z][A-Z_]+__', INJECTED_SCRIPT)
    leftovers = [name for name in leftovers if name != '__STEAMPACC_ACTIVE__']
    assert leftovers == []


def test_injected_script_runs_once() -> None:
    '''Повторное добавление сценария защищено флагом.'''
    assert '__STEAMPACC_ACTIVE__' in INJECTED_SCRIPT


def test_injected_script_marks_box_and_uses_cache() -> None:
    '''Сценарий рисует блок с известным идентификатором и кэширует ответы.'''
    assert 'steampacc_prices' in INJECTED_SCRIPT
    assert 'sessionStorage' in INJECTED_SCRIPT
    assert 'price_overview' in INJECTED_SCRIPT


def test_injected_script_uses_observer_not_polling() -> None:
    '''Изменения страницы отслеживает MutationObserver, а не опрос каждую секунду.'''
    assert 'MutationObserver' in INJECTED_SCRIPT
    assert 'setInterval(update, 1000)' not in INJECTED_SCRIPT


def test_injected_script_has_memory_cache_fallback() -> None:
    '''При переполнении sessionStorage цены кэшируются в памяти.'''
    assert 'var mem = {}' in INJECTED_SCRIPT


def test_injected_script_is_bilingual() -> None:
    '''Надписи блока есть на двух языках и переключаются настройкой.'''
    assert 'TEXT.ru' in INJECTED_SCRIPT or "'ru':" in INJECTED_SCRIPT
    assert 'en: {' in INJECTED_SCRIPT
    assert "next.lang === 'ru' || next.lang === 'en'" in INJECTED_SCRIPT


def test_unavailable_region_text_capitalized() -> None:
    '''Для региона без цены пишется понятный текст с заглавной буквы.'''
    assert '\\u041D\\u0435\\u0434\\u043E\\u0441\\u0442\\u0443\\u043F\\u043D\\u043E' in INJECTED_SCRIPT
