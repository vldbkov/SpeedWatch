# -*- coding: utf-8 -*-
"""
PyInstaller hook для pystray
Обеспечивает корректную сборку иконки в трее для EXE
"""

from PyInstaller.utils.hooks import collect_submodules

# pystray использует PIL и требует скрытые импорты
hiddenimports = [
    'pystray',
    'pystray._base',
    'pystray._win32',
    'PIL',
    'PIL._tkinter_finder',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageTk',
]

# Собираем все подмодули PIL (но без ошибок)
try:
    pil_modules = collect_submodules('PIL')
    for module in pil_modules:
        if module not in hiddenimports:
            hiddenimports.append(module)
except:
    pass

# НЕ добавляем pystray._win32._win32 - его нет!