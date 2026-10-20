'''Точка входа SteamPACC.

Запуск пакета: ``python -m steampacc``.
В собранном виде это SteamPACC.exe, который запускает тот же код.

Модуль написан так, чтобы программа никогда не умирала молча.
Первым делом в журнал пишется факт запуска, а любая ошибка
показывается пользователю окном. В сборке --windowed стандартный
поток ошибок не виден, поэтому рассчитывать только на него нельзя.

Служебные ключи запуска:

* ``--version`` - напечатать версию и выйти;
* ``--selftest`` - собрать сведения о системе и записать отчёт;
* ``--smoke`` - проверить, что графическая часть поднимается.
'''

from __future__ import annotations

import sys
from typing import Sequence

#: Ключ запуска: показать версию.
VERSION_FLAG = '--version'

#: Ключ запуска: собрать отчёт о состоянии системы.
SELFTEST_FLAG = '--selftest'

#: Ключ запуска: проверить запуск графической части.
SMOKE_FLAG = '--smoke'


def _log_start() -> None:
    '''Пишет в журнал факт запуска программы и её аргументы.'''
    try:
        from steampacc.diagnostics import log_message

        log_message('Старт SteamPACC, аргументы: ' + ' '.join(sys.argv))
    except Exception:
        pass


def _log_path() -> str:
    '''Возвращает путь к журналу работы программы.'''
    try:
        from steampacc.diagnostics import log_path

        return str(log_path())
    except Exception:
        return 'неизвестно'


def _show_fatal(text: str) -> None:
    '''Показывает пользователю окно с ошибкой и пишет её в журнал.'''
    try:
        from steampacc.diagnostics import log_exception, show_error

        log_exception('Критическая ошибка запуска')
        show_error('SteamPACC - ошибка', text)
    except Exception:
        print(text, file=sys.stderr)


def _run_version() -> int:
    '''Печатает версию программы.'''
    from steampacc import __version__

    print('SteamPACC ' + str(__version__))
    return 0


def _run_selftest() -> int:
    '''Собирает сведения о системе и записывает отчёт на диск.'''
    from steampacc.selftest import run_selftest

    path = run_selftest()
    print('Отчёт самопроверки сохранён: ' + str(path))
    return 0


def _run_smoke() -> int:
    '''Проверяет, что графическая часть поднимается.'''
    from steampacc.app import smoke_test

    return int(smoke_test())


def main(argv: Sequence[str] | None = None) -> int:
    '''Запускает программу и возвращает код возврата для системы.'''
    args = list(argv) if argv is not None else list(sys.argv[1:])
    _log_start()
    try:
        if VERSION_FLAG in args:
            return _run_version()
        if SELFTEST_FLAG in args:
            return _run_selftest()
        if SMOKE_FLAG in args:
            return _run_smoke()
        from steampacc.app import run

        return int(run())
    except ImportError as error:
        _show_fatal(
            'Не удалось загрузить графическую часть программы: ' + str(error) + chr(10)
            + 'Подробности в файле: ' + str(_log_path())
        )
        return 1
    except Exception as error:
        _show_fatal(
            'Не удалось запустить программу: ' + str(error) + chr(10)
            + 'Подробности в файле: ' + str(_log_path())
        )
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
