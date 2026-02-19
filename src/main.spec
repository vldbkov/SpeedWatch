# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icon.ico', '.'),
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
    icon='icon.ico'
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
    icon='icon.ico'
)