#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модифицированный librespeed-cli (https://github.com/librespeed/speedtest-cli)
для интеграции с OpenSpeedTest.ru API.

Этот скрипт использует только стандартные библиотеки Python 3.
"""

import sys
import os
import json
import hmac
import hashlib
import time
import threading
import urllib.request
import urllib.parse # Добавляем для сборки URL
import ssl
from queue import Queue
import math
import argparse # Используем argparse для удобства
import statistics # <-- ДОБАВЛЕНО для медианы
import io

# Устанавливаем кодировку для Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ---
# Глобальные переменные и конфигурация
# ---
API_BASE_URL = "https://openspeedtest.ru"

# Пути к конфигурации
CONFIG_DIR_NAME = ".config"
CONFIG_APP_NAME = "openspeedtest-cli"
CONFIG_FILE_NAME = "config.json"

# ---
# NOTE 1 (БЕЗОПАСНОСТЬ): Отключить проверку SSL по умолчанию.
# ---
ssl_context = None # Глобальный контекст
try:
    ssl_context = ssl._create_unverified_context()
except AttributeError:
    print("Внимание: не удалось создать непроверяемый SSL-контекст. Тест может не удаться.", file=sys.stderr)
    ssl_context = ssl.create_default_context()


# ---
# Функции Спиннера (для UX)
# ---
spinner_running = False
spinner_chars = ['-', '\\', '|', '/']

def spinner(label=""):
    """Поток для отображения спиннера."""
    global spinner_running
    i = 0
    while spinner_running:
        char = spinner_chars[i % len(spinner_chars)]
        sys.stdout.write(f'\r{label} {char} ')
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1

def start_spinner(label=""):
    """Запускает спиннер в отдельном потоке."""
    global spinner_running
    if sys.stdout.isatty(): # Запускаем спиннер только в TTY
        spinner_running = True
        t = threading.Thread(target=spinner, args=(label,))
        t.daemon = True
        t.start()
        return t
    else:
        print(f"{label}...") # Просто выводим текст, если это не TTY
        return None

def stop_spinner(spinner_thread, success=True, message=""):
    """Останавливает спиннер и выводит сообщение."""
    global spinner_running
    if spinner_thread:
        spinner_running = False
        spinner_thread.join()
    
    if sys.stdout.isatty():
        sys.stdout.write('\r\033[K') # Очищаем строку
    
    if message:
        if success:
            print(f"OK {message}")  # Было: ✓
        else:
            print(f"ERR {message}", file=sys.stderr)  # Было: ✗
    sys.stdout.flush()


# ---
# Управление конфигурацией (~/.config/openspeedtest-cli/config.json)
# ---

def get_config_path():
    """Получает правильный путь к файлу конфигурации."""
    try:
        home_dir = os.environ.get("HOME") or os.path.expanduser("~")
        if not home_dir:
            raise EnvironmentError("$HOME не установлен и os.path.expanduser('~') не сработал.")
        config_dir_path = os.path.join(home_dir, CONFIG_DIR_NAME, CONFIG_APP_NAME)
        return os.path.join(config_dir_path, CONFIG_FILE_NAME)
    except Exception as e:
        print(f"Критическая ошибка: Не удалось определить домашнюю директорию: {e}", file=sys.stderr)
        sys.exit(1)

def load_config():
    """Загружает API-ключ из файла конфигурации."""
    config_path = get_config_path()
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        return config_data
    except Exception as e:
        print(f"Внимание: Не удалось прочитать файл конфигурации ({config_path}): {e}", file=sys.stderr)
        return None

def save_config(api_key):
    """Сохраняет API-ключ в файл."""
    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)
    try:
        os.makedirs(config_dir, mode=0o750, exist_ok=True)
        config_data = {"api_key": api_key}
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        os.chmod(config_path, 0o600)
        print(f"\nКонфигурация успешно сохранена в: {config_path}")
    except Exception as e:
        print(f"\nКритическая ошибка: Не удалось сохранить конфигурацию: {e}", file=sys.stderr)
        sys.exit(1)

def handle_configure():
    """Обрабатывает команду 'configure'."""
    try:
        api_key = input("Введите ваш API-ключ (64 символа): ").strip()
        if len(api_key) != 64 or not all(c in '0123456789abcdef' for c in api_key):
            print("Ошибка: API-ключ выглядит неверно.", file=sys.stderr)
            sys.exit(1)
        save_config(api_key)
    except KeyboardInterrupt:
        print("\nОтмена.", file=sys.stderr)
        sys.exit(1)


# ---
# Функции API (взаимодействие с openspeedtest.ru)
# ---

def fix_protocol_relative_url(url):
    """Добавляет https: к URL, если он начинается с // или не имеет протокола"""
    if url and url.startswith("//"):
        return "https:" + url
    if url and not url.startswith(("http:", "https:")):
        # Проверяем, похоже ли это на доменное имя (упрощенно)
        # Добавляем "//" чтобы urljoin работал правильно, если это просто домен
        if '.' in url and '/' not in url.split('.')[0]:
             return "https:" + "//" + url
    return url

