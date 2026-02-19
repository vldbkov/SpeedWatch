# -*- coding: utf-8 -*-
"""
Runtime hook для PyInstaller
Выполняется сразу при запуске скомпилированного EXE
"""

import sys
import os

# Принудительно устанавливаем UTF-8 для консоли
if hasattr(sys, 'frozen'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        # Для старых версий Python
        try:
            sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
            sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)
        except:
            pass

# Устанавливаем переменные окружения для корректной работы
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

# Регистрируем пути для ресурсов
if hasattr(sys, 'frozen'):
    # Базовая директория EXE
    base_dir = os.path.dirname(sys.executable)
    
    # Директория для данных приложения в AppData
    appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'SpeedWatch')
    data_dir = os.path.join(appdata_dir, 'data')
    
    # Создаем директории если их нет
    os.makedirs(data_dir, exist_ok=True)
    
    # Сохраняем пути в глобальных переменных для доступа из main.py
    sys._MEIPASS_data = data_dir
    sys._MEIPASS_base = base_dir