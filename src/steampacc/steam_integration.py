'''Внедрение цен в страницы магазина клиентa Steam.

Модуль держит подключение к отладочному порту steamwebhelper и следит
за открытыми страницами магазина. Каждой новой странице он добавляет
сценарий из :mod:`steampacc.inject`: тот рисует блок с ценами других
регионов прямо в карточке покупки. Сценарий добавляется двумя путями:
на будущие переходы (addScriptToEvaluateOnNewDocument) и в уже открытую
страницу (Runtime.evaluate).

Подключение живёт в графическом потоке Qt: WebSocket и таймеры —
асинхронные, интерфейс не блокируется. Сеть страницы Steam запрашивает
сама — SteamPACC цены не качает.
'''

from __future__ import annotations

import json
import time
from typing import Any

from . import cef
from .inject import INJECTED_SCRIPT

try:
    from PySide6.QtCore import QObject, QTimer, QUrl, Signal
    from PySide6.QtNetwork import QAbstractSocket
    from PySide6.QtWebSockets import QWebSocket
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

#: Как часто сканировать список страниц магазина, секунд.
SCAN_INTERVAL_SECONDS = 5.0

#: Сколько портов проверяется, если 8080 не отвечает.
PORT_SCAN_RANGE = 12

#: Через сколько секунд простаивающее подключение считается мёртвым.
IDLE_RECONNECT_SECONDS = 120


