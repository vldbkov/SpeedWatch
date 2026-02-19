# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files

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
        (icon_file, '.'),
        ('openspeedtest-cli-fixed', '.'),
    ],
    hiddenimports=[
        'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.filedialog',
        'tkcalendar', 'matplotlib', 'matplotlib.backends.backend_tkagg',
        'PIL', 'PIL._tkinter_finder', 'pystray', 'pystray._base', 'pystray._win32',
        'psutil', 'requests', 'sqlite3', 'threading', 'datetime', 'json', 'time',
        'os', 'sys', 'tempfile', 'subprocess', 'winreg', 'ctypes', 'logging',
        'traceback', '_strptime', 'tzdata',
    ],
    hookspath=['.'],
    hooksconfig={},
    runtime_hooks=['runtime_hook.py'],
    excludes=[],
    noarchive=False,
)

# Добавляем данные для matplotlib
datas_matplotlib = collect_data_files('matplotlib')
for data in datas_matplotlib:
    if data not in a.datas:
        a.datas.append(data)

pyz = PYZ(a.pure, a.zipped_data)

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

exe_windowed = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='speedwatch_w',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=icon_file
)