def make_request(url, headers=None, data=None, timeout=10):
    """Универсальная функция для HTTP-запросов."""
    global ssl_context
    fixed_url = fix_protocol_relative_url(url) # Исправляем URL здесь
    if not fixed_url:
        # print(f"[DEBUG] make_request received invalid URL: {url}", file=sys.stderr)
        return None, 999 # Возвращаем кастомный код ошибки, если URL невалидный

    try:
        # print(f"[DEBUG] Making request to: {fixed_url}", file=sys.stderr) # Для отладки URL
        req = urllib.request.Request(fixed_url, headers=headers or {}, data=data, method='POST' if data else 'GET')
        with urllib.request.urlopen(req, context=ssl_context, timeout=timeout) as response:
            return response.read(), response.getcode()
    except Exception as e:
        # print(f"[DEBUG] make_request failed for {fixed_url}: {e}", file=sys.stderr) # Для отладки ошибок
        # Возвращаем None и код ошибки (если есть) или 500
        return None, getattr(e, 'code', 500)

def fetch_servers_from_api(config): # <--- ИЗМЕНЕНИЕ: Принимаем config
    """Получает список серверов с нашего API."""
    url = f"{API_BASE_URL}/api.php?action=get-servers"
    
    # --- НОВОЕ ИЗМЕНЕНИЕ ---
    api_key = config.get("api_key")
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    
    spinner = start_spinner("Получение списка серверов...")
    body, status = make_request(url, headers=headers) # <--- ИЗМЕНЕНИЕ: Передаем headers
    
    if status != 200 or not body:
        stop_spinner(spinner, False, f"Ошибка загрузки серверов (Статус: {status})")
        sys.exit(1)
    try:
        servers = json.loads(body.decode('utf-8'))
        if not servers:
            stop_spinner(spinner, False, "Список серверов пуст.")
            sys.exit(1)
        stop_spinner(spinner, True, "Список серверов получен.")
        formatted_servers = []
        for s in servers:
            # Исправляем базовый URL сервера прямо при загрузке
            base_url = fix_protocol_relative_url(s.get('server_url'))
            if not base_url:
                 # print(f"Внимание: Невалидный базовый URL для сервера ID {s.get('id')}: {s.get('server_url')}. Пропускаем.", file=sys.stderr)
                 continue # Пропускаем сервер с невалидным URL

            formatted_servers.append({
                'id': s.get('id'),
                'name': s.get('name'),
                'server': base_url, # Исправленный базовый URL сервера
                'dlURL': s.get('dl_url', 'garbage.php'),     # Путь к файлу скачивания (относительный), с дефолтом
                'ulURL': s.get('ul_url', 'empty.php'),     # Путь к файлу загрузки (относительный), с дефолтом
                'pingURL': s.get('ping_url', 'empty.php'), # Путь к файлу пинга (относительный), с дефолтом
                'sponsor': s.get('sponsor_name', '')
            })
        return formatted_servers
    except json.JSONDecodeError as e:
        stop_spinner(spinner, False, f"Ошибка парсинга списка серверов: {e}")
        sys.exit(1)

