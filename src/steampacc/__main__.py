"""Точка входа SteamPACC.

Запуск пакета: ``python -m steampacc``.
В собранном виде это SteamPACC.exe, который запускает тот же код.
"""

import sys


def main() -> int:
    """Запускает графическую часть приложения.

    Возвращает код возврата для передачи в систему.
    """
    try:
        from steampacc.app import run
    except ImportError:
        # Графическая часть ещё не реализована: сообщаем об этом и выходим.
        print(
            "SteamPACC: графическая часть ещё не реализована, "
            "программа завершает работу.",
            file=sys.stderr,
        )
        return 1
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
