'''Тесты модуля library: манифесты игр и перечни библиотек.'''

from __future__ import annotations

from pathlib import Path

from steampacc.library import (
    iter_library_games,
    parse_appmanifest,
    read_installed_games,
    read_library_folders,
)

TAB = chr(9)
NL = chr(10)
BACKSLASH = chr(92)

MANIFEST_LINES = [
    '"AppState"',
    '{',
    TAB + '"appid"' + TAB + '"440"',
    TAB + '"name"' + TAB + '"Team Fortress 2"',
    TAB + '"installdir"' + TAB + '"Team Fortress 2"',
    TAB + '"SizeOnDisk"' + TAB + '"123456"',
    TAB + '"LastUpdated"' + TAB + '"1700000000"',
    TAB + '"buildid"' + TAB + '"555"',
    '}',
]

LIBRARY_LINES = [
    '"libraryfolders"',
    '{',
    TAB + '"0"',
    TAB + '{',
    TAB + TAB + '"path"' + TAB + '"D:' + BACKSLASH + BACKSLASH + 'Games"',
    TAB + '}',
    TAB + '"1"',
    TAB + '{',
    TAB + TAB + '"path"' + TAB + '"E:' + BACKSLASH + BACKSLASH + 'Games2"',
    TAB + '}',
    TAB + '"contentstatsid"' + TAB + '"1234567890"',
    '}',
]

MANIFEST = NL.join(MANIFEST_LINES)
LIBRARYFOLDERS = NL.join(LIBRARY_LINES)


def test_parse_appmanifest_reads_fields() -> None:
    info = parse_appmanifest(MANIFEST)
    assert info['appid'] == 440
    assert info['name'] == 'Team Fortress 2'
    assert info['installdir'] == 'Team Fortress 2'
    assert info['size_on_disk'] == 123456
    assert info['last_updated'] == 1700000000
    assert info['buildid'] == 555


def test_parse_appmanifest_survives_garbage() -> None:
    info = parse_appmanifest('битый файл {{{')
    assert not info.get('appid')


def test_read_installed_games_reads_manifest(tmp_path: Path) -> None:
    steamapps = tmp_path / 'steamapps'
    steamapps.mkdir(parents=True)
    (steamapps / 'appmanifest_440.acf').write_text(MANIFEST, encoding='utf-8')
    (steamapps / 'appmanifest_999.acf').write_text('битый файл', encoding='utf-8')
    games = read_installed_games(tmp_path)
    assert len(games) == 1
    game = games[0]
    assert game.appid == 440
    assert game.name == 'Team Fortress 2'
    assert game.install_dir == steamapps / 'common' / 'Team Fortress 2'
    assert game.library_root == tmp_path
    assert game.size_on_disk == 123456
    assert game.manifest_path == steamapps / 'appmanifest_440.acf'


def test_read_installed_games_without_directory(tmp_path: Path) -> None:
    assert read_installed_games(tmp_path / 'нет') == []


def test_read_library_folders_reads_paths() -> None:
    paths = read_library_folders(LIBRARYFOLDERS)
    assert len(paths) == 2
    assert str(paths[0]) == 'D:' + BACKSLASH + 'Games'
    assert str(paths[1]) == 'E:' + BACKSLASH + 'Games2'


def test_iter_library_games_skips_duplicates(tmp_path: Path) -> None:
    for root in (tmp_path / 'one', tmp_path / 'two'):
        steamapps = root / 'steamapps'
        steamapps.mkdir(parents=True)
        (steamapps / 'appmanifest_440.acf').write_text(MANIFEST, encoding='utf-8')
    games = list(iter_library_games([tmp_path / 'one', tmp_path / 'two']))
    assert len(games) == 1
