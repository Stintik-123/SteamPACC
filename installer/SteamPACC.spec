# -*- mode: python ; coding: utf-8 -*-
"""Спецификация PyInstaller для SteamPACC.

Собирает один исполняемый файл (onefile) для Windows:

* обычный вариант — без окна консоли, программа работает в трее;
* консольный вариант — с окном консоли, удобно для диагностики.

Консольный вариант включается переменной окружения STEAMPACC_CONSOLE=1.
Примеры запуска из корня проекта:

    pyinstaller --noconfirm --clean --distpath dist --workpath build installer/SteamPACC.spec
    STEAMPACC_CONSOLE=1 pyinstaller --noconfirm --clean --distpath dist --workpath build installer/SteamPACC.spec
"""

import os

# SPECPATH задаётся PyInstaller и указывает на папку с этим файлом.
# Если по какой-то причине его нет, считаем, что сборка идёт из корня проекта.
_spec_dir = globals().get('SPECPATH') or os.path.join(os.getcwd(), 'installer')

# Корень проекта — на уровень выше папки installer.
ROOT = os.path.abspath(os.path.join(_spec_dir, os.pardir))
SRC = os.path.join(ROOT, 'src')
ENTRY = os.path.join(SRC, 'steampacc', '__main__.py')

# Консольный вариант включается переменной окружения.
CONSOLE = os.environ.get('STEAMPACC_CONSOLE', '').strip() == '1'
NAME = 'SteamPACC-Console' if CONSOLE else 'SteamPACC'

a = Analysis(
    [ENTRY],
    pathex=[SRC],
    binaries=[],
    # Значок приложения: трей и окно настроек грузят его из ресурсов.
    datas=[(os.path.join(SRC, 'steampacc', 'assets', 'steampacc.ico'), 'assets')],
    # Модули, которые импортируются внутри функций: подсказываем
    # PyInstaller, что их нельзя выкинуть при анализе импортов.
    hiddenimports=[
        'steampacc',
        'steampacc.app',
        'steampacc.diagnostics',
        'steampacc.selftest',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Эти модули программе не нужны, но тянут за собой лишние мегабайты.
    excludes=['tkinter', 'PyQt5', 'PyQt6'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=NAME,
    icon=os.path.join(SRC, 'steampacc', 'assets', 'steampacc.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX на сборщике может отсутствовать, поэтому не включаем сжатие.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
