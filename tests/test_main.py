'''Тесты точки входа: служебные ключи запуска и защита от тихой ошибки.'''

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from steampacc import __main__ as entry
from steampacc import app
from steampacc import diagnostics


def test_flags_are_declared() -> None:
    '''Служебные ключи запуска объявлены в модуле.'''
    assert entry.VERSION_FLAG == '--version'
    assert entry.SELFTEST_FLAG == '--selftest'
    assert entry.SMOKE_FLAG == '--smoke'


def test_version_key_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    '''Ключ --version печатает версию и завершает работу без ошибки.'''
    code = entry.main(['--version'])
    captured = capsys.readouterr()
    assert code == 0
    assert 'SteamPACC' in captured.out


def test_log_start_writes_to_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    '''Старт программы записывается в журнал: видно, что она вообще запустилась.'''
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    entry._log_start()
    log = tmp_path / 'SteamPACC' / 'steampacc.log'
    assert log.exists()
    assert 'Старт SteamPACC' in log.read_text(encoding='utf-8')


def test_critical_error_is_shown_to_user(monkeypatch: pytest.MonkeyPatch) -> None:
    '''Критическая ошибка показывается пользователю, а не теряется в stderr.'''
    shown: list[str] = []

    def broken_version() -> int:
        '''Заглушка: имитирует падение при загрузке модуля.'''
        raise ImportError('нет модуля')

    def fake_show(text: str) -> None:
        '''Запоминает показанный текст ошибки.'''
        shown.append(text)

    monkeypatch.setattr(entry, '_run_version', broken_version)
    monkeypatch.setattr(entry, '_show_fatal', fake_show)
    code = entry.main(['--version'])
    assert code == 1
    assert shown
    assert 'нет модуля' in shown[0]


def test_first_launch_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    '''Первый запуск отмечается меткой, второй раз метка уже есть.'''
    monkeypatch.setattr(diagnostics, 'data_dir', lambda: tmp_path)
    assert app.is_first_launch() is True
    assert app.is_first_launch() is False


def test_claim_single_instance_outside_windows() -> None:
    '''Вне Windows проверка не блокирует работу программы.'''
    if sys.platform.startswith('win'):
        pytest.skip('проверка для систем без Windows')
    assert app.claim_single_instance() is True


def test_smoke_test_reports_missing_qt(monkeypatch: pytest.MonkeyPatch) -> None:
    '''Без PySide6 проверка графики честно возвращает ошибку, а не молчит.'''
    monkeypatch.setattr(app, 'QT_AVAILABLE', False)
    assert app.smoke_test() == 1


def test_autostart_flags_are_declared() -> None:
    '''Ключи управления автозапуском объявлены в модуле.'''
    assert entry.ENABLE_AUTOSTART_FLAG == '--enable-autostart'
    assert entry.DISABLE_AUTOSTART_FLAG == '--disable-autostart'


def test_autostart_flags_in_help() -> None:
    '''Справка по командной строке содержит ключи автозапуска.'''
    assert entry.ENABLE_AUTOSTART_FLAG in entry.HELP_TEXT
    assert entry.DISABLE_AUTOSTART_FLAG in entry.HELP_TEXT


def test_autostart_routes_to_setter(monkeypatch: pytest.MonkeyPatch) -> None:
    '''Ключи автозапуска доходят до функции изменения состояния.'''
    calls: list[bool] = []

    def fake_set(enable: bool) -> int:
        '''Запоминает, с каким флагом вызвали функцию.'''
        calls.append(enable)
        return 0

    monkeypatch.setattr(entry, '_set_autostart', fake_set)
    assert entry.main(['--enable-autostart']) == 0
    assert entry.main(['--disable-autostart']) == 0
    assert calls == [True, False]


def test_set_autostart_outside_windows(
    capsys: pytest.CaptureFixture[str],
) -> None:
    '''Вне Windows автозапуск честно сообщает о недоступности.'''
    from steampacc import win_api

    if win_api.is_available():
        pytest.skip('проверка для систем без Windows')
    code = entry._set_autostart(True)
    captured = capsys.readouterr()
    assert code == 1
    assert 'Windows' in captured.out


def test_set_autostart_inside_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    '''Под Windows функция просит win_api записать и стереть запись реестра.'''
    from steampacc import win_api

    calls: list[tuple[str, bool]] = []

    def fake_register(executable: str, enable: bool = True) -> bool:
        '''Запоминает вызовы записи автозапуска.'''
        calls.append((executable, enable))
        return True

    monkeypatch.setattr(win_api, 'is_available', lambda: True)
    monkeypatch.setattr(win_api, 'register_autostart', fake_register)
    assert entry._set_autostart(True) == 0
    assert entry._set_autostart(False) == 0
    assert len(calls) == 2
    assert calls[0][1] is True
    assert calls[1][1] is False


def test_set_autostart_reports_registry_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    '''Если реестр не принял запись, программа возвращает ошибку.'''
    from steampacc import win_api

    monkeypatch.setattr(win_api, 'is_available', lambda: True)
    monkeypatch.setattr(win_api, 'register_autostart', lambda exe, enable=True: False)
    assert entry._set_autostart(True) == 1
