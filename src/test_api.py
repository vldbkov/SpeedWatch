import sys
import os

# Добавляем текущую директорию в путь Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # Импортируем правильное имя файла
    import openspeedtest as ost
    print("Модуль openspeedtest успешно импортирован")
except ImportError as e:
    print(f"Ошибка импорта модуля openspeedtest: {e}")
    print("Проверьте наличие файла openspeedtest.py в папке src/")
    sys.exit(1)

# Читаем API ключ из .env
api_key = None
try:
    env_path = '.env'
    with open(env_path, 'r') as f:
        for line in f:
            if line.startswith("OPENSPEEDTEST_API_KEY="):
                api_key = line.strip().split("=", 1)[1]
                break
except Exception as e:
    print(f"Ошибка чтения .env: {e}")

if not api_key:
    print("API ключ не найден. Добавьте в .env: OPENSPEEDTEST_API_KEY=ваш_ключ")
    sys.exit(1)

# Конфиг для функции
config = {"api_key": api_key}

# Получаем серверы
try:
    print("Получаем список серверов...")
    servers = ost.fetch_servers_from_api(config)
    print(f"Получено серверов: {len(servers)}")
    for server in servers[:3]:  # Показываем первые 3
        print(f"  - {server['name']} ({server.get('sponsor', 'N/A')})")
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()