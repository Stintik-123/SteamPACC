'''Проверки модуля автозапуска.

На системах без Windows функции безопасно возвращают False; сами
проверки записи в реестр выполняются только под Windows.
'''

from __future__ import annotations

import sys

from steampacc import autostart


def test_command_contains_flag() -> None:
    '''Команда автозапуска содержит ключ --autostart.'''
    assert '--autostart' in autostart._command()


def test_frozen_launch_points_to_executable() -> None:
    '''В собранной версии автозапуск указывает на исполняемый файл.'''

    class FakeFrozen:
        pass

    original = sys.executable
    try:
        sys.frozen = True  # type: ignore[attr-defined]
        command = autostart._command()
        assert original in command
        assert command.startswith('"')
    finally:
        del sys.frozen  # type: ignore[attr-defined]


def test_disabled_outside_windows(monkeypatch) -> None:
    '''Вне Windows включение и выключение не падают и возвращают False.'''
    if sys.platform == 'win32':
        return
    assert autostart.set_enabled(True) is False
    assert autostart.is_enabled() is False


def test_registry_round_trip() -> None:
    '''Под Windows запись реально появляется и убирается из реестра.'''
    if not sys.platform == 'win32':
        return
    import winreg

    original = None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, autostart.RUN_KEY
        ) as key:
            original, _ = winreg.QueryValueEx(key, autostart.VALUE_NAME)
    except OSError:
        pass

    try:
        assert autostart.set_enabled(True) is True
        assert autostart.is_enabled() is True
        assert autostart.set_enabled(False) is True
        assert autostart.is_enabled() is False
    finally:
        # Возвращаем то, что было у пользователя до проверки.
        if original is not None:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, autostart.RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, autostart.VALUE_NAME, 0, winreg.REG_SZ, original)
