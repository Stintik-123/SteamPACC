'''Проверки слоя WinAPI: контракт функций и безопасное поведение вне Windows.'''

from __future__ import annotations

import sys

import pytest

from steampacc import win_api
from steampacc.win_api import WinApiError


def test_module_imports() -> None:
    '''Модуль импортируется на любой системе без ошибок.'''
    assert win_api is not None


def test_constants_values() -> None:
    '''Константы WinAPI имеют правильные значения.'''
    assert win_api.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
    assert win_api.GWL_EXSTYLE == -20
    assert win_api.GWL_STYLE == -16


def test_is_available_matches_platform() -> None:
    '''Доступность WinAPI совпадает с операционной системой.'''
    assert win_api.is_available() is sys.platform.startswith('win')


def test_safe_values_outside_windows() -> None:
    '''Вне Windows функции возвращают безопасные значения, а не падают.'''
    if win_api.is_available():
        return
    assert win_api.foreground_window() == 0
    assert win_api.find_window_by_class('SteamMainWindow') == 0
    assert win_api.set_dpi_awareness() is False


def test_bad_handle_raises() -> None:
    '''Неположительный дескриптор - понятная ошибка, а не падение.'''
    for bad in (0, -5):
        with pytest.raises(WinApiError):
            win_api.window_title(bad)
        with pytest.raises(WinApiError):
            win_api.window_rect(bad)
        with pytest.raises(WinApiError):
            win_api.window_class(bad)
        with pytest.raises(WinApiError):
            win_api.is_minimized(bad)
        with pytest.raises(WinApiError):
            win_api.is_window(bad)


def test_empty_class_name_raises() -> None:
    '''Пустое имя класса окна - понятная ошибка.'''
    with pytest.raises(WinApiError):
        win_api.find_window_by_class('')
