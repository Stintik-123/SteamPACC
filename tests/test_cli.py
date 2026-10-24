'''Проверки консольных команд SteamPACC.

Консольный режим не зависит от графики: разбор аргументов и поиск игры
проверяются без сети, без Steam и без окон.
'''

from __future__ import annotations

from pathlib import Path

from steampacc.cli import main, resolve_game, _size_text
from steampacc.library import InstalledGame


def _game(appid: int, name: str) -> InstalledGame:
    '''Готовая игра для проверок.'''
    return InstalledGame(
        appid=appid,
        name=name,
        install_dir=Path(),
        library_root=Path(),
        size_on_disk=0,
        last_updated=0,
        manifest_path=Path(),
    )


GAMES = [
    _game(570, 'Dota 2'),
    _game(440, 'Team Fortress 2'),
    _game(730, 'Counter-Strike 2'),
]


def test_resolve_game_by_appid() -> None:
    '''Игра находится по числовому appid.'''
    assert resolve_game('570', GAMES) is GAMES[0]
    assert resolve_game(' 440 ', GAMES) is GAMES[1]


def test_resolve_game_by_name() -> None:
    '''Игра находится по подстроке имени без учёта регистра.'''
    assert resolve_game('dota', GAMES) is GAMES[0]
    assert resolve_game('Counter-strike', GAMES) is GAMES[2]


def test_resolve_game_prefers_exact_name() -> None:
    '''Точное совпадение имени ценнее частичного.'''
    games = [_game(1, 'Dota 2 mods'), _game(2, 'Dota 2')]
    assert resolve_game('dota 2', games) is games[1]


def test_resolve_game_unknown() -> None:
    '''Несуществующая игра не находится.'''
    assert resolve_game('нет такой', GAMES) is None
    assert resolve_game('', GAMES) is None
    assert resolve_game('999', GAMES) is None


def test_size_text_formats_gigabytes() -> None:
    '''Размер игры печатается в гигабайтах с запятой.'''
    assert _size_text(0) == '-'
    assert _size_text(7_308_388_352) == '6,81 ГБ'


def test_help_prints_usage(capsys) -> None:
    '''Без аргументов печатается справка.'''
    assert main([]) == 0
    text = capsys.readouterr().out
    assert 'games' in text
    assert 'price' in text


def test_unknown_command_reports_error(capsys) -> None:
    '''Неизвестная команда возвращает ошибку и подсказку.'''
    assert main(['сваргань']) == 2
    assert 'Неизвестная команда' in capsys.readouterr().err


def test_price_without_query_reports_error(capsys) -> None:
    '''Команда price без имени игры подсказывает формат вызова.'''
    assert main(['price']) == 2
    assert 'Укажите игру' in capsys.readouterr().err