if QT_AVAILABLE:
    class StorePageConnection(QObject):
        '''Подключение к одной странице магазина.

        Хранит WebSocket и признак того, что сценарий уже добавлен.
        При обрыве связи объект удаляется, а сканер заведёт новый.
        '''

        def __init__(self, target: dict[str, Any], parent: QObject | None = None):
            super().__init__(parent)
            self.key = str(target.get('webSocketDebuggerUrl') or '')
            self.injected = False
            self.socket = QWebSocket()
            self.socket.setParent(self)
            self.socket.connected.connect(self._on_connected)
            self.socket.open(QUrl(self.key))

        def _on_connected(self) -> None:
            '''Добавляет сценарий на страницу: в будущие документы и в текущий.'''
            self._send('Page.enable')
            self._send('Page.addScriptToEvaluateOnNewDocument', {'source': INJECTED_SCRIPT})
            self._send('Runtime.evaluate', {'expression': INJECTED_SCRIPT + '; void 0;'})
            self._send('Runtime.evaluate', {
                'expression': cef.configure_expression(
                    self._currencies(), self._lang())})
            self.injected = True

        def _currencies(self) -> list[str]:
            '''Текущий список валют; берётся из родителя-интегратора.'''
            parent = self.parent()
            value = getattr(parent, '_currencies', None)
            if isinstance(value, list) and value:
                return [str(code) for code in value]
            return ['RUB', 'USD', 'EUR']

        def _lang(self) -> str:
            '''Текущий язык надписей; берётся из родителя-интегратора.'''
            parent = self.parent()
            value = getattr(parent, '_lang', None)
            return value if value in ('ru', 'en') else 'ru'

        def _send(self, method: str, params: dict[str, Any] | None = None) -> None:
            '''Отправляет команду DevTools; обрыв связи не ломает работу.'''
            if self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
                return
            message = {'id': 1, 'method': method, 'params': params or {}}
            try:
                self.socket.sendTextMessage(json_dumps(message))
            except (OSError, ValueError):
                pass

        def apply_currencies(self, currencies: list[str], lang: str = 'ru') -> None:
            '''Обновляет список валют и язык на уже внедрённой странице.'''
            if not self.injected:
                return
            self._send('Runtime.evaluate', {
                'expression': cef.configure_expression(currencies, lang)})

        def close(self) -> None:
            self.socket.close()


    def json_dumps(message: dict[str, Any]) -> str:
        '''Сериализует сообщение DevTools в текст.'''
        import json
        return json.dumps(message, ensure_ascii=False)


    class SteamIntegrator(QObject):
        '''Следит за страницами магазина и внедряет в них цены.'''

        status_changed = Signal(str)

        def __init__(self, parent: QObject | None = None):
            super().__init__(parent)
            self._enabled = True
            self._currencies: list[str] = ['RUB', 'USD', 'EUR']
            self._lang = 'ru'
            self._connections: dict[str, StorePageConnection] = {}
            self._port: int | None = None

            self._scan_timer = QTimer(self)
            self._scan_timer.timeout.connect(self._scan)
            self._scan_timer.start(int(SCAN_INTERVAL_SECONDS * 1000))

        def set_enabled(self, enabled: bool) -> None:
            '''Включает или выключает внедрение; при выключении связи рвутся.'''
            self._enabled = bool(enabled)
            if not self._enabled:
                self._drop_all()
            self.status_changed.emit('вкл' if self._enabled else 'выкл')

        def set_currencies(self, currencies: list[str], lang: str = 'ru') -> None:
            '''Применяет новый список валют ко всем открытым страницам.'''
            self._currencies = list(currencies)
            self._lang = lang if lang in ('ru', 'en') else 'ru'
            for connection in list(self._connections.values()):
                connection.apply_currencies(self._currencies, self._lang)

        def restart_steam_with_debug(self, steam_exe: str) -> bool:
            '''Перезапускает Steam с отладочным портом и возвращает успех.

            После запуска ждём, пока порт отладки Steam реально поднимется:
            без этого можно решить, что всё готово, а цены так и не появятся.
            '''
            import subprocess
            import time as time_module

            subprocess.Popen(
                [steam_exe, '-shutdown'],
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            deadline = time_module.time() + 30
            while time_module.time() < deadline:
                if not _steam_running():
                    break
                time_module.sleep(1)
            if _steam_running():
                self.status_changed.emit('Steam не закрылся за 30 секунд')
                return False
            subprocess.Popen(
                [steam_exe, '-cef-enable-debugging', '-silent'],
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            self.status_changed.emit('Steam перезапускается, ждём порт…')
            port_deadline = time_module.time() + 60
            while time_module.time() < port_deadline:
                if cef.is_steam_devtools(cef.DEFAULT_DEBUG_PORT):
                    self.status_changed.emit('Steam с ценами: готово')
                    return True
                time_module.sleep(2)
            self.status_changed.emit('Порт отладки не поднялся за 60 секунд')
            return False

        def _drop_all(self) -> None:
            for connection in list(self._connections.values()):
                connection.close()
            self._connections.clear()
            self._port = None

        def _scan(self) -> None:
            '''Раз в несколько секунд: новые страницы подключить, мёртвые убрать.'''
            if not self._enabled:
                return
            try:
                if self._port is None or not cef.debug_available(self._port):
                    self._port = self._find_port()
                    if self._port is None:
                        self.status_changed.emit('Steam без отладки')
                        return
                targets = cef.store_targets(cef.fetch_targets(self._port))
            except OSError:
                self.status_changed.emit('Steam недоступен')
                return

            alive_keys = set()
            for target in targets:
                key = str(target.get('webSocketDebuggerUrl') or '')
                if not key:
                    continue
                alive_keys.add(key)
                connection = self._connections.get(key)
                if connection is None:
                    connection = StorePageConnection(target, self)
                    self._connections[key] = connection
                    self.status_changed.emit('страниц: ' + str(len(self._connections)))
                elif connection.injected:
                    # Список валют мог обновиться: повторная настройка безвредна.
                    connection.apply_currencies(self._currencies, self._lang)

            for key in list(self._connections):
                if key not in alive_keys:
                    self._connections.pop(key).close()

        def _find_port(self) -> int | None:
            '''Ищет отладочный порт steamwebhelper: 8080 и соседние.

            На каждом порту проверяется, что это именно Steam (по
            User-Agent), чтобы не подключиться к чужому DevTools.
            '''
            start = cef.DEFAULT_DEBUG_PORT
            for port in range(start, start + PORT_SCAN_RANGE):
                if cef.is_steam_devtools(port):
                    return port
            return None


def _steam_running() -> bool:
    '''True, если процесс steam.exe сейчас запущен.'''
    import ctypes
    import ctypes.wintypes

    if not hasattr(ctypes, 'windll'):
        return False
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot:
        return False

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', ctypes.c_ulong),
            ('cntUsage', ctypes.c_ulong),
            ('th32ProcessID', ctypes.c_ulong),
            ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
            ('th32ModuleID', ctypes.c_ulong),
            ('cntThreads', ctypes.c_ulong),
            ('th32ParentProcessID', ctypes.c_ulong),
            ('pcPriClassBase', ctypes.c_long),
            ('dwFlags', ctypes.c_ulong),
            ('szExeFile', ctypes.c_char * 260),
        ]

    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    found = False
    if kernel32.Process32First(snapshot, ctypes.byref(entry)):
        while True:
            if entry.szExeFile.decode('utf-8', errors='ignore').lower() == 'steam.exe':
                found = True
                break
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snapshot)
    return found
