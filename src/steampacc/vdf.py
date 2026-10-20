'''Разбор текстового и бинарного формата Valve KeyValues (VDF).

Модуль умеет разбирать текстовый VDF, разбирать бинарный VDF (KeyValues1
в бинарном виде) и обходить файл appinfo.vdf, в котором Steam хранит сведения
об играх. Используется только стандартная библиотека; файлы Steam читаются
только на чтение и никогда не изменяются.

Таблица типов бинарного KeyValues1 взята из ValveKeyValue (проект
ValveResourceFormat) и подтверждена SteamKit2:

    0x00 — вложенный объект, 0x01 — строка, 0x02 — int32,
    0x03 — float32, 0x04 — указатель, 0x05 — широкая строка,
    0x06 — цвет, 0x07 — uint64, 0x08 — конец объекта,
    0x09 — двоичный блок, 0x0A — int64, 0x0B — альтернативный
    конец объекта.

Типы 0x0C и выше относятся к другим форматам Valve и в appinfo.vdf не
встречаются; такой тип считается неизвестным и приводит к ошибке
разбора с понятным сообщением.
'''

from __future__ import annotations

import struct
from typing import Any, Iterator

#: Словарь ключей и значений VDF.
KeyValues = dict[str, Any]

#: Символы, задаваемые через chr, чтобы текст файла не зависел от
#: экранирования в разных средах.
QUOTE = chr(34)
BACKSLASH = chr(92)
NEWLINE = chr(10)
TAB = chr(9)
CARRIAGE_RETURN = chr(13)

#: Символы, разделяющие токены текстового VDF.
_SPACE_CHARS = ' ' + TAB + CARRIAGE_RETURN + NEWLINE

#: Признак конца строки в бинарном VDF.
NUL = bytes(1)

#: Тип значения «вложенный объект» в бинарном VDF.
_KV_CHILD_OBJECT = 0x00

#: Тип значения «конец объекта» в бинарном VDF.
_KV_END = 0x08

#: Тип значения «альтернативный конец объекта» в бинарном VDF.
_KV_ALTERNATE_END = 0x0B

#: Старшая часть сигнатуры appinfo.vdf одинакова для всех версий.
_APPINFO_MAGIC_HIGH = 0x075644

#: Минимальная версия формата appinfo.vdf, которую понимает модуль.
_APPINFO_MIN_VERSION = 39

#: Максимальная версия формата appinfo.vdf, которую понимает модуль.
_APPINFO_MAX_VERSION = 41

#: Длина служебной части записи appinfo.vdf для версии 39.
_APPINFO_HEADER_V39 = 40

#: Длина служебной части записи appinfo.vdf для версий 40 и 41.
_APPINFO_HEADER_V40 = 60


class VdfError(ValueError):
    '''Ошибка разбора VDF: данные повреждены или формат не распознан.'''

#: Ключ, под которым складываются безымянные блоки текстового VDF.
_ANONYMOUS_KEY = ''


def _put(mapping: KeyValues, key: str, value: Any) -> None:
    '''Добавляет значение в словарь, объединяя повторяющиеся ключи в список.'''
    if key not in mapping:
        mapping[key] = value
        return
    existing = mapping[key]
    if isinstance(existing, list):
        existing.append(value)
    else:
        mapping[key] = [existing, value]


def _tokenize(text: str) -> Iterator[str]:
    '''Разбивает текстовый VDF на токены: строки, слова и фигурные скобки.'''
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in _SPACE_CHARS:
            index += 1
            continue
        if char == '/' and index + 1 < length and text[index + 1] == '/':
            line_end = text.find(NEWLINE, index)
            index = length if line_end < 0 else line_end + 1
            continue
        if char == '{' or char == '}':
            yield char
            index += 1
            continue
        if char == QUOTE:
            index += 1
            buffer: list[str] = []
            while index < length:
                current = text[index]
                if current == BACKSLASH and index + 1 < length:
                    following = text[index + 1]
                    if following == 'n':
                        buffer.append(NEWLINE)
                    elif following == 't':
                        buffer.append(TAB)
                    else:
                        buffer.append(following)
                    index += 2
                    continue
                if current == QUOTE:
                    index += 1
                    break
                buffer.append(current)
                index += 1
            yield ''.join(buffer)
            continue
        word_end = index
        while word_end < length and text[word_end] not in _SPACE_CHARS:
            if text[word_end] in '{}' or text[word_end] == QUOTE:
                break
            word_end += 1
        yield text[index:word_end]
        index = word_end