def submit_result_to_api(result, config):
    """Отправляет результат на наш API с HMAC-подписью."""
    api_key = config.get("api_key")
    if not api_key:
        print("Внимание: API-ключ не найден. Результаты не будут отправлены.", file=sys.stderr)
        return

    spinner = start_spinner("Отправка результатов на сервер...")
    ts = str(int(time.time()))
    # Убедимся, что значения числовые перед форматированием
    try:
        dl = float(result['download'])
        ul = float(result['upload'])
        ping = float(result['ping'])
        jitter = float(result['jitter'])
    except (ValueError, TypeError):
        stop_spinner(spinner, False, "Ошибка: Некорректные числовые значения в результатах.")
        return

    data_string = f"dl={dl:.2f}:ul={ul:.2f}:ping={ping:.2f}:jitter={jitter:.2f}:timestamp={ts}"
    try:
        signature = hmac.new(api_key.encode('utf-8'), data_string.encode('utf-8'), hashlib.sha256).hexdigest()
    except Exception as e:
        stop_spinner(spinner, False, f"Ошибка создания HMAC: {e}")
        return

    payload = {"dl": dl, "ul": ul, "ping": ping, "jitter": jitter, "timestamp": ts}
    json_payload = json.dumps(payload).encode('utf-8')
    headers = {"Content-Type": "application/json", "X-API-Key": api_key, "X-Signature": signature}
    url = f"{API_BASE_URL}/api.php?action=submit-result"
    body, status = make_request(url, headers=headers, data=json_payload, timeout=20)
    
    if status == 200:
        stop_spinner(spinner, True, "Результаты успешно сохранены. Спасибо!")
    else:
        error_msg = f"Ошибка сохранения результатов (Статус: {status})"
        if body:
            try:
                error_data = json.loads(body.decode('utf-8'))
                error_msg += f": {error_data.get('error', 'Неизвестная ошибка')}"
            except json.JSONDecodeError: pass
        stop_spinner(spinner, False, error_msg)

# ---
# Ядро Librespeed (адаптированное)
# ---

# Глобальная переменная для worker, чтобы знать, какой тип теста идет
current_phase_for_worker = None

def worker(url, q, stop_event):
    """Рабочий поток для скачивания/загрузки (логика librespeed)."""
    global ssl_context, current_phase_for_worker
    # URL уже должен быть полным и исправленным на этапе вызова worker
    if not url: return # Проверка на пустой URL

    try:
        # Буфер создаем один раз
        buffer = os.urandom(1 * 1024 * 1024) if current_phase_for_worker == "upload" else None

        while not stop_event.is_set():
            start_time = time.monotonic()
            # Добавляем случайный параметр к полному URL
            full_url_with_param = f"{url}?r={time.time()}"
            data_to_send = None
            headers = {}

            if current_phase_for_worker == "upload":
                data_to_send = buffer
                headers["Content-Type"] = "application/octet-stream"

            req = urllib.request.Request(full_url_with_param, data=data_to_send, headers=headers, method='POST' if data_to_send else 'GET')
            
            with urllib.request.urlopen(req, context=ssl_context, timeout=15) as response:
                if current_phase_for_worker == "upload":
                    # Для upload нам не нужно читать ответ, только убедиться, что он успешный
                    _ = response.read() # Читаем, чтобы закрыть соединение
                    if 200 <= response.getcode() < 300:
                        end_time = time.monotonic()
                        q.put(end_time - start_time) # Отправляем время выполнения запроса
                    # else: # Ошибка сервера при upload
                        # print(f"[DEBUG] Upload worker received status {response.getcode()} for {full_url_with_param}", file=sys.stderr)

                else: # Download
                    total_read = 0
                    while not stop_event.is_set():
                        # Читаем чанками
                        chunk = response.read(1024 * 1024) # Читаем до 1MB за раз
                        if not chunk:
                            break # Загрузка завершена
                        total_read += len(chunk)
                    end_time = time.monotonic()
                    if total_read > 0: # Только если что-то скачали
                         q.put((end_time - start_time, total_read)) # Отправляем (время, байты)
            # Добавим небольшую паузу, чтобы не перегружать сервер пустыми запросами, если что-то пошло не так
            # time.sleep(0.01)

    except Exception as e:
        # print(f"[DEBUG] Worker error for {url} ({current_phase_for_worker}): {e}", file=sys.stderr) # Отладка ошибок worker
        pass


