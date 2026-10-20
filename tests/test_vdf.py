'''Проверки разбора текстового VDF, бинарного KeyValues и файла appinfo.vdf.'''

from __future__ import annotations

import struct

from steampacc.vdf import (
    VdfError,
    iter_appinfo_entries,
    parse_binary_vdf,
    parse_keyvalues,
)

#: Байт с нулевым значением: им заканчиваются строки.
NUL = bytes(1)

#: Байты-типы значений бинарного KeyValues.
TYPE_OBJECT = bytes(1)
TYPE_STRING = bytes([1])
TYPE_INT32 = bytes([2])
TYPE_END = bytes([8])

#: Обратная косая черта, заданная через chr, чтобы не зависеть от экранирования.
BACKSLASH = chr(92)

#: Перевод строки, заданный через chr.
NEWLINE = chr(10)


def _string(key: str, value: str) -> bytes:
    '''Собирает пару «ключ — строковое значение» бинарного KeyValues.'''
    return (
        TYPE_STRING
        + key.encode('utf-8')
        + NUL
        + value.encode('utf-8')
        + NUL
    )


def _object(key: str) -> bytes:
    '''Собирает начало вложенного объекта бинарного KeyValues.'''
    return TYPE_OBJECT + key.encode('utf-8') + NUL


def test_parse_keyvalues_reads_nested_blocks() -> None:
    '''Вложенные блоки разбираются в словари.'''
    text = (
        '"root"' + NEWLINE
        + '{' + NEWLINE
        + '  "name" "Counter-Strike"' + NEWLINE
        + '  "common" {' + NEWLINE
        + '    "type" "game"' + NEWLINE
        + '  }' + NEWLINE
        + '}' + NEWLINE
    )
    result = parse_keyvalues(text)
    assert result['root']['name'] == 'Counter-Strike'
    assert result['root']['common']['type'] == 'game'


def test_parse_keyvalues_joins_repeated_keys() -> None:
    '''Повторяющиеся ключи собираются в список.'''
    text = '"appid" "10"' + NEWLINE + '"appid" "20"' + NEWLINE
    result = parse_keyvalues(text)
    assert result['appid'] == ['10', '20']


def test_parse_keyvalues_skips_comments() -> None:
    '''Комментарии из двух косых черт игнорируются.'''
    text = '// комментарий' + NEWLINE + '"key" "value" // хвост' + NEWLINE
    result = parse_keyvalues(text)
    assert result == {'key': 'value'}


def test_parse_keyvalues_unescapes_symbols() -> None:
    '''Экранированная обратная косая черта разворачивается.'''
    text = '"path" "C:' + BACKSLASH + BACKSLASH + 'games"' + NEWLINE
    result = parse_keyvalues(text)
    assert result['path'] == 'C:' + BACKSLASH + 'games'


def test_parse_keyvalues_reads_anonymous_block() -> None:
    '''Безымянный блок попадает в ключ с пустым именем.'''
    text = '{' + NEWLINE + '"a" "1"' + NEWLINE + '}' + NEWLINE
    result = parse_keyvalues(text)
    assert result[''] == {'a': '1'}


def test_parse_binary_vdf_reads_values() -> None:
    '''Строки и целые числа читаются по типам.'''
    data = (
        _string('appid', '440')
        + TYPE_INT32 + b'size' + NUL + struct.pack('<i', 1234)
        + TYPE_END
    )
    result = parse_binary_vdf(data)
    assert result['appid'] == '440'
    assert result['size'] == 1234


def test_parse_binary_vdf_reads_nested_object() -> None:
    '''Вложенный объект попадает в словарь по своему ключу.'''
    data = _object('info') + _string('name', 'Game') + TYPE_END + TYPE_END
    result = parse_binary_vdf(data)
    assert result['info']['name'] == 'Game'


def test_parse_binary_vdf_rejects_unknown_type() -> None:
    '''Неизвестный тип значения приводит к понятной ошибке.'''
    data = bytes([20]) + b'key' + NUL
    try:
        parse_binary_vdf(data)
    except VdfError as error:
        assert 'Неизвестный тип' in str(error)
    else:
        raise AssertionError('Ожидалась ошибка VdfError')


def test_iter_appinfo_entries_reads_game() -> None:
    '''Из appinfo.vdf читаются appid, имя игры и каталог установки.'''
    block = bytes(40) + (
        _object('info')
        + _object('common') + _string('name', 'Test Game') + TYPE_END
        + _object('config') + _string('installdir', 'TestGame') + TYPE_END
        + TYPE_END
        + TYPE_END
    )
    data = (
        struct.pack('<II', 0x07564428, 41)
        + struct.pack('<II', 440, len(block))
        + block
        + struct.pack('<II', 0, 0)
    )
    entries = list(iter_appinfo_entries(data))
    assert len(entries) == 1
    assert entries[0]['appid'] == 440
    assert entries[0]['name'] == 'Test Game'
    assert entries[0]['install_dir'] == 'TestGame'


def test_iter_appinfo_entries_rejects_wrong_magic() -> None:
    '''Файл с чужой сигнатурой отклоняется.'''
    data = struct.pack('<II', 0x12345678, 41) + struct.pack('<II', 0, 0)
    try:
        list(iter_appinfo_entries(data))
    except VdfError as error:
        assert 'сигнатура' in str(error)
    else:
        raise AssertionError('Ожидалась ошибка VdfError')
