'''Проверки внедрения цен в магазин Steam.

Модули cef и inject зависят от сети и живого Steam, поэтому проверяются
чистые части: отбор страниц, форматирование команд и самодостаточность
внедряемого сценария.
'''

from __future__ import annotations

import re

from steampacc import cef
from steampacc.inject import INJECTED_SCRIPT, INJECTED_SETTINGS_SCRIPT


def test_settings_targets_finds_settings_window() -> None:
    '''Окно настроек Steam опознаётся по заголовку и служебному адресу.'''
    targets = [
        {'type': 'page', 'title': 'Настройки',
         'url': 'about:blank?createflags=4114', 'webSocketDebuggerUrl': 'ws://x'},
        {'type': 'page', 'title': 'Settings',
         'url': 'about:blank?createflags=4114', 'webSocketDebuggerUrl': 'ws://y'},
        {'type': 'page', 'title': 'Steam',
         'url': 'about:blank?createflags=274', 'webSocketDebuggerUrl': 'ws://z'},
        {'type': 'page', 'title': 'Настройки',
         'url': 'https://store.steampowered.com/', 'webSocketDebuggerUrl': 'ws://w'},
    ]
    result = cef.settings_targets(targets)
    assert len(result) == 2
    assert result[0]['webSocketDebuggerUrl'] == 'ws://x'


def test_settings_script_makes_panel_with_binding() -> None:
    '''Сценарий панели настроек рисует панель и передаёт выбор программе.'''
    assert 'SteamUIPopupWindowBody' in INJECTED_SETTINGS_SCRIPT
    assert 'steampacc_settings' in INJECTED_SETTINGS_SCRIPT
    assert 'SteamPACC_set' in INJECTED_SETTINGS_SCRIPT


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


def test_configure_expression_embeds_currencies() -> None:
    '''Команда настройки содержит список валют в формате JSON.'''
    expression = cef.configure_expression(['USD', 'EUR'])
    assert 'SteamPACC_configure' in expression
    assert '"currencies"' in expression
    assert 'USD' in expression and 'EUR' in expression


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


def test_unavailable_region_text() -> None:
    '''Для региона без цены пишется понятный текст вместо прочерка.'''
    assert '\\u041D\\u0435\\u0434\\u043E\\u0441\\u0442\\u0443\\u043F\\u043D\\u043E' in INJECTED_SCRIPT
    assert '__UNAVAILABLE__' not in INJECTED_SCRIPT


def test_best_price_highlight() -> None:
    '''Самая низкая цена помечается зелёным, как скидки в Steam.'''
    assert '#beee11' in INJECTED_SCRIPT
    assert 'isBest' in INJECTED_SCRIPT or 'best' in INJECTED_SCRIPT