def parse_keyvalues(text: str) -> KeyValues:
    '''Разбирает текстовый VDF и возвращает словарь ключей и значений.

    Поддерживаются вложенные блоки в фигурных скобках, безымянные блоки,
    повторяющиеся ключи (значения собираются в список), комментарии из двух
    косых черт и экранирование кавычки и обратной косой черты.
    '''
    tokens = list(_tokenize(text))
    position = 0

    def parse_object(depth: int) -> KeyValues:
        nonlocal position
        result: KeyValues = {}
        while position < len(tokens):
            token = tokens[position]
            if token == '}':
                position += 1
                if depth == 0:
                    raise VdfError('В тексте VDF лишняя закрывающая скобка')
                return result
            if token == '{':
                position += 1
                _put(result, _ANONYMOUS_KEY, parse_object(depth + 1))
                continue
            key = token
            position += 1
            if position >= len(tokens):
                raise VdfError('Неожиданный конец текста: у ключа нет значения')
            following = tokens[position]
            if following == '{':
                position += 1
                _put(result, key, parse_object(depth + 1))
            else:
                position += 1
                _put(result, key, following)
        if depth > 0:
            raise VdfError('Неожиданный конец текста: не закрыты фигурные скобки')
        return result

    return parse_object(0)


def _read_cstring(data: bytes, offset: int) -> tuple[str, int]:
    '''Читает строку с завершающим нулём и возвращает её и новое смещение.'''
    end = data.find(NUL, offset)
    if end < 0:
        raise VdfError('Неожиданный конец данных: строка без завершающего нуля')
    text = data[offset:end].decode('utf-8', errors='replace')
    return text, end + 1


def _read_wstring(data: bytes, offset: int) -> tuple[str, int]:
    '''Читает широкую строку UTF-16LE, завершённую двойным нулём.'''
    end = offset
    while end + 1 < len(data):
        if data[end] == 0 and data[end + 1] == 0:
            break
        end += 2
    else:
        raise VdfError('Неожиданный конец данных: широкая строка без двойного нуля')
    text = data[offset:end].decode('utf-16-le', errors='replace')
    return text, end + 2


def _unpack(data: bytes, offset: int, fmt: str) -> Any:
    '''Читает одно число из данных, проверяя, что данных достаточно.'''
    size = struct.calcsize(fmt)
    if offset + size > len(data):
        raise VdfError('Неожиданный конец данных при чтении числа')
    return struct.unpack_from(fmt, data, offset)[0]


def _read_value(data: bytes, offset: int, type_id: int) -> tuple[Any, int]:
    '''Читает значение бинарного KeyValues по его типу.'''
    if type_id == 0x01:
        return _read_cstring(data, offset)
    if type_id == 0x02:
        return _unpack(data, offset, '<i'), offset + 4
    if type_id == 0x03:
        return _unpack(data, offset, '<f'), offset + 4
    if type_id == 0x04:
        return _unpack(data, offset, '<I'), offset + 4
    if type_id == 0x05:
        return _read_wstring(data, offset)
    if type_id == 0x06:
        return _unpack(data, offset, '<I'), offset + 4
    if type_id == 0x07:
        return _unpack(data, offset, '<Q'), offset + 8
    if type_id == 0x09:
        size = _unpack(data, offset, '<i')
        offset += 4
        if size < 0 or offset + size > len(data):
            raise VdfError('Неожиданный конец данных: обрезан двоичный блок')
        block = data[offset:offset + size]
        return block, offset + size
    if type_id == 0x0A:
        return _unpack(data, offset, '<q'), offset + 8
    raise VdfError('Неизвестный тип значения в бинарном VDF: 0x{:02X}'.format(type_id))


