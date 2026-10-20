"""Точка входа SteamPACC.

Запуск программы: ``python -m steampacc``.
В сборанном виде это SteamPACC.exe, который запускает этот код.

Модуль настраивает консоль и обрабатывает аргументы командной строки.

Ключи запуска:

* ``--version`` - напечатать версию и выйти;
* ``--selftest`` - создать отчёт о системе и выйти;
* ``--smoke`` - проверить, что графическая часть работает;
* ``--autostart`` - флаг, что запуск из автозагрузки Windows.
"""

from __future__ import annotations

import sys
from typing import Sequence

#: Ключ запуска: напечатать версию.
VERSION_FLAG = '--version'

#: Ключ запуска: создать отчёт о системе.
SELFTEST_FLAG = '--selftest'

#: Ключ запуска: проверить графическую часть.
SMOKE_FLAG = '--smoke'

#: Ключ запуска: автозапуск из Windows.
AUTOSTART_FLAG = '--autostart'


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
        if SELFTEST_FLAG in args:
            return _run_selftest()
        if SMOKE_FLAG in args:
            return _run_smoke()
        
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
