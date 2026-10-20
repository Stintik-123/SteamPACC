'''Тесты самопроверки: отчёт собирается и пишется на диск.'''

from __future__ import annotations

from pathlib import Path

from steampacc.selftest import collect_info, format_report, run_selftest


def test_collect_info_has_key_fields() -> None:
    '''Сведения о системе содержат основные поля.'''
    info = collect_info()
    assert 'os' in info
    assert 'python' in info
    assert 'qt_available' in info
    assert isinstance(info['qt_available'], bool)


def test_format_report_is_readable() -> None:
    '''Отчёт содержит понятные названия полей.'''
    text = format_report(collect_info())
    assert 'ОС:' in text
    assert 'Python:' in text


def test_run_selftest_writes_file(tmp_path: Path) -> None:
    '''Отчёт записывается в указанный файл.'''
    target = tmp_path / 'otchet.txt'
    result = run_selftest(target)
    assert result == target
    assert target.exists()
    assert target.read_text(encoding='utf-8').strip()


def test_run_selftest_never_raises(tmp_path: Path, monkeypatch: object) -> None:
    '''Ошибка записи не приводит к исключению.'''
    def broken(*args: object, **kwargs: object) -> None:
        '''Заглушка: имитирует недоступный диск.'''
        raise OSError('диск недоступен')

    monkeypatch.setattr(Path, 'write_text', broken)  # type: ignore[attr-defined]
    result = run_selftest(tmp_path / 'otchet.txt')
    assert isinstance(result, Path)
