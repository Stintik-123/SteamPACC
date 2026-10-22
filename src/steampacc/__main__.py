"""Точка входа SteamPACC.

Запуск программы: ``python -m steampacc``.
В сборанном виде это SteamPACC.exe, который запускает этот код.

Модуль настраивает консоль и обрабатывает аргументы командной строки.

Программу можно запустить двумя способами из командной строки:

* после установки пакета (``pip install steampacc``) — командой ``steampacc``;
* из исходников — командой ``python -m steampacc``.

Ключи запуска:

* ``--version`` - напечатать версию и выйти;
* ``--help`` - напечатать список ключей и выйти;
* ``--selftest`` - создать отчёт о системе и выйти;
* ``--smoke`` - проверить, что графическая часть работает;
* ``--prices APPID`` - показать цены игры прямо в консоли (без графики);
* ``--enable-autostart`` - включить запуск программы вместе с Windows;
* ``--disable-autostart`` - выключить запуск программы вместе с Windows;
* ``--autostart`` - флаг, что запуск из автозагрузки Windows.
"""

from __future__ import annotations

import sys
from typing import Sequence

#: Ключ запуска: напечатать версию.
VERSION_FLAG = '--version'

#: Ключ запуска: напечатать справку по командной строке.
HELP_FLAG = '--help'

#: Ключ запуска: напечатать справку по командной строке (короткий вид).
HELP_FLAG_SHORT = '-h'

#: Ключ запуска: создать отчёт о системе.
SELFTEST_FLAG = '--selftest'

#: Ключ запуска: проверить графическую часть.
SMOKE_FLAG = '--smoke'

#: Ключ запуска: показать цены игры в консоли.
PRICES_FLAG = '--prices'

#: Ключ запуска: включить автозапуск SteamPACC вместе с Windows.
ENABLE_AUTOSTART_FLAG = '--enable-autostart'

#: Ключ запуска: выключить автозапуск SteamPACC вместе с Windows.
DISABLE_AUTOSTART_FLAG = '--disable-autostart'

#: Ключ запуска: автозапуск из Windows.
AUTOSTART_FLAG = '--autostart'

#: Текст справки для запуска из командной строки.
HELP_TEXT = '\n'.join((
    'SteamPACC - цены игр Steam в разных валютах поверх клиента Steam.',
    '',
    'Запуск из командной строки:',
    '  steampacc                 - обычный запуск: программа живёт в трее',
    '  python -m steampacc       - то же самое из исходников',
    '',
    'Ключи:',
    '  --version                 напечатать версию',
    '  --help                    напечатать эту справку',
    '  --selftest                проверить систему и сохранить отчёт',
    '  --smoke                   проверить, что графическая часть работает',
    '  --prices APPID            показать цены игры APPID в консоли',
    '  --enable-autostart        включить запуск вместе с Windows',
    '  --disable-autostart       выключить запуск вместе с Windows',
    '  --autostart               запуск из автозагрузки Windows',
))


def _prepare_console() -> None:
    """Настраивает консоль для красивого вывода: кодировка и отступы."""
    try:
        from steampacc.diagnostics import configure_console
        configure_console()
    except Exception:
        pass


def _log_start() -> None:
    """Пишет в журнал факт запуска программы и её аргументы."""
    try:
        from steampacc.diagnostics import log_message
        log_message('Старт SteamPACC, аргументы: ' + ' '.join(sys.argv))
    except Exception:
        pass


def _log_path() -> str:
    """Возвращает путь к файлу журнала."""
    try:
        from steampacc.diagnostics import log_path
        return str(log_path())
    except Exception:
        return 'неизвестно'


def _show_fatal(text: str) -> None:
    """Показывает фатальную ошибку пользователю и пишет в журнал."""
    try:
        from steampacc.diagnostics import log_exception, safe_print, show_error
        log_exception('Критическая ошибка запуска')
        show_error('SteamPACC - ошибка', text)
    except Exception:
        try:
            from steampacc.diagnostics import safe_print
            safe_print(text, sys.stderr)
        except Exception:
            pass


def _run_version() -> int:
    """Печатает версию и выходит."""
    from steampacc import __version__
    from steampacc.diagnostics import safe_print
    safe_print('SteamPACC ' + str(__version__))
    return 0


def _run_help() -> int:
    """Печатает справку по ключам командной строки и выходит."""
    from steampacc.diagnostics import safe_print
    safe_print(HELP_TEXT)
    return 0


