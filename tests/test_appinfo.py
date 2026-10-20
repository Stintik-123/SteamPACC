'''Проверки модуля сведений об играх из appinfo.vdf.'''

from __future__ import annotations

import struct

from steampacc.appinfo import (
    find_apps,
    filter_by_type,
    installed_apps,
    load_appinfo,
)

#: Байт с нулевым значением: им заканчиваются строки.
NUL = bytes(1)

#: Байты-типы значений бинарного KeyValues.
TYPE_OBJECT = bytes(1)
TYPE_STRING = bytes([1])
TYPE_END = bytes([8])


def _string(key: str, value: str) -> bytes:
    '''Собирает пару «ключ — строковое значение» бинарного KeyValues.'''
    return TYPE_STRING + key.encode('utf-8') + NUL + value.encode('utf-8') + NUL


def _object(key: str) -> bytes:
    '''Собирает начало вложенного объекта бинарного KeyValues.'''
    return TYPE_OBJECT + key.encode('utf-8') + NUL


def _block(name: str, type_name: str, install_dir: str) -> bytes:
    '''Собирает блок записи appinfo.vdf со сведениями об игре.'''
    return bytes(40) + (
        _object('info')
        + _object('common')
        + _string('name', name)
        + _string('type', type_name)
        + TYPE_END
        + _object('config')
        + _string('installdir', install_dir)
        + TYPE_END
        + TYPE_END
        + TYPE_END
    )


def _file(*blocks: bytes) -> bytes:
    '''Собирает файл appinfo.vdf из готовых блоков записей.'''
    data = struct.pack('<II', 0x07564428, 41)
    for block in blocks:
        data += struct.pack('<II', 440, len(block)) + block
    return data + struct.pack('<II', 0, 0)


def test_load_appinfo_reads_game(tmp_path) -> None:
    '''Из файла читаются appid, имя, тип и каталог установки.'''
    path = tmp_path / 'appinfo.vdf'
    path.write_bytes(_file(_block('Test Game', 'game', 'TestGame')))
    apps = load_appinfo(path)
    assert len(apps) == 1
    assert apps[0].appid == 440
    assert apps[0].name == 'Test Game'
    assert apps[0].type == 'game'
    assert apps[0].installdir == 'TestGame'
    assert apps[0].is_installed is False
    assert apps[0].size_on_disk == 0


def test_load_appinfo_marks_installed(tmp_path) -> None:
    '''Установленная игра получает размер на диске.'''
    path = tmp_path / 'appinfo.vdf'
    path.write_bytes(_file(_block('Test Game', 'game', 'TestGame')))
    apps = load_appinfo(path, {440: 12345})
    assert apps[0].is_installed is True
    assert apps[0].size_on_disk == 12345


def test_load_appinfo_skips_broken_record(tmp_path) -> None:
    '''Обрезанная запись не роняет разбор, а пропускается.'''
    path = tmp_path / 'appinfo.vdf'
    good = _block('Test Game', 'game', 'TestGame')
    data = struct.pack('<II', 0x07564428, 41)
    data += struct.pack('<II', 440, len(good)) + good
    data += struct.pack('<II', 999, 4096) + b'\x00' * 16
    path.write_bytes(data)
    apps = load_appinfo(path)
    assert len(apps) == 1
    assert apps[0].appid == 440


def test_load_appinfo_missing_file(tmp_path) -> None:
    '''Отсутствующий файл даёт пустой список.'''
    assert load_appinfo(tmp_path / 'нет-такого.vdf') == []


def test_find_apps_ignores_case(tmp_path) -> None:
    '''Поиск по подстроке не учитывает регистр.'''
    path = tmp_path / 'appinfo.vdf'
    path.write_bytes(_file(_block('Counter Strike', 'game', 'cs')))
    apps = load_appinfo(path)
    assert len(find_apps(apps, 'counter')) == 1
    assert find_apps(apps, 'нет-такой') == []
    assert len(find_apps(apps, '')) == 1


def test_filter_by_type_keeps_only_type(tmp_path) -> None:
    '''Фильтр по типу оставляет только игры нужного типа.'''
    path = tmp_path / 'appinfo.vdf'
    path.write_bytes(_file(_block('Counter Strike', 'game', 'cs')))
    apps = load_appinfo(path)
    assert len(filter_by_type(apps, 'game')) == 1
    assert filter_by_type(apps, 'dlc') == []


def test_installed_apps_filters_list(tmp_path) -> None:
    '''Список установленных игр отбирается по признаку установки.'''
    path = tmp_path / 'appinfo.vdf'
    path.write_bytes(_file(_block('Counter Strike', 'game', 'cs')))
    apps = load_appinfo(path, {440: 100})
    assert len(installed_apps(apps)) == 1