def run_test_phase(phase, server, duration, threads):
    """Общая функция для теста скачивания или загрузки."""
    global current_phase_for_worker # Объявляем, что будем менять глобальную переменную
    q = Queue()
    stop_event = threading.Event()
    
    current_phase_for_worker = phase # Устанавливаем фазу для worker
    
    if phase == "download":
        url_key = 'dlURL'
        label = "Download"
    elif phase == "upload":
        url_key = 'ulURL'
        label = "Upload"
    else:
        return 0.0

    # Собираем полный URL, base_url уже исправлен при загрузке
    base_url = server.get('server')
    # Используем путь из БД, соответствующий фазе теста
    path = server.get(url_key)

    if not base_url or not path:
        print(f"[DEBUG] Отсутствует base_url ('{base_url}') или path ('{path}') для {phase} сервера {server.get('name')}", file=sys.stderr)
        return 0.0

    # Собираем полный URL, используя urljoin
    full_test_url = urllib.parse.urljoin(base_url, path)

    if not full_test_url:
         print(f"[DEBUG] Не удалось собрать URL для {phase} для сервера {server['name']}", file=sys.stderr)
         return 0.0

    worker_threads = []
    for _ in range(threads):
        # Передаем исправленный полный URL в worker
        t = threading.Thread(target=worker, args=(full_test_url, q, stop_event))
        t.daemon = True
        t.start()
        worker_threads.append(t)
        
    start_time = time.monotonic()
    total_downloaded_bytes = 0
    total_upload_requests = 0
    
    while True:
        elapsed = time.monotonic() - start_time
        if elapsed >= duration:
            stop_event.set()
            break
            
        # Обрабатываем данные из очереди
        while not q.empty():
            try:
                if phase == "download":
                    _, downloaded_bytes = q.get(timeout=0.01)
                    total_downloaded_bytes += downloaded_bytes
                else: # Upload
                    _ = q.get(timeout=0.01) # Время запроса, нам не нужно
                    total_upload_requests += 1
            except Exception: pass # Игнорируем ошибки очереди

        # Вычисляем и отображаем скорость
        current_speed_mbps = 0.0
        if elapsed > 0:
            if phase == "download":
                if total_downloaded_bytes > 0:
                    current_speed_mbps = (total_downloaded_bytes * 8) / (elapsed * 1000 * 1000)
            else: # Upload
                if total_upload_requests > 0:
                    # Считаем, что каждый успешный запрос отправил 1MB
                    total_uploaded_bytes = total_upload_requests * 1024 * 1024
                    current_speed_mbps = (total_uploaded_bytes * 8) / (elapsed * 1000 * 1000)
            
            # Обновляем строку вывода, если скорость изменилась
            sys.stdout.write(f'\r{label}: {current_speed_mbps:10.2f} Mbps')
            sys.stdout.flush()
        
        # Небольшая пауза, чтобы не загружать CPU
        time.sleep(0.05)
        
    # Даем немного времени рабочим потокам завершиться после установки stop_event
    time.sleep(0.2)

    # Собираем оставшиеся данные из очереди после остановки
    while not q.empty():
        try:
            if phase == "download":
                _, downloaded_bytes = q.get(timeout=0.01)
                total_downloaded_bytes += downloaded_bytes
            else: # Upload
                _ = q.get(timeout=0.01)
                total_upload_requests += 1
        except Exception: pass

    # Ждем завершения всех потоков (хотя они daemon, это хорошая практика)
    # for t in worker_threads:
    #     t.join(timeout=0.5) # Даем полсекунды на завершение

    # Финальный расчет скорости
    final_elapsed = time.monotonic() - start_time
    final_speed_mbps = 0.0
    if final_elapsed > 0:
        if phase == "download":
             if total_downloaded_bytes > 0:
                final_speed_mbps = (total_downloaded_bytes * 8) / (final_elapsed * 1000 * 1000)
        else: # Upload
            if total_upload_requests > 0:
                total_uploaded_bytes = total_upload_requests * 1024 * 1024
                final_speed_mbps = (total_uploaded_bytes * 8) / (final_elapsed * 1000 * 1000)
    ###
    # Выводим финальную скорость в новой строке
    sys.stdout.write(f'\r{label}: {final_speed_mbps:10.2f} Mbps\n')
    sys.stdout.flush()
    return final_speed_mbps

