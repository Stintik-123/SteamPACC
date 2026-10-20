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
    assert settings.country == 'ru'
    assert settings.overlay_opacity == 0.9
    assert settings.overlay_scale == 100
    assert settings.update_interval == 60
    assert settings.show_fps is True


def test_load_settings_reads_file(tmp_path: Path) -> None:
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'language': 'en', 'overlay_scale': 150}), encoding='utf-8')
    settings = load_settings(path)
    assert settings.language == 'en'
    assert settings.overlay_scale == 150
    assert settings.country == 'ru'


def test_load_settings_survives_broken_file(tmp_path: Path) -> None:
    path = tmp_path / 'config.json'
    path.write_text('это не json {{{', encoding='utf-8')
    assert load_settings(path) == Settings()


def test_load_settings_without_file(tmp_path: Path) -> None:
    assert load_settings(tmp_path / 'нет.json') == Settings()


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / 'nested' / 'config.json'
    settings = Settings(language='en', country='us', overlay_scale=120)
    saved = save_settings(settings, path)
    assert saved == path
    assert path.exists()
    loaded = load_settings(path)
    assert loaded.language == 'en'
    assert loaded.country == 'us'
    assert loaded.overlay_scale == 120


def test_apply_changes_clamps_values() -> None:
    result = apply_changes(Settings(), {'overlay_opacity': 5.0, 'overlay_scale': 10, 'update_interval': 1})
    assert result.overlay_opacity == 1.0
    assert result.overlay_scale == 50
    assert result.update_interval == 10


def test_apply_changes_ignores_garbage() -> None:
    result = apply_changes(Settings(), {'language': 42, 'show_fps': 'да'})
    assert result.language == 'ru'
    assert result.show_fps is True


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
