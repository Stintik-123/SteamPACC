'''Проверки журнала работы и отчёта о состоянии.'''

from __future__ import annotations

import pytest

from steampacc import diagnostics


@pytest.fixture()
def data_dir(tmp_path, monkeypatch) -> None:
    '''Переносит каталог данных приложения во временную папку.'''
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))


def test_data_dir_ends_with_app_name() -> None:
    '''Каталог данных приложения называется SteamPACC.'''
    assert diagnostics.data_dir().name == 'SteamPACC'


def test_log_message_creates_file(data_dir: None) -> None:
    '''Запись в журнал создаёт файл и строку в нём.'''
    diagnostics.log_message('проверка записи')
    assert diagnostics.log_path().is_file()
    text = diagnostics.log_path().read_text(encoding='utf-8')
    assert 'проверка записи' in text


def test_read_log_returns_last_lines(data_dir: None) -> None:
    '''Журнал читается обратно: последняя строка - последняя запись.'''
    diagnostics.log_message('первая строка')
    diagnostics.log_message('вторая строка')
    lines = diagnostics.read_log()
    assert len(lines) == 2
    assert 'вторая строка' in lines[-1]


def test_log_exception_records_error(data_dir: None) -> None:
    '''Ошибка попадает в журнал вместе с описанием.'''
    try:
        raise RuntimeError('сбой при запуске')
    except RuntimeError:
        diagnostics.log_exception('Ошибка при запуске')
    text = diagnostics.log_path().read_text(encoding='utf-8')
    assert 'Ошибка при запуске' in text
    assert 'сбой при запуске' in text


def test_write_report_creates_file(data_dir: None) -> None:
    '''Отчёт сохраняется и содержит переданные сведения.'''
    path = diagnostics.write_report(['Игр найдено: 3'])
    assert path.is_file()
    text = path.read_text(encoding='utf-8')
    assert 'Игр найдено: 3' in text
    assert 'SteamPACC' in text


def test_system_info_has_lines() -> None:
    '''Сведения о системе - список строк.'''
    info = diagnostics.system_info()
    assert info
    assert all(isinstance(item, str) for item in info)


def test_show_error_does_not_raise() -> None:
    '''Показ сообщения не роняет программу даже без Qt.'''
    diagnostics.show_error('SteamPACC', 'проверка')
    diagnostics.show_message('SteamPACC', 'проверка')