def _run_prices(args: Sequence[str]) -> int:
    """Показывает цены игры прямо в консоли: без графики и трея.

    Ключ ``--prices`` должен следовать за идентификатором игры (appid).
    Валюты берутся из настроек пользователя, как в оверлее.
    """
    from steampacc.diagnostics import safe_print
    from steampacc.config import load_settings
    from steampacc.prices import CURRENCY_COUNTRIES, PriceError, fetch_price, format_price

    items = list(args)
    index = items.index(PRICES_FLAG)
    appid: int | None = None
    if index + 1 < len(items):
        try:
            appid = int(items[index + 1])
        except ValueError:
            appid = None
    if appid is None or appid <= 0:
        safe_print('Нужен идентификатор игры: steampacc --prices 730')
        return 2

    from steampacc.app import watch_currencies

    settings = load_settings()
    codes = watch_currencies(settings)
    safe_print('Цены Steam для игры ' + str(appid) + ':')
    failures = 0
    for code in codes:
        country = CURRENCY_COUNTRIES.get(code, code.lower())
        try:
            price = fetch_price(appid, country)
        except PriceError as error:
            failures += 1
            safe_print(code + ': ошибка - ' + str(error))
            continue
        title = (price.title or '').strip()
        line = code + ': ' + format_price(price)
        if title:
            line += ' (' + title + ')'
        safe_print(line)
    return 0 if failures < len(codes) else 1


def _run_selftest() -> int:
    """Создаёт отчёт о системе и выходит."""
    from steampacc.diagnostics import safe_print
    from steampacc.selftest import run_selftest
    path = run_selftest()
    safe_print('Отчёт о системе создан: ' + str(path))
    return 0


def _run_smoke() -> int:
    """Проверяет, что графическая часть работает."""
    from steampacc.app import smoke_test
    return int(smoke_test())


def _current_program_path() -> str:
    """Возвращает путь к программе, который нужно записать в автозапуск.

    В собранном виде (PyInstaller) это SteamPACC.exe; при запуске из
    исходников — pythonw.exe с модулем steampacc, чтобы Windows запускала
    программу без окна консоли.
    """
    import sys
    from pathlib import Path

    frozen = getattr(sys, 'frozen', False)
    if frozen:
        return str(Path(sys.executable))
    # Из исходников: запускаем пакет через интерпретатор без окна консоли.
    python = Path(sys.executable)
    pythonw = python.with_name('pythonw' + python.suffix)
    if pythonw.exists():
        return str(pythonw)
    return str(python)


def _autostart_arguments() -> str:
    """Аргументы автозапуска: из собранного файла — флаг, иначе -m steampacc."""
    import sys

    if getattr(sys, 'frozen', False):
        return AUTOSTART_FLAG
    return '-m steampacc ' + AUTOSTART_FLAG


def _set_autostart(enable: bool) -> int:
    """Включает или выключает запуск программы вместе с Windows.

    Работает через командную строку (reg.exe), права администратора не
    нужны. Вне Windows честно сообщает, что автозапуск недоступен.
    """
    from steampacc.diagnostics import safe_print
    from steampacc import win_api

    if not win_api.is_available():
        safe_print('Автозапуск доступен только в Windows.')
        return 1
    executable = _current_program_path()
    command = win_api.build_autostart_command(executable, _autostart_arguments())
    ok = win_api.register_autostart(executable, enable=enable)
    if not ok:
        safe_print('Не удалось изменить автозапуск: проверьте доступ к реестру.')
        return 1
    state = 'включён' if enable else 'выключен'
    safe_print('Автозапуск SteamPACC ' + state + '.')
    if enable:
        safe_print('Запись в реестре: ' + command)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Запускает программу и возвращает код выхода.
    
    Запускает графический интерфейс, если не переданы специальные ключи.
    """
    args = list(argv) if argv is not None else list(sys.argv[1:])
    _prepare_console()
    _log_start()
    
    try:
        if VERSION_FLAG in args:
            return _run_version()
        if HELP_FLAG in args or HELP_FLAG_SHORT in args:
            return _run_help()
        if SELFTEST_FLAG in args:
            return _run_selftest()
        if SMOKE_FLAG in args:
            return _run_smoke()
        if PRICES_FLAG in args:
            return _run_prices(args)
        if ENABLE_AUTOSTART_FLAG in args:
            return _set_autostart(True)
        if DISABLE_AUTOSTART_FLAG in args:
            return _set_autostart(False)
        
        # Normal launch
        from steampacc.app import run
        return int(run())
        
    except ImportError as error:
        _show_fatal(
            'Не удалось загрузить графическую библиотеку: ' + str(error) + chr(10) +
            'Подробности в файле: ' + str(_log_path())
        )
        return 1
    except Exception as error:
        _show_fatal(
            'Не удалось запустить программу: ' + str(error) + chr(10) +
            'Подробности в файле: ' + str(_log_path())
        )
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