def download_test(server, duration, threads):
    result = run_test_phase("download", server, duration, threads)
    sys.stdout.write('\n')  # Добавляем перевод строки после теста скачивания
    return result

def upload_test(server, duration, threads):
    result = run_test_phase("upload", server, duration, threads)
    sys.stdout.write('\n')  # Добавляем перевод строки после теста загрузки
    return result

def try_ping_url(full_url):
    """Пытается выполнить один GET-запрос к URL для пинга."""
    global ssl_context
    start_time = time.monotonic()
    if not full_url: return None # Проверка на пустой URL

    try:
        # Добавляем случайный параметр
        full_url_with_param = f"{full_url}?r={time.time()}"
        req = urllib.request.Request(full_url_with_param, method='GET')
        with urllib.request.urlopen(req, context=ssl_context, timeout=5) as response:
            # ИЗМЕНЕНИЕ: Читаем больше байт
            _ = response.read(1024)
            # Проверяем статус код (2xx считается успехом)
            if 200 <= response.getcode() < 300:
                latency = (time.monotonic() - start_time) * 1000 # в мс
                return latency
            else:
                # Сервер ответил, но с ошибкой (например, 404)
                # print(f"[DEBUG] Ping attempt received status {response.getcode()} for {full_url_with_param}", file=sys.stderr)
                return None
    except Exception as e:
        # Убираем [DEBUG] вывод отсюда
        # print(f"[DEBUG] Ping attempt failed for ({full_url_with_param}): {e}", file=sys.stderr)
        return None # Возвращаем None при любой ошибке (таймаут, SSL и т.д.)

def measure_ping_and_jitter(server, count=10):
    """Измеряет пинг и джиттер, используя ТОЛЬКО пути из БД."""
    base_url = server.get('server')
    if not base_url: return -1, -1

    # ИСПРАВЛЕНИЕ: Используем только пути из БД
    ping_path = server.get('pingURL')
    dl_path = server.get('dlURL') # Резервный путь

    ping_url_full = None
    
    # Сначала пробуем pingURL
    if ping_path:
        potential_url = urllib.parse.urljoin(base_url, ping_path)
        # Проверяем доступность URL перед измерением
        if try_ping_url(potential_url) is not None:
            ping_url_full = potential_url
            
    # Если pingURL не сработал или его не было, пробуем dlURL
    if not ping_url_full and dl_path:
        potential_url = urllib.parse.urljoin(base_url, dl_path)
        # Проверяем доступность URL перед измерением
        if try_ping_url(potential_url) is not None:
            ping_url_full = potential_url

    # Если ни один из путей не сработал
    if not ping_url_full:
         # print(f"[DEBUG] Не удалось найти рабочий URL для пинга (pingURL:'{ping_path}', dlURL:'{dl_path}') для сервера {server['name']}", file=sys.stderr)
         return -1, -1

    latencies = []
    
    # Теперь измеряем пинг count раз, используя найденный рабочий URL
    for i in range(count):
        latency = try_ping_url(ping_url_full)
        if latency is not None:
            latencies.append(latency)
        # ИЗМЕНЕНИЕ: Уменьшаем паузу
        if count > 1:
             time.sleep(0.02 if i < count - 1 else 0) # Не спим после последнего

    if not latencies:
        # Ошибка будет выведена только если ни один из count пингов не удался
        # print(f"[DEBUG] Ни один из {count} пингов не удался для {server['name']} ({ping_url_full})", file=sys.stderr)
        return -1, -1
    
    # ИЗМЕНЕНИЕ: Используем медиану для пинга
    ping = statistics.median(latencies)
    
    # Jitter (RMS), рассчитывается только если есть больше одного успешного пинга
    jitter = 0.0
    if len(latencies) > 1:
        # Используем рассчитанный пинг (медиану) для расчета джиттера
        sum_sq_diff = sum([(l - ping) ** 2 for l in latencies])
        jitter = math.sqrt(sum_sq_diff / len(latencies)) # Делим на N
    
    return ping, jitter

