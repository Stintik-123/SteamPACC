'''Тонкий слой над WinAPI через ctypes, без pywin32.

Модуль нужен приложению, чтобы узнавать, какое окно сейчас активно: по
заголовку и классу окна определяется запущенная игра, по прямоугольнику
считается положение оверлея.

Библиотека user32 загружается только под Windows, поэтому модуль
импортируется на любой системе: на остальных платформах функции
возвращают безопасное значение или поднимают WinApiError с понятным
русским текстом.
'''

from __future__ import annotations

import ctypes
import sys
from typing import Any

#: Контекст DPI для Windows 10 1703 и новее: окно масштабируется под монитор.
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

#: Индекс расширенного стиля окна.
GWL_EXSTYLE = -20

#: Индекс обычного стиля окна.
GWL_STYLE = -16

#: Право доступа к процессу: только чтение сведений, без управления.
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

#: Расширенные стили окна: клики проходят сквозь окно и оно не активируется.
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000


class WinApiError(Exception):
    '''Ошибка вызова WinAPI с понятным русским текстом.'''


class RECT(ctypes.Structure):
    '''Прямоугольник окна в координатах экрана.'''

    _fields_ = [
        ('left', ctypes.c_long),
        ('top', ctypes.c_long),
        ('right', ctypes.c_long),
        ('bottom', ctypes.c_long),
    ]


_user32: Any | None = None


def is_available() -> bool:
    '''True только под Windows: на других системах WinAPI недоступен.'''
    return sys.platform.startswith('win')


def _lib() -> Any:
    '''Возвращает user32, загружая её при первом обращении.'''
    global _user32
    if not is_available():
        raise WinApiError('WinAPI доступен только в Windows, текущая система: ' + sys.platform)
    if _user32 is None:
        _user32 = ctypes.windll.user32
        _setup(_user32)
    return _user32


def _setup(user32: Any) -> None:
    '''Задаёт типы аргументов: без них на 64-битной системе ломаются дескрипторы.'''
    pointer = ctypes.c_void_p
    wide = ctypes.POINTER(ctypes.c_wchar)
    user32.GetForegroundWindow.restype = pointer
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = pointer
    user32.IsWindow.argtypes = [pointer]
    user32.IsWindow.restype = ctypes.c_int
    user32.IsIconic.argtypes = [pointer]
    user32.IsIconic.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [pointer, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = ctypes.c_int
    user32.GetWindowTextLengthW.argtypes = [pointer]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [pointer, wide, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [pointer, wide, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.SetProcessDpiAwarenessContext.argtypes = [pointer]
    user32.SetProcessDpiAwarenessContext.restype = ctypes.c_int
    user32.SetProcessDPIAware.restype = ctypes.c_int


def _require_hwnd(hwnd: int) -> int:
    '''Проверяет дескриптор окна и возвращает его как int.'''
    if isinstance(hwnd, bool) or not isinstance(hwnd, int) or hwnd <= 0:
        raise WinApiError('Некорректный дескриптор окна: ' + repr(hwnd))
    return hwnd


def set_dpi_awareness() -> bool:
    '''Включает DPI-осведомлённость Per-Monitor V2.

    Вызывать до создания первого окна: иначе оверлей уедет на мониторах
    с разным масштабом. Возвращает True при успехе.
    '''
    if not is_available():
        return False
    user32 = _lib()
    try:
        result = user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        )
        if result:
            return True
    except (AttributeError, OSError):
        pass
    try:
        return bool(user32.SetProcessDPIAware())
    except (AttributeError, OSError):
        return False


def foreground_window() -> int:
    '''Дескриптор активного окна или 0, если активного окна нет.'''
    if not is_available():
        return 0
    hwnd = _lib().GetForegroundWindow()
    return int(hwnd) if hwnd else 0


def find_window_by_class(class_name: str) -> int:
    '''Ищет окно по имени класса и возвращает его дескриптор (0 — не найдено).'''
    if not isinstance(class_name, str) or not class_name:
        raise WinApiError('Имя класса окна должно быть непустой строкой')
    if not is_available():
        return 0
    hwnd = _lib().FindWindowW(ctypes.c_wchar_p(class_name), None)
    return int(hwnd) if hwnd else 0


def enum_windows() -> list[int]:
    '''Перечисляет все окна верхнего уровня и возвращает их дескрипторы.

    Порядок совпадает с Z-порядком системы: первыми идут активные окна.
    '''
    if not is_available():
        return []
    user32 = _lib()
    found: list[int] = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ssize_t, ctypes.c_ssize_t)

    def callback(hwnd: int, _lparam: int) -> bool:
        found.append(int(hwnd))
        return True

    callback_ref = proc_type(callback)  # держим ссылку: ctypes не хранит её сам
    user32.EnumWindows.argtypes = [proc_type, ctypes.c_ssize_t]
    user32.EnumWindows.restype = ctypes.c_bool
    user32.EnumWindows(callback_ref, 0)
    return found


def is_window(hwnd: int) -> bool:
    '''True, если дескриптор указывает на существующее окно.'''
    hwnd = _require_hwnd(hwnd)
    return bool(_lib().IsWindow(ctypes.c_void_p(hwnd)))


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    '''Прямоугольник окна (left, top, right, bottom) или None.'''
    hwnd = _require_hwnd(hwnd)
    rect = RECT()
    if not _lib().GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
        return None
    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))