def _parse_object(data: bytes, offset: int, depth: int = 0) -> tuple[KeyValues, int]:
    '''Разбирает один объект бинарного KeyValues начиная со смещения offset.'''
    if depth > 64:
        raise VdfError('Слишком глубокая вложенность бинарного VDF')
    result: KeyValues = {}
    while True:
        if offset >= len(data):
            raise VdfError('Неожиданный конец данных внутри бинарного VDF')
        type_id = data[offset]
        offset += 1
        if type_id == _KV_END or type_id == _KV_ALTERNATE_END:
            return result, offset
        key, offset = _read_cstring(data, offset)
        if type_id == _KV_CHILD_OBJECT:
            value, offset = _parse_object(data, offset, depth + 1)
        else:
            value, offset = _read_value(data, offset, type_id)
        _put(result, key, value)


def parse_binary_vdf(data: bytes) -> KeyValues:
    '''Разбирает бинарный VDF и возвращает корневой словарь.'''
    result, _ = _parse_object(data, 0)
    return result


#: Полная сигнатура файла appinfo.vdf.
APPINFO_MAGIC = (_APPINFO_MAGIC_HIGH << 8) | 0x28


def _appinfo_header_length(universe: int) -> int:
    '''Возвращает длину служебной части записи appinfo.vdf.'''
    if universe >= 40:
        return _APPINFO_HEADER_V40
    return _APPINFO_HEADER_V39


def _find_info_section(block: bytes, universe: int) -> KeyValues | None:
    '''Ищет в блоке записи секцию info со сведениями об игре.'''
    marker = bytes(1) + b'info' + NUL
    candidates: list[int] = []
    position = block.find(marker)
    if position >= 0:
        candidates.append(position)
    candidates.append(_appinfo_header_length(universe))
    candidates.append(_APPINFO_HEADER_V39)
    candidates.append(0)
    fallback: KeyValues | None = None
    for start in candidates:
        if start < 0 or start >= len(block):
            continue
        try:
            parsed, _ = _parse_object(block, start)
        except VdfError:
            continue
        if not parsed:
            continue
        if 'info' in parsed:
            return parsed
        if fallback is None:
            fallback = parsed
    return fallback


def iter_appinfo_entries(data: bytes) -> Iterator[KeyValues]:
    '''Обходит записи appinfo.vdf и отдаёт сведения о каждой игре.

    Заголовок файла содержит сигнатуру и номер вселенной, дальше идут
    записи: идентификатор игры, размер блока и сам блок. Из блока
    достаются имя игры (common/name) и каталог установки
    (config/installdir), а полный разобранный блок доступен по ключу info.
    Если сигнатура не совпала, поднимается VdfError с понятным текстом;
    обрезанная запись тихо завершает обход.
    '''
    if len(data) < 8:
        raise VdfError('appinfo.vdf слишком короткий: нет заголовка')
    magic, universe = struct.unpack_from('<II', data, 0)
    if magic != APPINFO_MAGIC:
        raise VdfError(
            'Неизвестный формат appinfo.vdf: ожидалась сигнатура 0x{:08X}, получена 0x{:08X}'.format(
                APPINFO_MAGIC, magic
            )
        )
    offset = 8
    while offset + 8 <= len(data):
        appid, size = struct.unpack_from('<II', data, offset)
        offset += 8
        if appid == 0 and size == 0:
            return
        if size == 0 or offset + size > len(data):
            return
        block = data[offset:offset + size]
        offset += size
        section = _find_info_section(block, universe)
        if section is None:
            continue
        info = section.get('info')
        if not isinstance(info, dict):
            info = section
        common = info.get('common')
        config = info.get('config')
        common = common if isinstance(common, dict) else {}
        config = config if isinstance(config, dict) else {}
        yield {
            'appid': appid,
            'name': common.get('name'),
            'install_dir': config.get('installdir'),
            'info': info,
        }