def find_best_server(servers):
    """Находит лучший сервер по пингу."""
    spinner = start_spinner("Поиск лучшего сервера (проверка пинга)...")
    best_ping = float('inf')
    best_server = None
    tested_servers = 0
    successful_pings = 0
    
    results = [] # [(ping, server_object), ...]

    # Сначала измеряем пинг для всех серверов
    for server in servers:
        # Уменьшаем количество пингов для выбора до 3 для скорости
        ping, _ = measure_ping_and_jitter(server, count=3)
        if ping != -1: # Учитываем только успешные пинги
             successful_pings += 1
             results.append((ping, server))
        tested_servers += 1
            
    if not results: # Если ни один сервер не ответил
        error_msg = "Не удалось найти доступный сервер."
        if tested_servers > 0:
             error_msg += f" Ни один из {tested_servers} серверов не ответил на пинг."
        stop_spinner(spinner, False, error_msg)
        sys.exit(1)

    # Сортируем результаты по пингу
    results.sort(key=lambda x: x[0])
    
    # Берем лучший сервер из отсортированного списка
    best_ping_initial, best_server = results[0]
        
    # Уточняем пинг и джиттер для выбранного сервера (10 раз)
    final_ping, final_jitter = measure_ping_and_jitter(best_server, count=10)
    
    if final_ping != -1:
        best_server['ping'] = final_ping
        best_server['jitter'] = final_jitter
        stop_spinner(spinner, True, f"Лучший сервер найден: {best_server['name']} ({final_ping:.2f} мс)")
        return best_server
    else:
         # Если уточнение не удалось, возвращаем ошибку
        stop_spinner(spinner, False, f"Не удалось измерить финальный пинг для выбранного сервера {best_server['name']}.")
        sys.exit(1)


def list_servers(servers):
    """Выводит список серверов."""
    print("Доступные серверы:")
    print("-" * 70) # Увеличим ширину
    print(f"{'ID':<5} | {'Название':<35} | {'Спонсор':<25}")
    print("-" * 70)
    for s in servers:
        # Обрезаем длинные названия
        name = s.get('name', 'N/A')
        sponsor = s.get('sponsor', 'N/A')
        if len(name) > 35: name = name[:32] + "..."
        if len(sponsor) > 25: sponsor = sponsor[:22] + "..."
        print(f"{s.get('id', 'N/A'):<5} | {name:<35} | {sponsor:<25}")
    print("-" * 70)

# ---
# Main
# ---

