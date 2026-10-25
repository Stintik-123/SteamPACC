'''Тесты модуля config: пользовательские настройки приложения.'''

from __future__ import annotations

import json
from pathlib import Path

from steampacc.config import (
    Settings,
    apply_changes,
    load_settings,
    save_settings,
    settings_path,
)


def test_settings_have_defaults() -> None:
    settings = Settings()
    assert settings.language == 'ru'
    assert settings.theme == 'dark'
    assert settings.integration_enabled is True
    assert settings.launch_with_steam is False
    assert settings.steam_exe == ''


def test_load_settings_reads_file(tmp_path: Path) -> None:
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'language': 'en', 'theme': 'light'}), encoding='utf-8')
    settings = load_settings(path)
    assert settings.language == 'en'
    assert settings.theme == 'light'


def test_load_settings_ignores_garbage_values(tmp_path: Path) -> None:
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'language': 'клингонский', 'theme': 'розовая'}), encoding='utf-8')
    settings = load_settings(path)
    assert settings.language == 'ru'
    assert settings.theme == 'dark'


def test_load_settings_survives_broken_file(tmp_path: Path) -> None:
    path = tmp_path / 'config.json'
    path.write_text('это не json {{{', encoding='utf-8')
    assert load_settings(path) == Settings()


def test_load_settings_without_file(tmp_path: Path) -> None:
    assert load_settings(tmp_path / 'нет.json') == Settings()


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / 'nested' / 'config.json'
    settings = Settings(language='en', theme='light', steam_exe=r'C:\Games\Steam\steam.exe')
    saved = save_settings(settings, path)
    assert saved == path
    assert path.exists()
    loaded = load_settings(path)
    assert loaded.language == 'en'
    assert loaded.theme == 'light'
    assert loaded.steam_exe == r'C:\Games\Steam\steam.exe'


def test_old_overlay_fields_are_dropped(tmp_path: Path) -> None:
    '''Поля удалённого оверлея не ломают чтение старого конфига.'''
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({
        'overlay_opacity': 0.5, 'overlay_scale': 150, 'show_fps': False,
        'update_interval': 30, 'country': 'us', 'currencies': ['USD'],
    }), encoding='utf-8')
    settings = load_settings(path)
    assert settings.currencies == ('USD',)
    assert not hasattr(settings, 'overlay_opacity')


def test_apply_changes_ignores_garbage() -> None:
    result = apply_changes(Settings(), {'language': 42, 'integration_enabled': 'да'})
    assert result.language == 'ru'
    assert result.integration_enabled is True


def test_settings_path_points_to_file() -> None:
    path = settings_path()
    assert isinstance(path, Path)
    assert path.name == 'config.json'


def test_settings_have_default_currencies() -> None:
    assert Settings().currencies == ('RUB', 'USD', 'EUR')


def test_load_settings_reads_currencies(tmp_path: Path) -> None:
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'currencies': ['usd', 'eur', 'usd']}), encoding='utf-8')
    settings = load_settings(path)
    assert settings.currencies == ('USD', 'EUR')


def test_save_and_load_keeps_currencies(tmp_path: Path) -> None:
    path = tmp_path / 'config.json'
    save_settings(Settings(currencies=('USD',)), path)
    assert load_settings(path).currencies == ('USD',)


def test_apply_changes_replaces_currencies() -> None:
    result = apply_changes(Settings(), {'currencies': ['jpy']})
    assert result.currencies == ('JPY',)


def test_empty_currencies_allowed() -> None:
    '''Пустой список регионов — разрешённый выбор: блок цен выключается.'''
    result = apply_changes(Settings(), {'currencies': []})
    assert result.currencies == ()
    path = Path(__file__).parent / 'tmp_empty.json'
    try:
        save_settings(result, path)
        assert load_settings(path).currencies == ()
    finally:
        path.unlink(missing_ok=True)
