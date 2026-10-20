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
