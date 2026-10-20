'''Проверки модуля поиска установки Steam и путей к её файлам.'''

from __future__ import annotations

from pathlib import Path

from steampacc.steam_paths import SteamPaths, find_steam_root, steam_paths


def test_steam_paths_builds_expected_files(tmp_path: Path) -> None:
    '''steam_paths собирает все пути Steam от корневого каталога.'''
    paths = steam_paths(tmp_path)

    assert isinstance(paths, SteamPaths)
    assert paths.root == tmp_path
    assert paths.steamapps == tmp_path / 'steamapps'
    assert paths.appcache == tmp_path / 'appcache'
    assert paths.appinfo_vdf == tmp_path / 'appcache' / 'appinfo.vdf'
    assert paths.config_vdf == tmp_path / 'config' / 'config.vdf'
    assert paths.libraryfolders_vdf == tmp_path / 'steamapps' / 'libraryfolders.vdf'
    assert paths.userdata == tmp_path / 'userdata'


def test_steam_paths_does_not_touch_disk(tmp_path: Path) -> None:
    '''Построение путей ничего не создаёт на диске.'''
    root = tmp_path / 'Steam'
    root.mkdir()

    steam_paths(root)

    assert list(root.iterdir()) == []


def test_find_steam_root_returns_path_or_none() -> None:
    '''find_steam_root не бросает исключение и даёт Path или None.'''
    result = find_steam_root()

    assert result is None or isinstance(result, Path)


def test_module_imports_on_any_os() -> None:
    '''Модуль импортируется вне Windows и не падает.'''
    import steampacc.steam_paths as module

    assert module is not None
