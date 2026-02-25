# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# Принудительно указываем путь к иконке
icon_file = 'icon.ico'
if not os.path.exists(icon_file):
    # Если иконки нет в текущей папке, ищем в src
    if os.path.exists(os.path.join('src', icon_file)):
        icon_file = os.path.join('src', icon_file)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icon.ico', '.'),
        ('openspeedtest_cli.py', '.'),
        ('speedtest_runner.py', '.'),
        ('.env', '.'),
    ],
    hiddenimports=[
        'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.filedialog',
        'tkcalendar', 'matplotlib', 'matplotlib.backends.backend_tkagg',
        'PIL', 'PIL._tkinter_finder', 'pystray', 'pystray._base', 'pystray._win32',
        'psutil', 'requests', 'sqlite3', 'threading', 'datetime', 'json', 'time',
        'os', 'sys', 'tempfile', 'subprocess', 'winreg', 'ctypes', 'logging',
        'traceback', '_strptime', 'tzdata',
    ],
    hookspath=[],
    runtime_hooks=['runtime_hook.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='speedwatch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    icon=icon_file
)