def main():
    parser = argparse.ArgumentParser(
        description="OpenSpeedTest.ru CLI - Проверка скорости из командной строки.",
        epilog="Этот инструмент является модификацией librespeed-cli для работы с API openspeedtest.ru"
    )
    subparsers = parser.add_subparsers(dest='command', help="Доступные команды")
    subparsers.add_parser('configure', help='Настроить API-ключ для отправки результатов.')
    
    parser.add_argument('--server', type=int, help='ID сервера для теста (иначе - автовыбор).')
    parser.add_argument('--list-servers', action='store_true', help='Показать список доступных серверов и выйти.')
    parser.add_argument('--no-submit', action='store_true', help='Провести тест без отправки результатов на сервер.')
    parser.add_argument('--api-key', type=str, help='Временно использовать этот API-ключ (не сохраняется).')
    parser.add_argument('--threads', type=int, default=8, help='Количество потоков для теста (по умолч: 8).')
    parser.add_argument('--duration', type=int, default=10, help='Длительность теста (скачивание/загрузка) в сек (по умолч: 10).')
    
    args = parser.parse_args()
    
    if args.command == 'configure':
        handle_configure()
        sys.exit(0)
        
    config = load_config() or {}
    if args.api_key:
        if len(args.api_key) == 64 and all(c in '0123456789abcdef' for c in args.api_key):
             config['api_key'] = args.api_key
        else:
            print("Внимание: Указанный --api-key невалиден. Игнорируется.", file=sys.stderr)
            # Не выходим, просто не используем ключ
            
    if not config.get('api_key') and not args.no_submit:
        print("Внимание: API-ключ не настроен. Результаты не будут отправлены.", file=sys.stderr)
        print("Чтобы это исправить, выполните: openspeedtest-cli configure", file=sys.stderr)
        args.no_submit = True # Принудительно отключаем отправку
        
    servers = fetch_servers_from_api(config) # <--- ИЗМЕНЕНИЕ: Передаем config
    
    if args.list_servers:
        list_servers(servers)
        sys.exit(0)
    
    server = None
    ping = -1
    jitter = -1

    if args.server:
        found = False
        for s in servers:
            # Сравниваем ID как строки или числа
            if str(s.get('id')) == str(args.server):
                server = s
                found = True
                break
        if not found:
            print(f"Ошибка: Сервер с ID {args.server} не найден.", file=sys.stderr)
            sys.exit(1)
        print(f"Выбран сервер: {server['name']} ({server.get('sponsor', 'N/A')})")
        # Измеряем пинг для явно выбранного сервера
        ping, jitter = measure_ping_and_jitter(server)
        if ping == -1:
            print(f"Ошибка: Не удалось измерить пинг для выбранного сервера ID {args.server}.", file=sys.stderr)
            sys.exit(1)
        # Сохраняем измеренные значения в объект сервера
        server['ping'] = ping
        server['jitter'] = jitter
    else:
        server = find_best_server(servers) # Автовыбор (уже содержит пинг и джиттер)
        # Получаем пинг и джиттер из данных сервера после автовыбора
        ping = server.get('ping', -1)
        jitter = server.get('jitter', -1)

    # Проверка на случай, если пинг/джиттер не были измерены (не должно произойти)
    if ping == -1 or jitter == -1:
         print(f"Критическая ошибка: Не удалось получить пинг/джиттер для сервера {server['name']}.", file=sys.stderr)
         sys.exit(1)

    print(f'Ping:     {ping:10.2f} ms')
    print(f'Jitter:   {jitter:10.2f} ms')

    dl_speed = download_test(server, args.duration, args.threads)
    ul_speed = upload_test(server, args.duration, args.threads)

    print("\n" + "-" * 30)
    print("Тест завершен.")
    print(f"Сервер:   {server['name']} ({server.get('sponsor', 'N/A')})")
    print(f"Ping:     {ping:.2f} ms")
    print(f"Jitter:   {jitter:.2f} ms")
    print(f"Download: {dl_speed:.2f} Mbps")
    print(f"Upload:   {ul_speed:.2f} Mbps")
    print("-" * 30)
    
    result = {
        "server": server['name'], # Отправляем только имя
        "ping": ping, "jitter": jitter,
        "download": dl_speed, "upload": ul_speed,
    }

    if not args.no_submit:
        # Проверяем наличие ключа еще раз на всякий случай
        if config.get('api_key'):
             submit_result_to_api(result, config)
        else:
             print("\n(Отправка пропущена, так как API-ключ не был настроен)")
    else:
        print("(Результаты не были отправлены на сервер)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nТест прерван пользователем.", file=sys.stderr)
        # Попытка остановить спиннер, если он был активен
        stop_spinner(None, False, "") # Передаем None, т.к. нет ссылки на поток
        sys.exit(1)
    except Exception as e:
         print(f"\nКритическая ошибка: {e}", file=sys.stderr)
         # Попытка остановить спиннер
         stop_spinner(None, False, "")
         sys.exit(1)