def window_title(hwnd: int) -> str:
    '''Заголовок окна; пустая строка, если заголовка нет.'''
    hwnd = _require_hwnd(hwnd)
    user32 = _lib()
    length = int(user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd)))
    if length <= 0:
        return ''
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(ctypes.c_void_p(hwnd), buffer, length + 1)
    return buffer.value


def window_class(hwnd: int) -> str:
    '''Имя класса окна; пустая строка, если получить не удалось.'''
    hwnd = _require_hwnd(hwnd)
    buffer = ctypes.create_unicode_buffer(256)
    length = int(_lib().GetClassNameW(ctypes.c_void_p(hwnd), buffer, 256))
    if length <= 0:
        return ''
    return buffer.value


def is_minimized(hwnd: int) -> bool:
    '''True, если окно свёрнуто.'''
    hwnd = _require_hwnd(hwnd)
    return bool(_lib().IsIconic(ctypes.c_void_p(hwnd)))


def is_window_visible(hwnd: int) -> bool:
    '''True, если окно видно на экране.'''
    hwnd = _require_hwnd(hwnd)
    user32 = _lib()
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_int
    return bool(user32.IsWindowVisible(ctypes.c_void_p(hwnd)))


def window_process_id(hwnd: int) -> int:
    '''Идентификатор процесса, владеющего окном; 0, если узнать не удалось.'''
    hwnd = _require_hwnd(hwnd)
    pid = ctypes.c_ulong(0)
    user32 = _lib()
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    return int(pid.value)


def window_process_image(hwnd: int) -> str:
    '''Путь к исполняемому файлу процесса-владельца окна.

    Возвращает пустую строку, если сведения получить не удалось: на
    системах без Windows или при отказе в доступе программа не падает.
    '''
    if not is_available():
        return ''
    pid = window_process_id(hwnd)
    if pid <= 0:
        return ''
    kernel32 = _kernel32()
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_wchar),
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ''
    try:
        size = ctypes.c_ulong(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            ctypes.c_void_p(handle), 0, buffer, ctypes.byref(size)
        ):
            return ''
        return buffer.value
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def make_click_through(hwnd: int) -> bool:
    '''Делает окно прозрачным для мыши и неактивируемым.

    Оверлей перестаёт перехватывать клики даже там, где флага Qt
    WindowTransparentForInput недостаточно. Возвращает True при успехе.
    '''
    hwnd = _require_hwnd(hwnd)
    user32 = _lib()
    user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    style = int(user32.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_EXSTYLE))
    if style <= 0:
        return False
    new_style = style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_EXSTYLE, new_style)
    return True


#: Код ошибки Windows: объект с таким именем уже существует.
ERROR_ALREADY_EXISTS = 183

#: Загруженная библиотека kernel32; создаётся при первом обращении.
_kernel32_lib: Any | None = None


def _kernel32() -> Any:
    '''Возвращает kernel32, загружая её при первом обращении (только Windows).'''
    global _kernel32_lib
    if not is_available():
        raise WinApiError('WinAPI доступен только в Windows, текущая система: ' + sys.platform)
    if _kernel32_lib is None:
        _kernel32_lib = ctypes.WinDLL('kernel32', use_last_error=True)
    return _kernel32_lib


def create_named_mutex(name: str) -> tuple[int, bool]:
    '''Создаёт именованный мьютекс Windows.

    Возвращает пару (дескриптор, первый_ли_это_экземпляр). Если мьютекс с
    таким именем уже существует, открывается он, и первый элемент пары равен
    False: значит, программа уже запущена в другом окне.
    '''
    if not isinstance(name, str) or not name:
        raise WinApiError('Имя мьютекса должно быть непустой строкой')
    kernel32 = _kernel32()
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    error_code = ctypes.get_last_error()
    if not handle:
        raise WinApiError('Не удалось создать мьютекс: ' + name)
    return (int(handle), error_code != ERROR_ALREADY_EXISTS)


def close_handle(handle: int) -> bool:
    '''Закрывает дескриптор Windows; True, если закрытие удалось.'''
    if not isinstance(handle, int) or handle <= 0:
        raise WinApiError('Некорректный дескриптор: ' + repr(handle))
    kernel32 = _kernel32()
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    return bool(kernel32.CloseHandle(ctypes.c_void_p(handle)))
