import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import json
import os
import sys
from datetime import datetime, timedelta
import sqlite3
from sqlite3 import Error
import pystray
from PIL import Image, ImageDraw
import winreg
import subprocess
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import logging
from tkcalendar import Calendar, DateEntry
import tempfile
import psutil
# Регистрация адаптера для datetime для Python 3.12+
from datetime import datetime
import sqlite3
import sys
import traceback

# Настройка кодировки для EXE
if hasattr(sys, 'frozen'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

def safe_print(text, end='\n', flush=False):
    """Безопасный вывод текста в консоль для EXE режима"""
    try:
        print(text, end=end, flush=flush)
    except UnicodeEncodeError:
        try:
            print(text.encode('cp1251', errors='ignore').decode('cp1251'), end=end, flush=flush)
        except:
            pass
    except:
        pass

__version__ = "1.0.0"

def parse_arguments():
    """Парсинг аргументов командной строки"""
    import argparse
    parser = argparse.ArgumentParser(description='SpeedWatch - Мониторинг скорости интернета')
    parser.add_argument('--test-mode', action='store_true', 
                       help='Запуск в тестовом режиме (без GUI, вывод в консоль)')
    return parser.parse_args()

# Парсим аргументы при запуске
ARGS = parse_arguments()
TEST_MODE = ARGS.test_mode

# Определяем корневую директорию проекта
if getattr(sys, 'frozen', False):
    # Запуск из exe
    base_dir = os.path.dirname(sys.executable)
    # В EXE режиме используем AppData для данных
    appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'SpeedWatch')
    data_dir = os.path.join(appdata_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
else:
    # Запуск из скрипта - поднимаемся на уровень выше src
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, 'data')

# Меняем рабочую директорию (только для dev режима)
if not getattr(sys, 'frozen', False):
    os.chdir(base_dir)
    print(f"[AUTOSTART] Установлена рабочая директория: {os.getcwd()}")
else:
    # В EXE режиме не меняем рабочую директорию
    print(f"[AUTOSTART] Запуск из EXE: {base_dir}")

def crash_handler(exctype, value, tb):
    """Обработчик критических ошибок"""
    with open("crash_detailed.log", "w", encoding="utf-8") as f:
        f.write(f"Type: {exctype.__name__}\n")
        f.write(f"Value: {value}\n")
        f.write("Traceback:\n")
        traceback.print_tb(tb, file=f)
    # Вызываем стандартный обработчик
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = crash_handler

def global_exception_handler(exctype, value, tb):
    """Глобальный обработчик исключений"""
    error_msg = f"Необработанное исключение: {exctype.__name__}: {value}\n"
    error_msg += "".join(traceback.format_tb(tb))
    
    # Записываем в файл
    with open("crash.log", "w", encoding="utf-8") as f:
        f.write(error_msg)
    
    # Показываем сообщение
    try:
        import tkinter.messagebox as mb
        mb.showerror("Критическая ошибка", 
                    f"Программа аварийно завершилась.\n\n"
                    f"Ошибка: {value}\n\n"
                    f"Подробности в файле crash.log")
    except:
        print(error_msg)
    
    # Вызываем стандартный обработчик
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = global_exception_handler

def adapt_datetime(dt):
    return dt.isoformat()

sqlite3.register_adapter(datetime, adapt_datetime)

# Условный импорт fcntl (только для Unix-систем)
if sys.platform != 'win32':
    import fcntl
else:
    import ctypes

# Глобальный файловый лок
_lock_file = None
_lock_file_path = os.path.join(tempfile.gettempdir(), "internet_monitor.lock")


def get_dpi_scale_factor():
    """Получает масштабирование DPI для Windows."""
    try:
        if sys.platform == 'win32':
            # Получаем DPI масштабирование (по умолчанию 96 DPI = 100%)
            dpi = ctypes.windll.user32.GetDpiForSystem() if hasattr(ctypes.windll.user32, 'GetDpiForSystem') else 96
            return dpi / 96.0
    except:
        pass
    return 1.0


class InternetSpeedMonitor:
    def __init__(self, root):
        self.root = root
        
        # Определяем корневую директорию проекта
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
            # В EXE режиме используем AppData для данных
            appdata_dir = os.path.join(os.environ.get('APPDATA', ''), 'SpeedWatch')
            self.data_dir = os.path.join(appdata_dir, 'data')
        else:
            # Запуск из скрипта - поднимаемся на уровень выше src
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.data_dir = os.path.join(self.base_dir, 'data')

        # Создаем директорию для данных
        os.makedirs(self.data_dir, exist_ok=True)

        print("[DEBUG] InternetSpeedMonitor __init__ started")
        try:
            self.dpi_scale = get_dpi_scale_factor()

        except Exception as e:
            print(f"[DEBUG] Ошибка в __init__: {e}")
            import traceback
            traceback.print_exc()
            raise

        self.dpi_scale = get_dpi_scale_factor()
        
        # Увеличенное разрешение для современных мониторов
        base_width, base_height = 810, 600
        scaled_width = int(base_width * self.dpi_scale)
        scaled_height = int(base_height * self.dpi_scale)

        # Настройка окна
        self.root.title("SpeedWatch - Мониторинг скорости интернета")
        self.root.geometry(f"{scaled_width}x{scaled_height}")
        
        # Убираем окно из панели задач при сворачивании в трей
        self.root.attributes('-toolwindow', 0)  # Обычное окно
        
        self.center_window()
        
        # Установка иконки
        try:
            self.root.iconbitmap('src/icon.ico')
        except:
            self.create_icon()
        
        self.running = False

        self.test_in_progress = False  # Флаг выполнения теста

        # Анимация теста скорости        
        self.animation_chars = ['-', '\\', '|', '/']  # Символы для анимации
        self.animation_index = 0
        self.animation_job = None

        self.animation_chars = ['-', '\\', '|', '/']  # Символы для анимации теста
        self.animation_index = 0
        self.animation_job = None
        
        # Для анимации ожидания
        self.wait_animation_dots = 0
        self.wait_animation_job = None

        self.monitor_thread = None

        # Определяем корневую директорию проекта
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Путь к папке data
        data_dir = os.path.join(self.base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        self.db_path = os.path.join(self.base_dir, "data", "internet_speed.db")

        self.lock_file = None
        self.lock_file_path = os.path.join(tempfile.gettempdir(), "internet_monitor.lock")

        self.setup_logging() # СНАЧАЛА настраиваем логирование
        self.logger.info(f"Base directory: {self.base_dir}")         # ПОТОМ используем logger
        self.setup_database()        
        self.check_database_integrity()  # Проверяем целостность БД при запуске

        # Управление консолью
        self.console_visible = False  # Начинаем со скрытой консоли
        self.setup_console()
        
        # === ВСЕ ПЕРЕМЕННЫЕ ИНТЕРФЕЙСА ДОЛЖНЫ БЫТЬ ЗДЕСЬ ===
        self.download_var = tk.StringVar(value="0 Mbps")
        self.upload_var = tk.StringVar(value="0 Mbps")
        self.ping_var = tk.StringVar(value="0 ms")
        self.jitter_var = tk.StringVar(value="0 ms")
        self.last_check_var = tk.StringVar(value="Никогда")
        self.next_test_var = tk.StringVar(value="--:--:--")
        self.status_var = tk.StringVar(value="Готов к работе")
        
        # Переменные для информации о подключении
        self.provider_var = tk.StringVar(value="—")
        self.connection_type_var = tk.StringVar(value="—")
        self.server_info_var = tk.StringVar(value="—")
        self.ip_address_var = tk.StringVar(value="—")
        # ===================================================

        # === НАСТРАИВАЕМЫЕ ПОРОГИ ===
        self.download_threshold_var = tk.IntVar(value=25)  # % падения скорости
        self.ping_threshold_var = tk.IntVar(value=100)     # % роста пинга
        self.jitter_threshold_var = tk.IntVar(value=15)    # мс
        self.jitter_frequency_var = tk.IntVar(value=30)    # % частоты превышений
        # ===========================

        # === ПЕРЕМЕННЫЕ ДЛЯ СТАТИСТИКИ ===
        self.stats_period_var = tk.StringVar(value="Месяц")
        self.stats_date_var = tk.StringVar()
        self.stats_week_var = tk.StringVar()
        self.stats_month_var = tk.StringVar()
        self.stats_quarter_var = tk.StringVar()
        self.stats_year_var = tk.StringVar(value=str(datetime.now().year))
        # =================================

        # === ПЕРЕМЕННЫЕ ДЛЯ ГРАФИКОВ ===
        self.graph_period_var = tk.StringVar(value="День")
        self.graph_date_var = tk.StringVar()
        self.graph_week_var = tk.StringVar()
        self.graph_month_var = tk.StringVar()
        self.graph_year_var = tk.StringVar(value=str(datetime.now().year))

        # === ОЧИСТКА ИСТОРИИ ===
        self.clean_enabled_var = tk.BooleanVar(value=True)
        self.auto_clean_days_var = tk.IntVar(value=90)  # 90 дней по умолчанию

        # Создание интерфейса
        self.create_widgets()
        
        # Устанавливаем начальные даты в фильтре журнала
        first_date = self.get_first_measurement_date()
        self.date_from_entry.set_date(first_date)
        self.date_to_entry.set_date(datetime.now().date())        
       
        # Устанавливаем начальный статус
        self.status_var.set("Ожидание команды")
        
        # Загружаем время последнего измерения
        last_time = self.get_last_measurement_time()
        self.last_check_var.set(last_time)

        # Обновляем график с периодом "Все время"
#       self.root.after(500, self.update_graph)  # Небольшая задержка для полной загрузки интерфейса     
          
        
        # Загрузка настроек
        self.is_first_load = True  # Флаг первого запуска
        self.load_settings()
        
        # Загружаем последние значения измерений
        self.load_last_measurement()

        # Очистка старых записей при запуске
        self.clean_old_records()

        self.is_first_load = False  # Сбрасываем после загрузки
        self.update_log()         # Обновляем журнал принудительно
       
        
        # Создание меню для трея
        self.create_tray_icon()
        
        # При закрытии окна - сворачиваем в трей и обновляем меню трея
        self.root.protocol("WM_DELETE_WINDOW", self.handle_window_close)
        
       
        # Сворачиваем в трей если включена настройка
        if self.minimize_to_tray_var.get():
            self.minimize_to_tray()

        # Обновляем меню трея, чтобы текст пункта соответствовал текущему состоянию окна
        try:
            self.update_tray_menu()
        except Exception:
            pass


        # При автозапуске даем сети время инициализироваться
        if self.auto_start_var.get():
            self.logger.info("Автозапуск: ждем 15 секунд для инициализации сети...")
            self.root.after(15000, self.start_monitoring)  # 15 секунд задержки
        else:
            # Обычный запуск - задержка 2 секунды
            self.root.after(2000, self.analyze_connection_quality)

            # Автоматическая проверка обновлений при старте (с задержкой 3 секунды)
            self.root.after(3000, self._check_updates_auto)
        
        # Флаг начального состояния (старт в трее)
        self.started_in_tray = True        
        ###
        
        # Скрываем консоль после создания трея
        self.hide_console_on_start()
        
        # Запускаем главный цикл Tkinter
        self.root.after(100, self.check_tray_icon)

        
    def center_window(self):
        """Центрирование окна на экране"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def scale_font(self, font_name, size):
        """Масштабирует размер шрифта в зависимости от DPI."""
        scaled_size = int(size * self.dpi_scale)
        return (font_name, scaled_size)
    
    def scale_value(self, value):
        """Масштабирует любое числовое значение в зависимости от DPI."""
        return int(value * self.dpi_scale)

    ###
    def check_internet_connection(self):
        """Проверка наличия интернет-соединения"""
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False
    ###     

    def check_tray_icon(self):
        """Проверка что иконка трея запущена"""
        if not hasattr(self, 'tray_thread') or not self.tray_thread.is_alive():
            self.logger.warning("Иконка трея не запущена, перезапускаем...")
            self.create_tray_icon()


    def setup_logging(self):
        """Настройка логирования - только в файл"""
        log_path = os.path.join(self.base_dir, "data", "speed_monitor.log")
        
        # Только файловый логгер, без консоли
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_path, encoding='utf-8')
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Логирование настроено. Файл лога: {log_path}")


    def setup_database(self):
        """Создание базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS speed_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                download_speed REAL,
                upload_speed REAL,
                ping REAL,
                jitter REAL,
                server TEXT
            )
        ''')
        # Добавляем колонку jitter если её ещё нет (для совместимости с существующими БД)
        try:
            cursor.execute('ALTER TABLE speed_measurements ADD COLUMN jitter REAL DEFAULT 0')
        except sqlite3.OperationalError:
            pass  # Колонка уже существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        conn.commit()
        conn.close()

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def check_database_integrity(self):
        """Проверка целостности базы данных при запуске"""
        try:
            self.logger.info("Проверка целостности базы данных...")
            
            # Подключаемся к БД
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Выполняем проверку целостности
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            
            # Закрываем соединение
            conn.close()
            
            # Анализируем результат (без Unicode символов)
            if result and result[0] == "ok":
                self.logger.info("База данных целостна (OK)")
                return True
            else:
                error_msg = f"База данных повреждена: {result[0] if result else 'Неизвестная ошибка'}"
                self.logger.error(error_msg)
                
                # Спрашиваем пользователя о восстановлении
                from tkinter import messagebox
                response = messagebox.askyesno(
                    "Повреждение базы данных",
                    "Обнаружено повреждение базы данных с историей измерений.\n\n"
                    "Хотите создать новую базу данных? (Старая будет переименована)"
                )
                
                if response:
                    self.recover_database()
                else:
                    messagebox.showwarning(
                        "Внимание",
                        "Программа продолжит работу, но данные могут быть неполными.\n"
                        "Рекомендуется перезапустить программу позже."
                    )
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при проверке целостности БД: {e}")
            return False
# endregion

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def recover_database(self):
        """Восстановление поврежденной базы данных"""
        try:
            import shutil
            from datetime import datetime
            
            # Создаем резервную копию поврежденной БД
            if os.path.exists(self.db_path):
                backup_path = f"{self.db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(self.db_path, backup_path)
                self.logger.info(f"Создана резервная копия: {backup_path}")
                
                # Удаляем поврежденную БД
                os.remove(self.db_path)
                self.logger.info("Поврежденная БД удалена")
            
            # Создаем новую БД
            self.setup_database()
            
            from tkinter import messagebox
            messagebox.showinfo(
                "База данных восстановлена",
                f"Создана новая база данных.\n"
                f"Старая БД сохранена как:\n{backup_path}"
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка при восстановлении БД: {e}")
            from tkinter import messagebox
            messagebox.showerror(
                "Ошибка восстановления",
                f"Не удалось восстановить базу данных: {e}"
            )
# endregion

    def clean_old_records(self):
        """Удаление записей старше заданного периода"""
        if not self.clean_enabled_var.get() or self.auto_clean_days_var.get() == 0:
            return
            
        try:
            days = self.auto_clean_days_var.get()
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM speed_measurements WHERE timestamp < ?', (cutoff_date,))
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                self.logger.info(f"Автоматически удалено {deleted} записей старше {days} дней")
                self.update_log()
                
        except Exception as e:
            self.logger.error(f"Ошибка при очистке старых записей: {e}")

    def manual_clean_old(self):
        """Ручная очистка старых записей"""
        days = self.auto_clean_days_var.get()
        if days == 0:
            messagebox.showinfo("Очистка", "Период очистки не задан (0 дней)")
            return
            
        result = messagebox.askyesno(
            "Подтверждение",
            f"Удалить все записи старше {days} дней?\n\n"
            "Эта операция необратима!"
        )
        
        if result:
            self.clean_old_records()
            messagebox.showinfo("Очистка", f"Записи старше {days} дней удалены")

    def get_last_measurement_time(self):
        """Получение времени последнего измерения из БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp FROM speed_measurements 
                ORDER BY timestamp DESC LIMIT 1
            ''')
            result = cursor.fetchone()
            conn.close()
            
            if result:
                timestamp = result[0]
                # Форматируем дату из "YYYY-MM-DD HH:MM:SS.ffffff" в "DD.MM.YY HH:MM"
                try:
                    if timestamp and isinstance(timestamp, str):
                        dt = datetime.strptime(timestamp.split('.')[0], '%Y-%m-%d %H:%M:%S')
                        return dt.strftime('%d.%m.%y %H:%M')
                    else:
                        return "Нет данных"
                except:
                    return "Нет данных"
            else:
                return "Нет данных"
        except Exception as e:
            self.logger.error(f"Ошибка получения времени последнего измерения: {e}")
            return "Нет данных"        

    def get_external_ip_info(self):
        """Получить внешний IP и информацию о провайдере"""
        try:
            import requests
            
            # Получаем внешний IP
            ip_response = requests.get('https://api.ipify.org?format=json', timeout=5)
            ip_data = ip_response.json()
            my_ip = ip_data['ip']
            
            # Получаем информацию о провайдере по IP
            provider_response = requests.get(f'http://ip-api.com/json/{my_ip}?fields=status,isp,org,as,mobile,proxy,hosting', timeout=5)
            provider_data = provider_response.json()
            
            if provider_data.get('status') == 'success':
                isp = provider_data.get('isp', 'Неизвестно')
                org = provider_data.get('org', '')
                as_info = provider_data.get('as', '')
                
                # Очищаем название провайдера
                provider = isp
                if org and org != isp:
                    provider = f"{isp} ({org})"
                
                # Определяем тип подключения
                if provider_data.get('mobile'):
                    conn_type = "Мобильный"
                elif provider_data.get('proxy'):
                    conn_type = "Прокси/VPN"
                elif provider_data.get('hosting'):
                    conn_type = "Хостинг/Дата-центр"
                else:
                    conn_type = "Проводной"
                
                return {
                    'ip': my_ip,
                    'provider': provider,
                    'as': as_info,
                    'connection_type': conn_type
                }
            else:
                return {'ip': my_ip, 'provider': 'Неизвестно', 'connection_type': 'Неизвестно'}
                
        except Exception as e:
            self.logger.error(f"Ошибка получения IP информации: {e}")
            return {'ip': 'Неизвестно', 'provider': 'Неизвестно', 'connection_type': 'Неизвестно'}

    def get_first_measurement_date(self):
        """Получение даты первого измерения из БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp FROM speed_measurements 
                ORDER BY timestamp ASC LIMIT 1
            ''')
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                timestamp = result[0]
                # Парсим дату из "YYYY-MM-DD HH:MM:SS.ffffff"
                try:
                    if isinstance(timestamp, str):
                        dt = datetime.strptime(timestamp.split('.')[0], '%Y-%m-%d %H:%M:%S')
                        return dt.date()
                except:
                    pass
            
            # Если нет данных, возвращаем 01.01.2026
            return datetime(2026, 1, 1).date()
            
        except Exception as e:
            self.logger.error(f"Ошибка получения даты первого измерения: {e}")
            return datetime(2026, 1, 1).date()


    def load_last_measurement(self):
        """Загрузка последнего измерения из БД для отображения при старте"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Проверяем наличие новых колонок
            cursor.execute("PRAGMA table_info(speed_measurements)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Формируем запрос в зависимости от наличия колонок
            if all(col in columns for col in ['server_city', 'server_provider', 'client_ip']):
                cursor.execute('''
                    SELECT download_speed, upload_speed, ping, jitter, 
                           server, server_city, server_provider, client_ip 
                    FROM speed_measurements 
                    ORDER BY timestamp DESC LIMIT 1
                ''')
                result = cursor.fetchone()
                if result:
                    download, upload, ping, jitter, server, server_city, server_provider, client_ip = result
                    self.download_var.set(f"{download:.2f} Mbps" if download else "0 Mbps")
                    self.upload_var.set(f"{upload:.2f} Mbps" if upload else "0 Mbps")
                    self.ping_var.set(f"{ping:.2f} ms" if ping else "0 ms")
                    self.jitter_var.set(f"{jitter:.2f} ms" if jitter else "0 ms")
                    
                    # Обновляем информацию о сервере (только если есть данные)
                    self.server_info_var.set(server if server else "—")
                    
                    # Все поля подключения оставляем пустыми - они будут получены при новом тесте
                    self.provider_var.set("—")
                    self.ip_address_var.set("—")
                    self.connection_type_var.set("—")
                    self.server_info_var.set("—")  # <-- ДОБАВИТЬ эту строку
                    
                    # Определяем тип подключения (временно, пока нет данных)
                    self.connection_type_var.set("—")
                    
                    self.update_monitor_tab_colors()
                    self.update_planned_speed_indicator() 
                    self.logger.info(f"Загружены последние значения: Download={download:.2f} Mbps")

            else:
                # Старая БД без новых колонок
                cursor.execute('''
                    SELECT download_speed, upload_speed, ping, jitter, server 
                    FROM speed_measurements 
                    ORDER BY timestamp DESC LIMIT 1
                ''')
                result = cursor.fetchone()
                if result:
                    download, upload, ping, jitter, server = result
                    self.download_var.set(f"{download:.2f} Mbps")
                    self.upload_var.set(f"{upload:.2f} Mbps")
                    self.ping_var.set(f"{ping:.2f} ms")
                    self.jitter_var.set(f"{jitter:.2f} ms")
                    self.server_info_var.set(server if server else "—")
                    self.update_monitor_tab_colors()
                    self.logger.info(f"Загружены последние значения: Download={download:.2f} Mbps")
                else:
                    self.logger.info("Нет сохраненных измерений")
            
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки последнего измерения: {e}")

# region Можно осторожно менять

    def update_monitor_tab_colors(self):
        """Обновление цветов на вкладке моторинга согласно нормам"""
        try:
            # Получаем текущие значения
            download_text = self.download_var.get().replace(' Mbps', '')
            upload_text = self.upload_var.get().replace(' Mbps', '')
            ping_text = self.ping_var.get().replace(' ms', '')
            jitter_text = self.jitter_var.get().replace(' ms', '')
            
            # Преобразуем в числа (если не "Ошибка" или "0")
            try:
                download = float(download_text) if download_text not in ['Ошибка', '0', ''] else None
            except:
                download = None
                
            try:
                upload = float(upload_text) if upload_text not in ['Ошибка', '0', ''] else None
            except:
                upload = None
                
            try:
                ping = float(ping_text) if ping_text not in ['Ошибка', '0', ''] else None
            except:
                ping = None
                
            try:
                jitter = float(jitter_text) if jitter_text not in ['Ошибка', '0', ''] else None
            except:
                jitter = None
            
            # Получаем средние значения за неделю для сравнения
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                SELECT 
                    AVG(download_speed) as avg_download,
                    AVG(ping) as avg_ping
                FROM speed_measurements 
                WHERE timestamp >= ? AND download_speed > 0 AND ping > 0
            ''', (week_ago,))
            
            result = cursor.fetchone()
            conn.close()
            
            avg_download = result[0] if result and result[0] else None
            avg_ping = result[1] if result and result[1] else None
            
            # Получаем заявленную скорость из настроек
            planned_speed = self.planned_speed_var.get() if hasattr(self, 'planned_speed_var') else 0
            
            # Сбрасываем цвета по умолчанию (черный)
            self.download_label.config(foreground='black')
            self.upload_label.config(foreground='black')
            self.ping_label.config(foreground='black')
            self.jitter_label.config(foreground='black')
            
            # Проверка 1: Скорость ниже заявленной (если задана)
            if download is not None and planned_speed > 0 and download < planned_speed * (1 - self.download_threshold_var.get()/100):
                self.download_label.config(foreground='red')
                self.logger.info(f"Скорость ниже заявленной: {download:.2f} < {planned_speed} (на {((planned_speed-download)/planned_speed*100):.1f}%)")
            
            # Проверка 2: Скорость ниже средней (как резерв)
            elif download is not None and avg_download is not None and download < avg_download * 0.75:
                self.download_label.config(foreground='red')
            
            # Проверка 3: Пинг выше средней
            if ping is not None and avg_ping is not None and ping > avg_ping * (1 + self.ping_threshold_var.get()/100):
                self.ping_label.config(foreground='red')
            
            # Проверка 4: Джиттер выше порога
            if jitter is not None and jitter > self.jitter_threshold_var.get():
                self.jitter_label.config(foreground='red')
            
        except Exception as e:
            self.logger.error(f"Ошибка обновления цветов мониторинга: {e}")
# endregion

    def update_planned_speed_indicator(self):
        """Обновить индикатор заявленной скорости"""
        if hasattr(self, 'planned_speed_var') and hasattr(self, 'download_var'):
            planned = self.planned_speed_var.get()
            if planned > 0:
                try:
                    current = float(self.download_var.get().replace(' Mbps', ''))
                    if current > 0:
                        percent = (current / planned) * 100
                        if percent < 70:
                            status = "⚠️ Ниже тарифа"
                        elif percent < 90:
                            status = "⚡ Чуть ниже тарифа"
                        else:
                            status = "✅ Соответствует тарифу"
                        self.planned_speed_indicator.config(text=f"Тариф: {planned} Mbps ({percent:.0f}%)")
                    else:
                        self.planned_speed_indicator.config(text=f"Тариф: {planned} Mbps")
                except:
                    self.planned_speed_indicator.config(text=f"Тариф: {planned} Mbps")
            else:
                self.planned_speed_indicator.config(text="")


# region ### Можно осторожно менять
    def analyze_connection_quality(self):
        """Анализ качества соединения за последнюю неделю"""
        conn = None
        try:
            # Подключаемся к БД (ОДНО соединение для всех запросов)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Дата неделю назад
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            
            # Получаем средние значения за неделю
            cursor.execute('''
                SELECT 
                    AVG(download_speed) as avg_download,
                    AVG(upload_speed) as avg_upload,
                    AVG(ping) as avg_ping,
                    AVG(jitter) as avg_jitter,
                    COUNT(*) as measurements_count
                FROM speed_measurements 
                WHERE timestamp >= ?
            ''', (week_ago,))
            
            result = cursor.fetchone()
            
            if not result or not result[0] or result[4] < 3:  # Минимум 3 измерения
                self.logger.info("Недостаточно данных для анализа (меньше 3 измерений за неделю)")
                conn.close()
                return
            
            avg_download, avg_upload, avg_ping, avg_jitter, count = result
            
            # Получаем процент измерений с высоким джиттером
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN jitter > ? THEN 1 ELSE 0 END) as bad_count
                FROM speed_measurements 
                WHERE timestamp >= ?
            ''', (self.jitter_threshold_var.get(), week_ago))
            
            jitter_stats = cursor.fetchone()
            total_jitter, bad_jitter = jitter_stats if jitter_stats else (0, 0)
            
            # Получаем средние значения за предыдущий период для сравнения
            two_weeks_ago = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
            week_before = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                SELECT 
                    AVG(download_speed) as prev_avg_download,
                    AVG(ping) as prev_avg_ping
                FROM speed_measurements 
                WHERE timestamp BETWEEN ? AND ?
            ''', (two_weeks_ago, week_before))
            
            prev_result = cursor.fetchone()
            
            # Закрываем соединение ПОСЛЕ всех запросов
            conn.close()
            conn = None
            
            prev_avg_download = prev_result[0] if prev_result and prev_result[0] else avg_download
            prev_avg_ping = prev_result[1] if prev_result and prev_result[1] else avg_ping
            
            # Получаем заявленную скорость из настроек
            planned_speed = self.planned_speed_var.get() if hasattr(self, 'planned_speed_var') else 0
            
            # Проверяем условия (два типа проверок)
            issues = []
            
            # === ПРОВЕРКА 1: Отклонение от заявленной скорости (для претензий к провайдеру) ===
            if planned_speed > 0 and avg_download < planned_speed * (1 - self.download_threshold_var.get()/100):
                drop_percent = (1 - avg_download / planned_speed) * 100
                issues.append(f"• Скорость скачивания ниже заявленной на {drop_percent:.1f}% (тариф {planned_speed} Mbps)")
            
            # === ПРОВЕРКА 2: Отклонение от средней (для обнаружения внезапных проблем) ===
            if prev_avg_download > 0 and avg_download < prev_avg_download * (1 - self.download_threshold_var.get()/100):
                drop_percent = (1 - avg_download / prev_avg_download) * 100
                issues.append(f"• Скорость скачивания упала на {drop_percent:.1f}% от обычной (было {prev_avg_download:.1f}, стало {avg_download:.1f} Mbps)")
            
            # === ПРОВЕРКА 3: Отклонение пинга от средней ===
            if prev_avg_ping > 0 and avg_ping > prev_avg_ping * (1 + self.ping_threshold_var.get()/100):
                increase_percent = (avg_ping / prev_avg_ping - 1) * 100
                issues.append(f"• Пинг вырос на {increase_percent:.1f}% от обычного (было {prev_avg_ping:.1f}, стало {avg_ping:.1f} ms)")
            
            # === ПРОВЕРКА 4: Джиттер (два варианта) ===
            # Вариант 4а: Частое превышение порога
            if total_jitter > 0 and bad_jitter > 0 and (bad_jitter / total_jitter) > (self.jitter_frequency_var.get() / 100):
                issues.append(f"• Джиттер часто превышает норму: в {bad_jitter} из {total_jitter} измерений (среднее {avg_jitter:.1f} ms)")
            # Вариант 4б: Средний джиттер выше порога
            elif avg_jitter > self.jitter_threshold_var.get():
                issues.append(f"• Средний джиттер превышает норму: {avg_jitter:.1f} ms (порог {self.jitter_threshold_var.get()} ms)")
            
            # Если есть проблемы, показываем окно
            if issues:
                self.show_quality_warning(issues, avg_download, avg_upload, avg_ping, avg_jitter, count)
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа соединения: {e}")
        finally:
            # Гарантированно закрываем соединение, если оно еще открыто
            if conn:
                conn.close()
# endregion

# region ### Можно осторожно менять
    def show_quality_warning(self, issues, avg_download, avg_upload, avg_ping, avg_jitter, count):
        """Показать предупреждение о низком качестве соединения"""
        
        # Формируем текст сообщения
        message = "⚠️  НИЗКОЕ КАЧЕСТВО СОЕДИНЕНИЯ  ⚠️\n\n"
        message += "Обнаружены проблемы за последние 7 дней:\n\n"
        
        for issue in issues:
            message += f"{issue}\n"
        
        message += f"\nСредние значения за неделю ({count} измерений):\n"
        message += f"📥 Загрузка: {avg_download:.1f} Mbps\n"
        message += f"📤 Отдача: {avg_upload:.1f} Mbps\n"
        message += f"📶 Пинг: {avg_ping:.1f} ms\n"
        message += f"📊 Джиттер: {avg_jitter:.1f} ms\n\n"
        
        message += "Рекомендуется обратиться к вашему провайдеру\n"
        message += "для диагностики качества соединения."
        
        # Показываем окно с предупреждением
        self.root.after(0, lambda: messagebox.showwarning(
            "Качество соединения",
            message
        ))
# endregion

    def show_term_explanation(self, term):
        """Показать окно с объяснением термина"""
        explanations = {
            "ping": {
                "title": "Что такое пинг?",
                "text": "Пинг (латентность) - это время,\n"
                        "за которое сигнал доходит от вашего компьютера\n"
                        "до сервера и возвращается обратно.\n\n"
                        "📊 Измеряется в миллисекундах (мс).\n"
                        "✅ Чем меньше, тем лучше.\n"
                        "📈 Норма: до 50 мс для проводного интернета.\n"
                        "⚠️ Выше 100 мс - заметные задержки в играх."
            },
            "jitter": {
                "title": "Что такое джиттер?",
                "text": "Джиттер - это вариация задержки пакетов.\n"
                        "Показывает, насколько стабильно ваше соединение.\n\n"
                        "📊 Измеряется в миллисекундах (мс).\n"
                        "✅ Чем ниже, тем стабильнее связь.\n"
                        "📈 Норма: до 15 мс.\n"
                        "⚠️ Выше 15 мс - возможны проблемы\n"
                        "   в онлайн-играх и видео-звонках."
            },
            "jitter_frequency": {  
                "title": "Что такое частота джиттера?",
                "text": "Частота джиттера показывает, как часто\n"
                        "джиттер превышает допустимый порог (15 мс).\n\n"
                        "📊 Измеряется в процентах (%)\n\n"
                        "✅ Менее 10% - редкие скачки, нормально\n"
                        "⚠️ 10-30% - периодическая нестабильность\n"
                        "❌ Более 30% - системная проблема соединения\n\n"
                        "Например: если из 100 измерений джиттер был\n"
                        "высоким в 25 случаях - частота составит 25%."
            }
        }
        
        info = explanations.get(term)
        if not info:
            return
            
        # Создаем окно
        explanation_window = tk.Toplevel(self.root)
        explanation_window.title(info["title"])
        explanation_window.geometry("350x250")
        explanation_window.resizable(False, False)
        
        # Центрируем
        explanation_window.transient(self.root)
        explanation_window.grab_set()
        
        x = self.root.winfo_x() + (self.root.winfo_width() - 350) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 250) // 2
        explanation_window.geometry(f"+{x}+{y}")
        
        # Содержимое
        frame = ttk.Frame(explanation_window, padding="15")
        frame.pack(fill='both', expand=True)
        
        label = ttk.Label(frame, text=info["text"], 
                         font=('Arial', 10), justify='left')
        label.pack(pady=10)
        
        # Кнопка "Понятно"
        ttk.Button(frame, text="Понятно", 
                  command=explanation_window.destroy).pack(pady=10)

    def show_about_window(self):
        """Показать окно 'О программе'"""
        try:
            # Создаем окно
            about_window = tk.Toplevel()
            about_window.title("О программе")
            about_window.geometry("450x350")
            about_window.resizable(False, False)
            
            # Делаем окно независимым от главного
            about_window.transient()  # Убираем зависимость
            about_window.grab_set()
            about_window.focus_force()
            
            # Центрируем окно по центру экрана
            about_window.update_idletasks()
            screen_width = about_window.winfo_screenwidth()
            screen_height = about_window.winfo_screenheight()
            x = (screen_width - 450) // 2
            y = (screen_height - 350) // 2
            about_window.geometry(f"+{x}+{y}")
            
            # Основной контейнер
            main_frame = ttk.Frame(about_window, padding="20")
            main_frame.pack(fill='both', expand=True)
            
            # Заголовок
            title_label = ttk.Label(
                main_frame, 
                text="Добро пожаловать!",
                font=('Arial', 16, 'bold')
            )
            title_label.pack(pady=(0, 10))
            
            # Благодарность
            thanks_label = ttk.Label(
                main_frame,
                text="Благодарим за выбор\nSpeedWatch!",
                font=('Arial', 12),
                justify='center'
            )
            thanks_label.pack(pady=(0, 15))
            
            # Версия
            version_label = ttk.Label(
                main_frame,
                text=f"Версия {__version__}",
                font=('Arial', 11, 'bold')
            )

            version_label.pack(pady=(0, 15))
            
            # Пожелание
            wish_label = ttk.Label(
                main_frame,
                text="Желаем вам стабильного и быстрого интернета!\n"
                     "Мы поможем следить за качеством вашего соединения.",
                font=('Arial', 10),
                justify='center',
                wraplength=380
            )
            wish_label.pack(pady=(0, 20))
            
            # Ссылки
            links_frame = ttk.Frame(main_frame)
            links_frame.pack(pady=(0, 15))
            
            # Ссылка на GitHub Issues
            issues_link = tk.Label(
                links_frame,
                text="Замечания и предложения (GitHub Issues)",
                fg="blue",
                cursor="hand2",
                font=('Arial', 9)
            )
            issues_link.pack(pady=2)
            issues_link.bind("<Button-1>", lambda e: self._open_url("https://github.com/vldbkov/SpeedWatch/issues"))
            
            # Ссылка на поддержку
            sponsor_link = tk.Label(
                links_frame,
                text="Поддержать автора проекта (YooMoney)",
                fg="blue",
                cursor="hand2",
                font=('Arial', 9)
            )
            sponsor_link.pack(pady=2)
            sponsor_link.bind("<Button-1>", lambda e: self._open_url("https://yoomoney.ru/to/4100119453410920"))
            
            # Кнопка "Понятно" - ИСПРАВЛЕН размер
            ok_button = tk.Button(
                main_frame,
                text="Понятно",
                command=about_window.destroy,
                width=20,
                height=2,
                bg='#f0f0f0',
                relief='raised'
            )
            ok_button.pack(pady=(10, 0))
            
            # Принудительное отображение
            about_window.lift()
            about_window.attributes('-topmost', True)
            about_window.after(100, lambda: about_window.attributes('-topmost', False))
            
            self.logger.info("Окно 'О программе' успешно создано")
            
        except Exception as e:
            self.logger.error(f"Ошибка создания окна 'О программе': {e}")


    def check_for_updates(self):
        """Проверка наличия обновлений на GitHub"""
        try:
            import requests
            from tkinter import messagebox
            
            # Показываем сообщение о проверке
            self.logger.info("Проверка обновлений...")
            
            # GitHub API для получения последнего релиза
            repo = "vldbkov/SpeedWatch"  # замените на ваш репозиторий
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                latest_release = response.json()
                latest_version = latest_release["tag_name"].lstrip('v')  # убираем 'v' если есть
                current_version = __version__
                
                # Сравниваем версии (простое строковое сравнение для формата x.y.z)
                if self._is_newer_version(latest_version, current_version):
                    # Есть обновление
                    message = (
                        f"Доступна новая версия {latest_version}!\n\n"
                        f"У вас установлена версия {current_version}.\n\n"
                        f"Что нового:\n{latest_release.get('body', 'Описание отсутствует')}\n\n"
                        f"Хотите скачать обновление?"
                    )
                    
                    if messagebox.askyesno("Доступно обновление", message):
                        # Открываем страницу релиза
                        self._open_url(latest_release["html_url"])
                else:
                    # Нет обновлений
                    messagebox.showinfo(
                        "Проверка обновлений",
                        f"У вас установлена последняя версия ({current_version})."
                    )
            elif response.status_code == 404:
                messagebox.showinfo(
                    "Проверка обновлений",
                    f"У вас установлена последняя версия программы ({__version__})."
                )
            else:
                self.logger.error(f"Ошибка GitHub API: {response.status_code}")
                messagebox.showerror(
                    "Ошибка",
                    "Не удалось проверить обновления. Проверьте подключение к интернету."
                )
                
        except ImportError:
            messagebox.showerror(
                "Ошибка",
                "Для проверки обновлений требуется библиотека requests.\n"
                "Установите: pip install requests"
            )
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Ошибка сети при проверке обновлений: {e}")
            messagebox.showerror(
                "Ошибка",
                "Не удалось подключиться к GitHub. Проверьте интернет-соединение."
            )
        except Exception as e:
            self.logger.error(f"Ошибка при проверке обновлений: {e}")
            messagebox.showerror("Ошибка", f"Не удалось проверить обновления: {e}")

    def _check_updates_auto(self):
        """Автоматическая проверка обновлений при старте (без диалогов)"""
        try:
            import requests
            
            # GitHub API для получения последнего релиза
            repo = "baykovv/SpeedWatch"  # замените на ваш репозиторий
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                latest_release = response.json()
                latest_version = latest_release["tag_name"].lstrip('v')
                current_version = __version__
                
                # Если есть новая версия - показываем уведомление
                if self._is_newer_version(latest_version, current_version):
                    self._show_update_notification(latest_version, latest_release["html_url"])
            elif response.status_code == 404:
                # Нет релизов - это нормально для первой версии
                self.logger.info("Релизы не найдены, пропускаем проверку обновлений")
            else:
                self.logger.warning(f"Ошибка GitHub API при авто-проверке: {response.status_code}")
                
        except ImportError:
            self.logger.warning("Библиотека requests не установлена, авто-проверка обновлений отключена")
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Ошибка сети при авто-проверке обновлений: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка при авто-проверке обновлений: {e}")

    def _show_update_notification(self, new_version, download_url):
        """Показать уведомление о новой версии"""
        try:
            from tkinter import messagebox
            
            result = messagebox.askyesno(
                "Доступно обновление",
                f"Доступна новая версия SpeedWatch {new_version}!\n\n"
                f"У вас установлена версия {__version__}.\n\n"
                f"Хотите перейти на страницу загрузки?"
            )
            
            if result:
                self._open_url(download_url)
                
        except Exception as e:
            self.logger.error(f"Ошибка при показе уведомления: {e}")

    def _is_newer_version(self, latest, current):
        """Сравнение версий в формате x.y.z"""
        try:
            # Разбиваем на компоненты
            latest_parts = list(map(int, latest.split('.')))
            current_parts = list(map(int, current.split('.')))
            
            # Дополняем нулями до одинаковой длины
            max_len = max(len(latest_parts), len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))
            
            # Сравниваем покомпонентно
            return latest_parts > current_parts
        except:
            # Если не удалось распарсить, сравниваем как строки
            return latest > current


    def _open_url(self, url):
        """Открыть ссылку в браузере"""
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            self.logger.error(f"Ошибка открытия ссылки: {e}")

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def setup_console(self):
        """Настройка консоли Windows"""
        try:
            import ctypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            
            # Получаем хендл консоли
            self.hwnd = kernel32.GetConsoleWindow()
            
            # Если консоли нет - создаем её
            if not self.hwnd:
                kernel32.AllocConsole()
                self.hwnd = kernel32.GetConsoleWindow()
                
                # Перенаправляем stdout и stderr
                sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
                sys.stderr = open('CONOUT$', 'w', encoding='utf-8')
                
                # Обновляем логгер - заменяем StreamHandler
                for handler in self.logger.handlers[:]:
                    if isinstance(handler, logging.StreamHandler):
                        self.logger.removeHandler(handler)
                
                # Добавляем новый StreamHandler для новой консоли
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(logging.INFO)
                console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                self.logger.addHandler(console_handler)
                
                self.logger.info("Консоль создана принудительно")
            
            if self.hwnd:
                # Убираем ТОЛЬКО кнопку закрытия (крестик), оставляем свернуть и развернуть
                user32 = ctypes.WinDLL('user32', use_last_error=True)
                GWL_STYLE = -16
                
                style = user32.GetWindowLongW(self.hwnd, GWL_STYLE)
                style = style & ~0x00080000  # Убираем WS_SYSMENU
                style = style | 0x00020000   # Добавляем WS_MINIMIZEBOX
                style = style | 0x00010000   # Добавляем WS_MAXIMIZEBOX
                
                user32.SetWindowLongW(self.hwnd, GWL_STYLE, style)
                user32.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0, 
                                  0x0001 | 0x0002 | 0x0020)
                
                self.logger.info("Кнопка закрытия консоли отключена, кнопки свернуть/развернуть активны")
                
        except Exception as e:
            self.logger.error(f"Ошибка настройки консоли: {e}")
# endregion

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def hide_console_on_start(self):
        """Скрыть консоль при старте"""
        try:
            import ctypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            
            # Получаем актуальный хендл
            current_hwnd = kernel32.GetConsoleWindow()
            
            if current_hwnd:
                user32.ShowWindow(current_hwnd, 0)  # SW_HIDE
                self.hwnd = current_hwnd
                self.console_visible = False
        except Exception as e:
            self.logger.error(f"Ошибка скрытия консоли при старте: {e}")
# endregion

    def close_console(self):
        """Закрыть консольное окно при выходе"""
        try:
            import ctypes
            if hasattr(self, 'hwnd') and self.hwnd:
                # Отправляем сообщение на закрытие окна
                ctypes.windll.user32.PostMessageW(self.hwnd, 0x0010, 0, 0)  # WM_CLOSE = 0x0010
                self.logger.info("Команда на закрытие консоли отправлена")
        except Exception as e:
            self.logger.error(f"Ошибка закрытия консоли: {e}")

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def toggle_console(self, icon, item):
        """Переключение видимости консоли"""
        try:
            import ctypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            
            if hasattr(self, 'hwnd') and self.hwnd:
                if self.console_visible:
                    user32.ShowWindow(self.hwnd, 0)  # SW_HIDE
                    self.console_visible = False
                else:
                    user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE
                    self.console_visible = True
                
                self.update_tray_menu()
                    
        except Exception as e:
            self.logger.error(f"Ошибка переключения консоли: {e}")
# endregion

    def hide_console(self):
        """Принудительно скрыть консольное окно"""
        try:
            import ctypes
            if hasattr(self, 'hwnd') and self.hwnd:
                user32 = ctypes.WinDLL('user32', use_last_error=True)
                user32.ShowWindow(self.hwnd, 0)  # SW_HIDE = 0
                self.logger.info("Консоль скрыта при выходе")
        except Exception as e:
            self.logger.error(f"Ошибка скрытия консоли: {e}")
    def update_tray_menu(self):
        """Обновление меню в трее"""
        try:
            from functools import partial
            
            # Определяем текст для консоли
            console_text = "Скрыть консоль" if self.console_visible else "Показать консоль"
            
            # Определяем текст для окна
            # Используем комбинацию проверок для точного определения
            is_window_visible = (
                self.root.winfo_viewable() and 
                self.root.state() != 'withdrawn' and
                not self.root.winfo_ismapped() == 0
            )
            
            if is_window_visible:
                window_text = "Окно программы скрыть"
            else:
                window_text = "Окно программы показать"
            
            # Создаем новое меню
            new_menu = pystray.Menu(
                pystray.MenuItem(
                    window_text, 
                    lambda: self.toggle_window_visibility()
                ),
                pystray.MenuItem(
                    console_text, 
                    lambda: self.toggle_console(self.tray_icon, None)
                ),
                pystray.MenuItem(
                    "Тест сейчас", 
                    lambda: self.run_speed_test()
                ),
                pystray.MenuItem(
                    "Проверить обновления", 
                    lambda: self.check_for_updates()
                ),
                pystray.MenuItem(
                    "О программе", 
                    lambda: self.show_about_window()
                ),
                pystray.MenuItem(
                    "Выход", 
                    lambda: self.quit_app()
                )
            )
            
            # Обновляем меню
            if hasattr(self, 'tray_icon'):
                self.tray_icon.menu = new_menu
                self.tray_icon.update_menu()
                
        except Exception as e:
            self.logger.error(f"Ошибка обновления меню трея: {e}")
          

    def create_icon(self):
        """Создание простой иконки если файла нет"""
        try:
            image = Image.new('RGB', (64, 64), color='blue')
            draw = ImageDraw.Draw(image)
            draw.text((20, 25), "SPD", fill='white')
            image.save('src/icon.png')
            
            # Конвертируем PNG в ICO
            img = Image.open('src/icon.png')
            img.save('src/icon.ico', format='ICO')
            self.root.iconbitmap('src/icon.ico')
        except:
            pass


    def create_widgets(self):
        """Создание виджетов интерфейса"""
        # Конфигурируем стили для высокого разрешения
        style = ttk.Style()
        style.configure('TLabel', font=self.scale_font('Arial', 10))
        style.configure('TButton', font=self.scale_font('Arial', 10), padding=self.scale_value(5))
        style.configure('TCheckbutton', font=self.scale_font('Arial', 10))
        style.configure('TRadiobutton', font=self.scale_font('Arial', 10))
        style.configure('Treeview', font=self.scale_font('Arial', 9), rowheight=self.scale_value(25))
        style.configure('Treeview.Heading', font=self.scale_font('Arial', 10))
        style.configure('TNotebook.Tab', font=self.scale_font('Arial', 10))
        style.configure('TLabelframe', font=self.scale_font('Arial', 11))
        style.configure('TLabelframe.Label', font=self.scale_font('Arial', 11) + ('bold',))
        
        # Создаем Notebook (вкладки)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=self.scale_value(15), pady=self.scale_value(15))
        
        # Вкладка мониторинга
        self.monitor_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.monitor_frame, text='Мониторинг')
        
        # Вкладка графиков
        self.graph_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.graph_frame, text='Графики')
        
        # Вкладка журнала
        self.log_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.log_frame, text='Журнал')

        # Вкладка настроек
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text='Настройки')

         # === НОВАЯ ВКЛАДКА СТАТИСТИКИ ===
        self.stats_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.stats_frame, text='Статистика')      
      
        # Заполняем вкладку мониторинга
        self.setup_monitor_tab()
        
        # Заполняем вкладку графиков
        self.setup_graph_tab()
        
        # Заполняем вкладку журнала
        self.setup_log_tab()
        
        # Заполняем вкладку настроек
        self.setup_settings_tab()

        # === ВАЖНО: Заполняем вкладку статистики ===
        self.setup_stats_tab()

    def setup_monitor_tab(self):
        """Настройка вкладки мониторинга"""
        # Фрейм с текущими показателями
        current_frame = ttk.LabelFrame(self.monitor_frame, text="Параметры соединения", padding=self.scale_value(15))
        current_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))
        
        # Скорость загрузки
        ttk.Label(current_frame, text="Скорость загрузки:", font=self.scale_font('Arial', 12)).grid(row=0, column=0, sticky='w', pady=5)
        self.download_label = ttk.Label(current_frame, textvariable=self.download_var, font=self.scale_font('Arial', 16) + ('bold',), width=12, anchor='w')
        self.download_label.grid(row=0, column=1, padx=10, sticky='w')
        
        # Метка с заявленной скоростью (таким же шрифтом как скорость загрузки)
        self.planned_speed_indicator = ttk.Label(current_frame, text="", font=self.scale_font('Arial', 12))
        self.planned_speed_indicator.grid(row=0, column=2, padx=(20, 0), sticky='w')
        
        # Скорость отдачи
        ttk.Label(current_frame, text="Скорость отдачи:", font=self.scale_font('Arial', 12)).grid(row=1, column=0, sticky='w', pady=5)
        self.upload_label = ttk.Label(current_frame, textvariable=self.upload_var, font=self.scale_font('Arial', 16) + ('bold',), width=12, anchor='w')
        self.upload_label.grid(row=1, column=1, padx=10, sticky='w')
        
        # Пинг
        ping_frame = ttk.Frame(current_frame)
        ping_frame.grid(row=2, column=0, sticky='w', pady=5)
        
        ttk.Label(ping_frame, text="Пинг:", font=self.scale_font('Arial', 12)).pack(side='left')
        
        # Знак вопроса для пинга
        ping_question = tk.Label(ping_frame, text="❓", font=('Arial', 10, 'bold'), fg="blue", cursor="hand2")
        ping_question.pack(side='left', padx=(2, 0))
        ping_question.bind("<Button-1>", lambda e: self.show_term_explanation("ping"))
        
        self.ping_label = ttk.Label(current_frame, textvariable=self.ping_var, font=self.scale_font('Arial', 16) + ('bold',), width=12, anchor='w')
        self.ping_label.grid(row=2, column=1, padx=10, sticky='w')
        
        # Jitter
        jitter_frame = ttk.Frame(current_frame)
        jitter_frame.grid(row=3, column=0, sticky='w', pady=5)       
        ttk.Label(jitter_frame, text="Джиттер:", font=self.scale_font('Arial', 12)).pack(side='left')
        
        # Знак вопроса для джиттера
        jitter_question = tk.Label(jitter_frame, text="❓", font=('Arial', 10, 'bold'), fg="blue", cursor="hand2")
        jitter_question.pack(side='left', padx=(2, 0))
        jitter_question.bind("<Button-1>", lambda e: self.show_term_explanation("jitter"))
        
        self.jitter_label = ttk.Label(current_frame, textvariable=self.jitter_var, font=self.scale_font('Arial', 16) + ('bold',), width=12, anchor='w')
        self.jitter_label.grid(row=3, column=1, padx=10, sticky='w')
        
        # Время последнего измерения
        ttk.Label(current_frame, text="Последнее измерение:", font=self.scale_font('Arial', 12)).grid(row=4, column=0, sticky='w', pady=5)
        self.last_check_label = ttk.Label(current_frame, textvariable=self.last_check_var, font=self.scale_font('Arial', 11), width=16, anchor='w')
        self.last_check_label.grid(row=4, column=1, padx=10, sticky='w')

        # === ФРЕЙМ: Информация о подключении ===
        info_frame = ttk.LabelFrame(self.monitor_frame, text="Информация о подключении", padding=self.scale_value(15))
        info_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))

        # Провайдер
        ttk.Label(info_frame, text="Провайдер:", font=self.scale_font('Arial', 11)).grid(row=0, column=0, sticky='w', pady=3)
        ttk.Label(info_frame, textvariable=self.provider_var, font=self.scale_font('Arial', 11) + ('bold',)).grid(row=0, column=1, sticky='w', padx=10)

        # Тип подключения
        ttk.Label(info_frame, text="Подключение:", font=self.scale_font('Arial', 11)).grid(row=1, column=0, sticky='w', pady=3)
        ttk.Label(info_frame, textvariable=self.connection_type_var, font=self.scale_font('Arial', 11) + ('bold',)).grid(row=1, column=1, sticky='w', padx=10)

        # Сервер
        ttk.Label(info_frame, text="Сервер:", font=self.scale_font('Arial', 11)).grid(row=2, column=0, sticky='w', pady=3)
        ttk.Label(info_frame, textvariable=self.server_info_var, font=self.scale_font('Arial', 11) + ('bold',)).grid(row=2, column=1, sticky='w', padx=10)

        # IP адрес
        ttk.Label(info_frame, text="IP адрес:", font=self.scale_font('Arial', 11)).grid(row=3, column=0, sticky='w', pady=3)
        ttk.Label(info_frame, textvariable=self.ip_address_var, font=self.scale_font('Arial', 11) + ('bold',)).grid(row=3, column=1, sticky='w', padx=10)

        # Фрейм с управлением
        control_frame = ttk.Frame(self.monitor_frame)
        control_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(20))
        
        # Кнопки управления
        self.start_button = ttk.Button(control_frame, text="Запуск мониторинга", command=self.start_monitoring)
        self.start_button.pack(side='left', padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="Остановить", command=self.stop_monitoring, state='disabled')
        self.stop_button.pack(side='left', padx=5)
        
        self.test_button = ttk.Button(control_frame, text="Тест сейчас", command=self.run_speed_test)
        self.test_button.pack(side='left', padx=self.scale_value(5))
        
        # Информация о следующем тесте
        ttk.Label(control_frame, text="Следующий тест через:", font=self.scale_font('Arial', 10)).pack(side='left', padx=self.scale_value(20))
        ttk.Label(control_frame, textvariable=self.next_test_var, font=self.scale_font('Arial', 11) + ('bold',)).pack(side='left')
        
        # Статус бар ПОД кнопками управления
        status_bar = ttk.Label(self.monitor_frame, textvariable=self.status_var, relief=tk.SUNKEN, padding=5)
        status_bar.pack(fill='x', padx=self.scale_value(15), pady=(0, self.scale_value(15)))

    def setup_graph_tab(self):
        """Настройка вкладки с графиками"""
        # Панель управления графиками
        control_frame = ttk.Frame(self.graph_frame)
        control_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))
        
        ttk.Label(control_frame, text="Период:", font=self.scale_font('Arial', 10)).pack(side='left')
        
        # Радиокнопки выбора периода
        period_frame = ttk.Frame(control_frame)
        period_frame.pack(side='left', padx=10)
        
        ttk.Radiobutton(period_frame, text="День", variable=self.graph_period_var, 
                       value="День", command=self.update_graph_period_ui).pack(side='left', padx=2)
        ttk.Radiobutton(period_frame, text="Неделя", variable=self.graph_period_var, 
                       value="Неделя", command=self.update_graph_period_ui).pack(side='left', padx=2)
        ttk.Radiobutton(period_frame, text="Месяц", variable=self.graph_period_var, 
                       value="Месяц", command=self.update_graph_period_ui).pack(side='left', padx=2)
        ttk.Radiobutton(period_frame, text="Все время", variable=self.graph_period_var, 
                       value="Все время", command=self.update_graph_period_ui).pack(side='left', padx=2)
        
        # Контейнер для элементов выбора
        self.graph_selector_frame = ttk.Frame(control_frame)
        self.graph_selector_frame.pack(side='left', padx=10)
        
        # Кнопка обновления
        ttk.Button(control_frame, text="Обновить\n  график", command=self.update_graph, 
                  width=8).pack(side='left', padx=5)
        
        # Кнопка экспорта
        ttk.Button(control_frame, text="Экспорт\n  PNG", command=self.export_graph, 
                  width=8).pack(side='left', padx=5)
        
        # Область для графиков
        self.graph_canvas_frame = ttk.Frame(self.graph_frame)
        self.graph_canvas_frame.pack(fill='both', expand=True, padx=self.scale_value(15), pady=self.scale_value(15))
        
        # Создаем фигуру для matplotlib
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_canvas_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        
        # Инициализация UI
        self.update_graph_period_ui()

    def update_graph_period_ui(self):
        """Обновление UI выбора периода для графиков"""
        # Очищаем контейнер
        for widget in self.graph_selector_frame.winfo_children():
            widget.destroy()
        
        period = self.graph_period_var.get()
        
        if period == "День":
            # Календарь для выбора даты
            from tkcalendar import DateEntry
            self.graph_date_picker = DateEntry(self.graph_selector_frame, width=10, 
                                               background='darkblue', foreground='white',
                                               date_pattern='dd.mm.yyyy', locale='ru_RU')
            self.graph_date_picker.pack(side='left')
            
        elif period == "Неделя":
            # Выбор недели и года
            ttk.Label(self.graph_selector_frame, text="Неделя:").pack(side='left')
            current_week = datetime.now().isocalendar()[1]
            week_values = [str(i) for i in range(1, 53)]
            
            self.graph_week_combo = ttk.Combobox(self.graph_selector_frame, 
                                                 values=week_values,
                                                 width=2, state='readonly')
            self.graph_week_combo.pack(side='left', padx=5)
            self.graph_week_combo.set(str(current_week))
            
            ttk.Label(self.graph_selector_frame, text="Год:").pack(side='left')
            self.graph_year_combo = ttk.Combobox(self.graph_selector_frame,
                                                 values=[str(y) for y in range(2026, datetime.now().year+1)],
                                                 width=4, state='readonly')
            self.graph_year_combo.pack(side='left', padx=5)
            self.graph_year_combo.set(str(datetime.now().year))
            
        elif period == "Месяц":
            # Выбор месяца и года (цифрами)
            months = [str(i) for i in range(1, 13)]  # ['1', '2', '3', ... '12']
            
            ttk.Label(self.graph_selector_frame, text="Месяц:").pack(side='left')
            self.graph_month_combo = ttk.Combobox(self.graph_selector_frame, values=months,
                                                  width=2, state='readonly')  # ширина 2 символа
            self.graph_month_combo.pack(side='left', padx=5)
            self.graph_month_combo.set(str(datetime.now().month))  # текущий месяц цифрой
            
            ttk.Label(self.graph_selector_frame, text="Год:").pack(side='left')
            self.graph_month_year_combo = ttk.Combobox(self.graph_selector_frame,
                                                       values=[str(y) for y in range(2026, datetime.now().year+1)],
                                                       width=4, state='readonly')
            self.graph_month_year_combo.pack(side='left', padx=5)
            self.graph_month_year_combo.set(str(datetime.now().year))

    def setup_log_tab(self):
        """Настройка вкладки журнала"""
        # Панель управления журналом
        log_control_frame = ttk.Frame(self.log_frame)
        log_control_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))
        
        # Кнопки управления журналом
        ttk.Button(log_control_frame, text="Обновить", command=self.update_log).pack(side='left', padx=5)
        ttk.Button(log_control_frame, text="Экспорт в CSV", command=self.export_log).pack(side='left', padx=5)
        ttk.Button(log_control_frame, text="Очистить журнал", command=self.clear_log).pack(side='left', padx=5)
        
        # Поля выбора периода с календарем
        ttk.Label(log_control_frame, text="Период с:").pack(side='left', padx=(20, 5))
        
        # Календарь для начальной даты
        self.date_from_var = tk.StringVar()
        self.date_from_entry = DateEntry(
            log_control_frame,
            textvariable=self.date_from_var,
            width=9,
            background='darkblue',
            foreground='white',
            borderwidth=2,
            date_pattern='dd.mm.yyyy',
            locale='ru_RU'
        )
        self.date_from_entry.pack(side='left')
        
        ttk.Label(log_control_frame, text="по:").pack(side='left', padx=(5, 5))
        
        # Календарь для конечной даты
        self.date_to_var = tk.StringVar()
        self.date_to_entry = DateEntry(
            log_control_frame,
            textvariable=self.date_to_var,
            width=9,
            background='darkblue',
            foreground='white',
            borderwidth=2,
            date_pattern='dd.mm.yyyy',
            locale='ru_RU'
        )
        self.date_to_entry.pack(side='left')
        
        # Кнопки управления
        ttk.Button(log_control_frame, text="Применить", command=self.update_log).pack(side='left', padx=5)
        ttk.Button(log_control_frame, text="Сбросить", command=self.reset_date_filter).pack(side='left', padx=5)
        
        # Панель со средними значениями
        avg_frame = ttk.LabelFrame(self.log_frame, text="Средние значения", padding=self.scale_value(15))
        avg_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))
        
        # Контейнер для значений (три колонки)
        values_frame = ttk.Frame(avg_frame)
        values_frame.pack(fill='x')
        
        # Левая колонка - Загрузка
        left_frame = ttk.Frame(values_frame)
        left_frame.pack(side='left', fill='x', expand=True, padx=5)
        
        ttk.Label(left_frame, text="Загрузка:", font=self.scale_font('Arial', 11)).pack(side='left', padx=5)
        self.avg_download_var = tk.StringVar(value="0 Mbps")
        ttk.Label(left_frame, textvariable=self.avg_download_var, font=self.scale_font('Arial', 12) + ('bold',)).pack(side='left', padx=5)
        
        # Средняя колонка - Отдача
        middle_frame = ttk.Frame(values_frame)
        middle_frame.pack(side='left', fill='x', expand=True, padx=5)
        
        ttk.Label(middle_frame, text="Отдача:", font=self.scale_font('Arial', 11)).pack(side='left', padx=5)
        self.avg_upload_var = tk.StringVar(value="0 Mbps")
        ttk.Label(middle_frame, textvariable=self.avg_upload_var, font=self.scale_font('Arial', 12) + ('bold',)).pack(side='left', padx=5)
        
        # Правая колонка - Пинг
        right_frame = ttk.Frame(values_frame)
        right_frame.pack(side='left', fill='x', expand=True, padx=5)
        
        ttk.Label(right_frame, text="Пинг:", font=self.scale_font('Arial', 11)).pack(side='left', padx=5)
        self.avg_ping_var = tk.StringVar(value="0 ms")
        ttk.Label(right_frame, textvariable=self.avg_ping_var, font=self.scale_font('Arial', 12) + ('bold',)).pack(side='left', padx=5)
        
        # Четвёртая колонка - Джиттер
        jitter_frame = ttk.Frame(values_frame)
        jitter_frame.pack(side='left', fill='x', expand=True, padx=5)
        
        ttk.Label(jitter_frame, text="Джиттер:", font=self.scale_font('Arial', 11)).pack(side='left', padx=5)
        self.avg_jitter_var = tk.StringVar(value="0 ms")
        ttk.Label(jitter_frame, textvariable=self.avg_jitter_var, font=self.scale_font('Arial', 12) + ('bold',)).pack(side='left', padx=5)
        
        # Таблица журнала
        columns = ('ID', 'Время', 'Загрузка (Mbps)', 'Отдача (Mbps)', 'Пинг (ms)', 'Джиттер (ms)', 'Сервер')
        
        # Создаем Treeview с полосой прокрутки
        tree_frame = ttk.Frame(self.log_frame)
        tree_frame.pack(fill='both', expand=True, padx=self.scale_value(15), pady=self.scale_value(15))
        
        # Вертикальная полоса прокрутки
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side='right', fill='y')
        
        # Горизонтальная полоса прокрутки
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side='bottom', fill='x')
        
        # Создаем Treeview для журнала
        self.log_tree = ttk.Treeview(tree_frame, columns=columns, show='headings',
                                    yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        ###
        # Настройка тегов для отдельных колонок (красный цвет для конкретных значений)
        self.log_tree.tag_configure('low_download', foreground='red')
        self.log_tree.tag_configure('low_upload', foreground='red')
        self.log_tree.tag_configure('high_ping', foreground='red')
        self.log_tree.tag_configure('high_jitter', foreground='red')
        ###        
        # Настройка стиля для Treeview с поддержкой тегов
        style = ttk.Style()
        
        # Создаем пользовательский стиль для низких значений
        # К сожалению, ttk.Treeview имеет ограничения с цветами, поэтому используем красный текст
        style.configure('Treeview', rowheight=20)
        
       
        ###        
        # Настройка колонок - все фиксированной ширины, растяжение отключено
        for i, col in enumerate(columns):
            self.log_tree.heading(col, text=col)
            # Все столбцы имеют фиксированную ширину
            if i == 0:  # ID
                self.log_tree.column(col, width=42, anchor=tk.CENTER, stretch=False)
            elif i == 1:  # Время
                self.log_tree.column(col, width=90, anchor=tk.CENTER, stretch=False)
            elif i == 2:  # Загрузка (+2 символа ≈ 16 пикселей)
                self.log_tree.column(col, width=108, anchor=tk.CENTER, stretch=False)
            elif i == 3:  # Отдача
                self.log_tree.column(col, width=100, anchor=tk.CENTER, stretch=False)
            elif i == 4:  # Пинг
                self.log_tree.column(col, width=70, anchor=tk.CENTER, stretch=False)
            elif i == 5:  # Джиттер (+2 символа ≈ 16 пикселей)
                self.log_tree.column(col, width=96, anchor=tk.CENTER, stretch=False)
            else:  # Сервер (+5 символов ≈ 40 пикселей)
                self.log_tree.column(col, width=240, anchor=tk.W, stretch=False)
        ###
        
        self.log_tree.pack(fill='both', expand=True)
        
        # Конфигурация скроллбаров
        vsb.config(command=self.log_tree.yview)
        hsb.config(command=self.log_tree.xview)
        
        # Загружаем данные
        self.update_log()

    def setup_stats_tab(self):
        """Настройка вкладки статистики"""
        # Панель выбора периода
        period_frame = ttk.Frame(self.stats_frame)
        period_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))
        
        ttk.Label(period_frame, text="Период:", font=self.scale_font('Arial', 10)).pack(side='left')
        
        # Переменные для периода
        self.stats_period_var = tk.StringVar(value="Месяц")
        self.stats_date_var = tk.StringVar()
        self.stats_week_var = tk.StringVar()
        self.stats_month_var = tk.StringVar()
        self.stats_quarter_var = tk.StringVar()
        self.stats_year_var = tk.StringVar(value=str(datetime.now().year))
        
        # Радиокнопки выбора периода
        periods_frame = ttk.Frame(period_frame)
        periods_frame.pack(side='left', padx=10)
        
        ttk.Radiobutton(periods_frame, text="День", variable=self.stats_period_var, 
                       value="День", command=self.update_stats_period_ui).pack(side='left', padx=2)
        ttk.Radiobutton(periods_frame, text="Неделя", variable=self.stats_period_var, 
                       value="Неделя", command=self.update_stats_period_ui).pack(side='left', padx=2)
        ttk.Radiobutton(periods_frame, text="Месяц", variable=self.stats_period_var, 
                       value="Месяц", command=self.update_stats_period_ui).pack(side='left', padx=2)
        ttk.Radiobutton(periods_frame, text="Квартал", variable=self.stats_period_var, 
                       value="Квартал", command=self.update_stats_period_ui).pack(side='left', padx=2)
        ttk.Radiobutton(periods_frame, text="Год", variable=self.stats_period_var, 
                       value="Год", command=self.update_stats_period_ui).pack(side='left', padx=2)
        
        # Контейнер для элементов выбора (будет обновляться динамически)
        self.stats_selector_frame = ttk.Frame(period_frame)
        self.stats_selector_frame.pack(side='left', padx=10)
        
        # Кнопка обновления
        ttk.Button(period_frame, text="🔄 Обновить", command=self.update_stats).pack(side='left', padx=5)
        
        # === ГОРИЗОНТАЛЬНЫЙ КОНТЕЙНЕР ДЛЯ 4 БЛОКОВ (2 ряда по 2) ===
        stats_container = ttk.Frame(self.stats_frame)
        stats_container.pack(fill='both', expand=True, padx=self.scale_value(15), pady=self.scale_value(5))
        
        # Верхний ряд
        top_row = ttk.Frame(stats_container)
        top_row.pack(fill='both', expand=True, pady=2)
        top_row.columnconfigure(0, weight=1)
        top_row.columnconfigure(1, weight=1)
        
        # Блок 1: Соответствие тарифу
        self.tariff_frame = ttk.LabelFrame(top_row, text="Соответствие тарифу", padding=8)
        self.tariff_frame.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        
        # Блок 2: Стабильность
        self.stability_frame = ttk.LabelFrame(top_row, text="Стабильность", padding=8)
        self.stability_frame.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)
        
        # Нижний ряд
        bottom_row = ttk.Frame(stats_container)
        bottom_row.pack(fill='both', expand=True, pady=2)
        bottom_row.columnconfigure(0, weight=1)
        bottom_row.columnconfigure(1, weight=1)
        
        # Блок 3: Проблемные периоды
        self.problems_frame = ttk.LabelFrame(bottom_row, text="Проблемные периоды", padding=8)
        self.problems_frame.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        
        # Блок 4: Общая статистика
        self.total_stats_frame = ttk.LabelFrame(bottom_row, text="Общая статистика", padding=8)
        self.total_stats_frame.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)
        
        # Кнопки экспорта внизу
        export_frame = ttk.Frame(self.stats_frame)
        export_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))
        
        ttk.Button(export_frame, text="🧾 Экспорт отчета", command=self.export_stats_report).pack(side='left', padx=5)
        ttk.Button(export_frame, text="📋 Копировать в буфер", command=self.copy_stats_to_clipboard).pack(side='left', padx=5)
        
        # === ЗАПОЛНЕНИЕ БЛОКОВ ДАННЫМИ (ВРЕМЕННО) ===
        self.update_stats_display()
        
        # Инициализация UI для выбранного периода
        self.update_stats_period_ui()

    def update_stats_period_ui(self):
        """Обновление UI выбора периода в зависимости от выбранного типа"""
        # Очищаем контейнер
        for widget in self.stats_selector_frame.winfo_children():
            widget.destroy()
        
        period = self.stats_period_var.get()
        
        if period == "День":
            # Календарь для выбора даты
            from tkcalendar import DateEntry
            self.stats_date_picker = DateEntry(self.stats_selector_frame, width=10, 
                                               background='darkblue', foreground='white',
                                               date_pattern='dd.mm.yyyy', locale='ru_RU')
            self.stats_date_picker.pack(side='left')
            
        elif period == "Неделя":
            # Выбор недели и года
            ttk.Label(self.stats_selector_frame, text="Неделя:").pack(side='left')
            
            # Получаем текущую неделю
            current_week = datetime.now().isocalendar()[1]
            
            # Создаем список значений с тегами для выделения текущей недели
            week_values = [str(i) for i in range(1, 53)]
            
            self.stats_week_combo = ttk.Combobox(self.stats_selector_frame, 
                                                 values=week_values,
                                                 width=4, state='readonly')
            self.stats_week_combo.pack(side='left', padx=5)
            
            # Устанавливаем текущую неделю как выбранную
            self.stats_week_combo.set(str(current_week))
            
            # Настраиваем тег для выделения текущей недели (работает только в некоторых темах)
            # В качестве альтернативы - просто устанавливаем значение по умолчанию
            
            ttk.Label(self.stats_selector_frame, text="Год:").pack(side='left')
            self.stats_week_year_combo = ttk.Combobox(self.stats_selector_frame,
                                                      values=[str(y) for y in range(2026, datetime.now().year+1)],
                                                      width=4, state='readonly')
            self.stats_week_year_combo.pack(side='left', padx=5)
            self.stats_week_year_combo.set(str(datetime.now().year))
            
        elif period == "Месяц":
            # Выбор месяца и года
            months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                     'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
            ttk.Label(self.stats_selector_frame, text="Месяц:").pack(side='left')
            self.stats_month_combo = ttk.Combobox(self.stats_selector_frame, values=months,
                                                  width=9, state='readonly')
            self.stats_month_combo.pack(side='left', padx=5)
            self.stats_month_combo.set(months[datetime.now().month-1])
            
            ttk.Label(self.stats_selector_frame, text="Год:").pack(side='left')
            self.stats_month_year_combo = ttk.Combobox(self.stats_selector_frame,
                                                       values=[str(y) for y in range(2026, datetime.now().year+1)],
                                                       width=4, state='readonly')
            self.stats_month_year_combo.pack(side='left', padx=5)
            self.stats_month_year_combo.set(str(datetime.now().year))
            
        elif period == "Квартал":
            # Выбор квартала и года
            quarters = ['I', 'II', 'III', 'IV']  # ТОЛЬКО РИМСКИЕ ЦИФРЫ
            ttk.Label(self.stats_selector_frame, text="Квартал:").pack(side='left')
            self.stats_quarter_combo = ttk.Combobox(self.stats_selector_frame, values=quarters,
                                                    width=4, state='readonly')
            self.stats_quarter_combo.pack(side='left', padx=5)
            self.stats_quarter_combo.set(quarters[0])
            
            ttk.Label(self.stats_selector_frame, text="Год:").pack(side='left')
            self.stats_quarter_year_combo = ttk.Combobox(self.stats_selector_frame,
                                                         values=[str(y) for y in range(2026, datetime.now().year+1)],
                                                         width=6, state='readonly')
            self.stats_quarter_year_combo.pack(side='left', padx=5)
            self.stats_quarter_year_combo.set(str(datetime.now().year))
            
        elif period == "Год":
            # Выбор года
            ttk.Label(self.stats_selector_frame, text="Год:").pack(side='left')
            self.stats_year_combo = ttk.Combobox(self.stats_selector_frame,
                                                 values=[str(y) for y in range(2026, datetime.now().year+1)],
                                                 width=6, state='readonly')
            self.stats_year_combo.pack(side='left', padx=5)
            self.stats_year_combo.set(str(datetime.now().year))

    def update_stats_display(self):
        """Обновление отображения статистики в блоках"""
        try:
            # Очищаем старые данные
            for widget in self.tariff_frame.winfo_children():
                widget.destroy()
            for widget in self.stability_frame.winfo_children():
                widget.destroy()
            for widget in self.problems_frame.winfo_children():
                widget.destroy()
            for widget in self.total_stats_frame.winfo_children():
                widget.destroy()
            
            # === БЛОК 1: Соответствие тарифу ===
            planned = self.planned_speed_var.get() if hasattr(self, 'planned_speed_var') else 100
            ttk.Label(self.tariff_frame, text=f"(заявлено {planned} Mbps)", 
                     font=('Arial', 8)).pack(anchor='w')
            
            # Заглушка данных
            stats = self.get_stats_for_period()
            
            if stats:
                # Реальные данные
                self._fill_tariff_block(stats)
                self._fill_stability_block(stats)
                self._fill_problems_block(stats)
                self._fill_total_stats_block(stats)
            else:
                # Заглушка "нет данных"
                self._fill_placeholder_blocks()
                
        except Exception as e:
            self.logger.error(f"Ошибка обновления статистики: {e}")
            self._fill_placeholder_blocks()

    def _fill_placeholder_blocks(self):
        """Заполнение блоков заглушками (нет данных)"""
        # Блок 1: Соответствие тарифу
        ttk.Label(self.tariff_frame, text="📥 Загрузка: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        ttk.Label(self.tariff_frame, text="📤 Отдача: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        ttk.Label(self.tariff_frame, text="⏱️ Ниже тарифа: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        
        # Блок 2: Стабильность
        ttk.Label(self.stability_frame, text="📶 Пинг: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        ttk.Label(self.stability_frame, text="📊 Джиттер: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        ttk.Label(self.stability_frame, text="🌡️ Колебания: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        
        # Блок 3: Проблемные периоды
        ttk.Label(self.problems_frame, text="🕐 Худшее время: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        ttk.Label(self.problems_frame, text="📉 Худший день: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        
        # Блок 4: Общая статистика
        ttk.Label(self.total_stats_frame, text="📊 Всего измерений: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        ttk.Label(self.total_stats_frame, text="🏆 Лучшая скорость: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        ttk.Label(self.total_stats_frame, text="🐢 Худшая скорость: —", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)

    def _fill_tariff_block(self, stats):
        """Заполнение блока соответствия тарифу"""
        planned = self.planned_speed_var.get() if hasattr(self, 'planned_speed_var') else 100
        
        # Загрузка
        download_percent = (stats['avg_download'] / planned * 100) if planned > 0 else 0
        download_diff = planned - stats['avg_download']
        
        download_text = f"📥 Загрузка: {stats['avg_download']:.1f} Mbps  (тариф {planned} Mbps)"
        if download_diff > 0:
            download_text += f"  🔻 ниже на {download_diff/planned*100:.1f}%"
        ttk.Label(self.tariff_frame, text=download_text, font=('Arial', 9)).pack(anchor='w', pady=1)
        
        # Отдача
        upload_text = f"📤 Отдача: {stats['avg_upload']:.1f} Mbps"
        ttk.Label(self.tariff_frame, text=upload_text, font=('Arial', 9)).pack(anchor='w', pady=1)
        
        # Процент времени ниже тарифа (оценка по hourly данным)
        if stats['hourly']:
            low_count = sum(1 for h in stats['hourly'] if h[1] < planned * 0.9)
            low_percent = (low_count / len(stats['hourly'])) * 100
            ttk.Label(self.tariff_frame, text=f"⏱️ Ниже тарифа: {low_percent:.0f}% времени", 
                     font=('Arial', 9)).pack(anchor='w', pady=1)

    def _fill_stability_block(self, stats):
        """Заполнение блока стабильности"""
        # Пинг
        ping_text = f"📶 Пинг: {stats['avg_ping']:.1f} ms"
        ttk.Label(self.stability_frame, text=ping_text, font=('Arial', 9)).pack(anchor='w', pady=1)
        
        # Джиттер
        jitter_text = f"📊 Джиттер: {stats['avg_jitter']:.1f} ms"
        if stats['avg_jitter'] > 15:
            jitter_text += " ⚠️"
        ttk.Label(self.stability_frame, text=jitter_text, font=('Arial', 9)).pack(anchor='w', pady=1)        
       
        # Колебания скорости
        if stats['max_download'] > 0 and stats['min_download'] > 0:
            variation = ((stats['max_download'] - stats['min_download']) / stats['avg_download']) * 100
            ttk.Label(self.stability_frame, text=f"🌡️ Колебания: ±{variation:.0f}%", 
                     font=('Arial', 9)).pack(anchor='w', pady=1)

    def _fill_problems_block(self, stats):
        """Заполнение блока проблемных периодов"""
        period = self.stats_period_var.get()
        
        if period == "День" and stats['hourly']:
            # Получаем день недели для выбранной даты
            day_names = ['ПОНЕДЕЛЬНИК', 'ВТОРНИК', 'СРЕДА', 'ЧЕТВЕРГ', 'ПЯТНИЦА', 'СУББОТА', 'ВОСКРЕСЕНЬЕ']
            
            # Получаем выбранную дату из календаря
            if hasattr(self, 'stats_date_picker'):
                selected_date = self.stats_date_picker.get_date()
                day_of_week = selected_date.weekday()  # понедельник = 0
                day_name = day_names[day_of_week]
            else:
                day_name = ""
            
            ttk.Label(self.problems_frame, text=f"🕐 Пиковые нагрузки: {day_name}", 
                     font=('Arial', 9, 'bold')).pack(anchor='w', pady=1)
            
            # Сортируем по скорости (самые плохие часы)
            bad_hours = sorted(stats['hourly'], key=lambda x: x[1])[:3]
            for hour_data in bad_hours:
                hour = int(hour_data[0])
                speed = hour_data[1]
                ttk.Label(self.problems_frame, 
                         text=f"   {hour:02d}:00 - {hour+1:02d}:00  ({speed:.0f} Mbps)",
                         font=('Arial', 9)).pack(anchor='w')
        
        else:
            # Для других периодов показываем худшее время и худший день
            if stats['hourly']:
                worst_hour = min(stats['hourly'], key=lambda x: x[1])
                hour = int(worst_hour[0])
                ttk.Label(self.problems_frame, 
                         text=f"🕐 Худшее время: {hour:02d}:00 - {hour+1:02d}:00",
                         font=('Arial', 9)).pack(anchor='w', pady=1)
            
            if stats['daily']:
                worst_day = min(stats['daily'], key=lambda x: x[2])
                day_name = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][int(worst_day[0])]
                ttk.Label(self.problems_frame, 
                         text=f"📉 Худший день: {day_name} ({worst_day[1][8:10]}.{worst_day[1][5:7]})",
                         font=('Arial', 9)).pack(anchor='w', pady=1)

    def _fill_total_stats_block(self, stats):
        """Заполнение блока общей статистики"""
        ttk.Label(self.total_stats_frame, text=f"📊 Всего измерений: {stats['count']}", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        ttk.Label(self.total_stats_frame, text=f"🏆 Лучшая скорость: {stats['max_download']:.1f} Mbps", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)
        ttk.Label(self.total_stats_frame, text=f"🐢 Худшая скорость: {stats['min_download']:.1f} Mbps", 
                 font=('Arial', 9)).pack(anchor='w', pady=1)

    def get_stats_for_period(self):
        """Получение статистики за выбранный период из БД"""
        try:
            # Определяем начальную и конечную дату в зависимости от выбранного периода
            start_date, end_date = self._get_period_dates()
            if not start_date:
                return None
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Получаем статистику за период
            cursor.execute('''
                SELECT 
                    COUNT(*) as count,
                    AVG(download_speed) as avg_download,
                    MAX(download_speed) as max_download,
                    MIN(download_speed) as min_download,
                    AVG(upload_speed) as avg_upload,
                    AVG(ping) as avg_ping,
                    MAX(ping) as max_ping,
                    MIN(ping) as min_ping,
                    AVG(jitter) as avg_jitter,
                    MAX(jitter) as max_jitter
                FROM speed_measurements 
                WHERE timestamp BETWEEN ? AND ?
            ''', (start_date, end_date))
            
            result = cursor.fetchone()
            
            # Получаем измерения для анализа по часам и дням
            cursor.execute('''
                SELECT 
                    strftime('%H', timestamp) as hour,
                    AVG(download_speed) as avg_speed,
                    AVG(ping) as avg_ping,
                    COUNT(*) as count
                FROM speed_measurements 
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY hour
                ORDER BY avg_speed ASC
            ''', (start_date, end_date))
            
            hourly_data = cursor.fetchall()
            
            cursor.execute('''
                SELECT 
                    strftime('%w', timestamp) as day_of_week,
                    strftime('%Y-%m-%d', timestamp) as day,
                    AVG(download_speed) as avg_speed,
                    AVG(ping) as avg_ping,
                    COUNT(*) as count
                FROM speed_measurements 
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY day
                ORDER BY avg_speed ASC
            ''', (start_date, end_date))
            
            daily_data = cursor.fetchall()
            
            conn.close()
            
            if not result or not result[0] or result[0] < 3:
                return None
            
            # Формируем результат
            stats = {
                'count': result[0],
                'avg_download': result[1],
                'max_download': result[2],
                'min_download': result[3],
                'avg_upload': result[4],
                'avg_ping': result[5],
                'max_ping': result[6],
                'min_ping': result[7],
                'avg_jitter': result[8],
                'max_jitter': result[9],
                'hourly': hourly_data,
                'daily': daily_data
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики: {e}")
            return None

    def _get_period_dates(self):
        """Получение начальной и конечной даты для выбранного периода"""
        try:
            period = self.stats_period_var.get()
            end_date = datetime.now()
            start_date = None
            
            if period == "День":
                # Выбранная дата
                if hasattr(self, 'stats_date_picker'):
                    selected = self.stats_date_picker.get_date()
                    start_date = datetime(selected.year, selected.month, selected.day, 0, 0, 0)
                    end_date = datetime(selected.year, selected.month, selected.day, 23, 59, 59)
            
            elif period == "Неделя":
                # Выбранная неделя и год
                week = int(self.stats_week_combo.get())
                year = int(self.stats_week_year_combo.get())
                # Первый день года
                first_day = datetime(year, 1, 1)
                # Смещение до нужной недели
                start_date = first_day + timedelta(weeks=week-1)
                end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
            
            elif period == "Месяц":
                # Выбранный месяц и год
                months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                         'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
                month = months.index(self.stats_month_combo.get()) + 1
                year = int(self.stats_month_year_combo.get())
                start_date = datetime(year, month, 1)
                if month == 12:
                    end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
                else:
                    end_date = datetime(year, month+1, 1) - timedelta(seconds=1)
            
            elif period == "Квартал":
                # Выбранный квартал и год
                quarters = {'I': (1, 3), 'II': (4, 6), 'III': (7, 9), 'IV': (10, 12)}
                quarter = self.stats_quarter_combo.get()
                year = int(self.stats_quarter_year_combo.get())
                start_month, end_month = quarters[quarter]
                start_date = datetime(year, start_month, 1)
                if end_month == 12:
                    end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
                else:
                    end_date = datetime(year, end_month+1, 1) - timedelta(seconds=1)
            
            elif period == "Год":
                # Выбранный год
                year = int(self.stats_year_combo.get())
                start_date = datetime(year, 1, 1)
                end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
            
            if start_date:
                return (start_date.strftime('%Y-%m-%d %H:%M:%S'), 
                       end_date.strftime('%Y-%m-%d %H:%M:%S'))
            
            return None, None
            
        except Exception as e:
            self.logger.error(f"Ошибка определения дат периода: {e}")
            return None, None

    def update_stats(self):
        """Обновление статистики на основе выбранного периода"""
        self.logger.info("Обновление статистики...")
        self.update_stats_display()

    def export_stats_report(self):
        """Экспорт статистики в текстовый файл"""
        # TODO: Реализовать экспорт
        messagebox.showinfo("Экспорт", "Функция будет доступна в следующей версии")
        
    def copy_stats_to_clipboard(self):
        """Копирование статистики в буфер обмена"""
        # TODO: Реализовать копирование
        messagebox.showinfo("Копирование", "Функция будет доступна в следующей версии")

    def setup_settings_tab(self):
        """Настройка вкладки настроек"""

        # Основной фрейм с настройками
        settings_frame = ttk.LabelFrame(self.settings_frame, text="Настройки мониторинга", padding=20)
        settings_frame.pack(fill='both', expand=True, padx=self.scale_value(15), pady=self.scale_value(15))
        
        # === ВАЖНО: настраиваем растяжение колонки ===
        settings_frame.columnconfigure(0, weight=1)  # колонка 0 будет растягиваться
        # ===========================================
        
        # === ВЕРХНЯЯ СТРОКА: Интервал + Автозапуск ===
        top_frame = ttk.Frame(settings_frame)
        top_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=5)
        top_frame.columnconfigure(1, weight=1)
        
        # Интервал проверки (слева)
        ttk.Label(top_frame, text="Интервал проверки (мин):     ", font=self.scale_font('Arial', 10)).grid(row=0, column=0, sticky='w')
        self.interval_var = tk.IntVar(value=60)
        ttk.Spinbox(top_frame, from_=1, to=1440, textvariable=self.interval_var, width=8, font=self.scale_font('Arial', 10)).grid(row=0, column=1, padx=5, sticky='w')
        
        # Автозапуск (справа)
        self.auto_start_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top_frame, text="Автозапуск при старте Windows", 
                       variable=self.auto_start_var).grid(row=0, column=2, padx=(20,0), sticky='w')
        
        # === ВТОРАЯ СТРОКА: Заявленная скорость + Сворачивание ===
        middle_frame = ttk.Frame(settings_frame)
        middle_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=5)
        middle_frame.columnconfigure(1, weight=1)
        
        # Заявленная скорость (слева)
        ttk.Label(middle_frame, text="Заявленная скорость (Mbps):", font=self.scale_font('Arial', 10)).grid(row=0, column=0, sticky='w')
        
        # Фрейм для спинбокса и пояснения
        speed_frame = ttk.Frame(middle_frame)
        speed_frame.grid(row=0, column=1, padx=5, sticky='w')
        
        self.planned_speed_var = tk.IntVar(value=100)
        ttk.Spinbox(speed_frame, from_=0, to=10000, textvariable=self.planned_speed_var, 
                   width=8, font=self.scale_font('Arial', 10)).pack(side='left')
        
        ttk.Label(speed_frame, text="(0=не учитывать)", font=self.scale_font('Arial', 8), 
                 foreground='gray').pack(side='left', padx=5)
        
        # Сворачивание в трей (справа)
        self.minimize_to_tray_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(middle_frame, text="Сворачивать в трей", 
                       variable=self.minimize_to_tray_var).grid(row=0, column=2, padx=(20,0), sticky='w')
        
        # === ТРЕТЬЯ СТРОКА: Кнопка сохранения ===
        save_frame = ttk.Frame(settings_frame)
        save_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=10)
        
        save_button = ttk.Button(save_frame, text="💾 Сохранить настройки", command=self.save_settings)
        save_button.grid(row=0, column=0, sticky='w')

        # === ГОРИЗОНТАЛЬНЫЙ КОНТЕЙНЕР ДЛЯ ДВУХ БЛОКОВ ===
        horizontal_frame = ttk.Frame(settings_frame)
        horizontal_frame.grid(row=3, column=0, columnspan=1, sticky='ew', pady=10)
        horizontal_frame.columnconfigure(0, weight=1, uniform='group1')
        horizontal_frame.columnconfigure(1, weight=1, uniform='group1')

        # === ЛЕВЫЙ БЛОК: ПОРОГИ КАЧЕСТВА ===
        thresholds_frame = ttk.LabelFrame(horizontal_frame, text="Пороги качества соединения", padding=10)
        thresholds_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
        # Настройка растяжения внутри левого блока
        thresholds_frame.columnconfigure(1, weight=1)
        
        # Скорость скачивания
        ttk.Label(thresholds_frame, text="Скорость скачивания:", font=self.scale_font('Arial', 10)).grid(row=0, column=0, sticky='w', pady=5)
        ttk.Spinbox(thresholds_frame, from_=0, to=100, textvariable=self.download_threshold_var, width=6).grid(row=0, column=1, padx=5)
        ttk.Label(thresholds_frame, text="% от средней", font=self.scale_font('Arial', 9)).grid(row=0, column=2, sticky='w')
        
        # Пинг
        ttk.Label(thresholds_frame, text="Пинг:", font=self.scale_font('Arial', 10)).grid(row=1, column=0, sticky='w', pady=5)
        ttk.Spinbox(thresholds_frame, from_=0, to=500, textvariable=self.ping_threshold_var, width=6).grid(row=1, column=1, padx=5)
        ttk.Label(thresholds_frame, text="% от средней", font=self.scale_font('Arial', 9)).grid(row=1, column=2, sticky='w')
        
        # Джиттер (значение)
        ttk.Label(thresholds_frame, text="Джиттер:", font=self.scale_font('Arial', 10)).grid(row=2, column=0, sticky='w', pady=5)
        ttk.Spinbox(thresholds_frame, from_=0, to=100, textvariable=self.jitter_threshold_var, width=6).grid(row=2, column=1, padx=5)
        ttk.Label(thresholds_frame, text="мс", font=self.scale_font('Arial', 9)).grid(row=2, column=2, sticky='w')
        
        # Частота превышений джиттера
        jitter_freq_frame = ttk.Frame(thresholds_frame)
        jitter_freq_frame.grid(row=3, column=0, sticky='w', pady=5)
        
        ttk.Label(jitter_freq_frame, text="Частота джиттера:", font=self.scale_font('Arial', 10)).pack(side='left')
        
        # Знак вопроса для частоты джиттера
        jitter_freq_question = tk.Label(jitter_freq_frame, text="❓", font=('Arial', 10, 'bold'), fg="blue", cursor="hand2")
        jitter_freq_question.pack(side='left', padx=(2, 0))
        jitter_freq_question.bind("<Button-1>", lambda e: self.show_term_explanation("jitter_frequency"))
        
        ttk.Spinbox(thresholds_frame, from_=0, to=100, textvariable=self.jitter_frequency_var, width=6).grid(row=3, column=1, padx=5)
        ttk.Label(thresholds_frame, text="% измерений", font=self.scale_font('Arial', 9)).grid(row=3, column=2, sticky='w')

        # === ПРАВЫЙ БЛОК: ОЧИСТКА ИСТОРИИ ===
        clean_frame = ttk.LabelFrame(horizontal_frame, text="Очистка истории измерений", padding=10)
        clean_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
        # Чекбокс + выбор периода
        clean_row1 = ttk.Frame(clean_frame)
        clean_row1.pack(fill='x', pady=2)
        
        self.clean_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(clean_row1, text="Авто-очистка старше", 
                       variable=self.clean_enabled_var).pack(side='left')
        
        self.auto_clean_days_var = tk.IntVar(value=90)
        ttk.Spinbox(clean_row1, from_=30, to=365, increment=30, 
                   textvariable=self.auto_clean_days_var, width=6).pack(side='left', padx=5)
        ttk.Label(clean_row1, text="дней").pack(side='left')
        
        # Пояснение
        ttk.Label(clean_frame, text="(0 = не удалять)", font=('Arial', 8), 
                 foreground='gray').pack(anchor='w', pady=2)
        
        # Кнопка ручной очистки
        ttk.Button(clean_frame, text="🗑️ Очистить сейчас", 
                  command=self.manual_clean_old).pack(anchor='w', pady=5)

        # === НИЖНИЙ БЛОК: ИНФОРМАЦИЯ О ПРОГРАММЕ ===
        info_frame = ttk.LabelFrame(settings_frame, text="Информация", padding=10)
        info_frame.grid(row=4, column=0, columnspan=1, sticky='ew', pady=15)
        
        version_text = f"SpeedWatch v{__version__}"
        ttk.Label(info_frame, text=version_text, font=self.scale_font('Arial', 12) + ('bold',)).pack()
        ttk.Label(info_frame, text="Мониторинг скорости интернет-соединения", 
                 font=self.scale_font('Arial', 9)).pack()
        ttk.Label(info_frame, text=f"© {datetime.now().year}", 
                 font=self.scale_font('Arial', 8)).pack()


    def create_tray_icon(self):
        """Создание иконки в системном трее"""
        try:
            ###
            # Загружаем иконку из файла
            try:
                if getattr(sys, 'frozen', False):
                    # EXE режим - иконка рядом с exe
                    icon_path = os.path.join(self.base_dir, "icon.ico")
                else:
                    # Режим разработки - иконка в папке src
                    icon_path = os.path.join(self.base_dir, "src", "icon.ico")
                
                image = Image.open(icon_path)
                # При необходимости измените размер
                image = image.resize((64, 64), Image.Resampling.LANCZOS)                
            except Exception as e:
                self.logger.error(f"Не удалось загрузить иконку для трея: {e}")
                # Запасной вариант - создаем простую иконку
                image = Image.new('RGB', (64, 64), color='blue')
                draw = ImageDraw.Draw(image)
                draw.text((20, 25), "SPD", fill='white')
            
            self.tray_icon = pystray.Icon(
                "speedwatch", 
                image, 
                "SpeedWatch - Мониторинг скорости"
            )
            
            # Создаем начальное меню
            self.update_tray_menu()
            
            # Запускаем иконку в трее в отдельном потоке
            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()
            # Даем время на запуск потока
            time.sleep(0.2)

            self.logger.info("Иконка трея запущена")
        except Exception as e:
            self.logger.error(f"Ошибка создания иконки трея: {e}")


    def toggle_window_visibility(self):
        """Переключение видимости окна программы"""
        if self.root.state() == 'withdrawn' or not self.root.winfo_viewable():
            self.show_window()  # Будет записано "Приложение открыто"
        else:
            self.minimize_to_tray()  # Будет записано "Приложение свернуто в трей"
        
        # Обновляем меню
        self.update_tray_menu()

    def acquire_lock(self):
        """Захватить эксклюзивную блокировку файла"""
        try:
            if sys.platform == 'win32':
                import msvcrt
                # Открываем файл для исключительного доступа
                # 'a+' открывает для добавления, создает если не существует
                self.lock_file = open(self.lock_file_path, 'a+')
                # Пытаемся захватить эксклюзивный лок на первый байт
                # Если другой процесс уже держит лок - это будет ошибка
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                self.lock_file.seek(0)
                self.lock_file.write(str(os.getpid()))
                self.lock_file.truncate()
                self.lock_file.flush()
                self.logger.info(f"Файловый лок захвачен успешно: {self.lock_file_path}")
                return True
            else:
                # Unix: используем fcntl
                self.lock_file = open(self.lock_file_path, 'w')
                import fcntl
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.lock_file.write(str(os.getpid()))
                self.lock_file.flush()
                self.logger.info(f"Файловый лок захвачен успешно: {self.lock_file_path}")
                return True
        except (IOError, OSError, BlockingIOError) as e:
            self.logger.error(f"Не удалось захватить лок: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка захвата лока: {e}")
            return False

    def release_lock(self):
        """Освободить блокировку файла"""
        try:
            if self.lock_file:
                if sys.platform == 'win32':
                    import msvcrt
                    # Разблокируем файл
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                
                self.lock_file.close()
                self.lock_file = None
                self.logger.info("Файловый лок освобожден")
        except Exception as e:
            self.logger.error(f"Ошибка освобождения лока: {e}")
        
        # Пытаемся удалить файл лока
        try:
            if os.path.exists(self.lock_file_path):
                os.remove(self.lock_file_path)
        except Exception:
            pass

    def load_settings(self):
        """Загрузка настроек из БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT value FROM settings WHERE key='interval'")
            result = cursor.fetchone()
            if result:
                self.interval_var.set(int(result[0]))

            cursor.execute("SELECT value FROM settings WHERE key='planned_speed'")
            result = cursor.fetchone()
            if result:
                self.planned_speed_var.set(int(result[0]))
            else:
                self.planned_speed_var.set(100)

            # === НОВЫЕ ПОРОГИ ===
            cursor.execute("SELECT value FROM settings WHERE key='download_threshold'")
            result = cursor.fetchone()
            if result:
                self.download_threshold_var.set(int(result[0]))
            
            cursor.execute("SELECT value FROM settings WHERE key='ping_threshold'")
            result = cursor.fetchone()
            if result:
                self.ping_threshold_var.set(int(result[0]))
            
            cursor.execute("SELECT value FROM settings WHERE key='jitter_threshold'")
            result = cursor.fetchone()
            if result:
                self.jitter_threshold_var.set(int(result[0]))
            
            cursor.execute("SELECT value FROM settings WHERE key='jitter_frequency'")
            result = cursor.fetchone()
            if result:
                self.jitter_frequency_var.set(int(result[0]))
            # ===================

            # === НАСТРОЙКИ ОЧИСТКИ ===
            cursor.execute("SELECT value FROM settings WHERE key='clean_enabled'")
            result = cursor.fetchone()
            if result:
                self.clean_enabled_var.set(result[0] == '1')
            
            cursor.execute("SELECT value FROM settings WHERE key='clean_days'")
            result = cursor.fetchone()
            if result:
                self.auto_clean_days_var.set(int(result[0]))

            cursor.execute("SELECT value FROM settings WHERE key='auto_start'")
            result = cursor.fetchone()
            if result:
                self.auto_start_var.set(result[0] == '1')
            
            cursor.execute("SELECT value FROM settings WHERE key='minimize_to_tray'")
            result = cursor.fetchone()
            if result:
                self.minimize_to_tray_var.set(result[0] == '1')
            
            conn.close()
        except Error as e:
            self.logger.error(f"Ошибка загрузки настроек: {e}")


    def save_settings(self, restart=True, show_message=True):
        """Сохранение настроек в БД"""
        if hasattr(self, '_saving_settings') and self._saving_settings:
            return
        self._saving_settings = True
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Существующие настройки
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('interval', str(self.interval_var.get())))
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('planned_speed', str(self.planned_speed_var.get())))

            # === НОВЫЕ ПОРОГИ ===
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('download_threshold', str(self.download_threshold_var.get())))
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('ping_threshold', str(self.ping_threshold_var.get())))
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('jitter_threshold', str(self.jitter_threshold_var.get())))
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('jitter_frequency', str(self.jitter_frequency_var.get())))
            # ===================

            # === НАСТРОЙКИ ОЧИСТКИ ===
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('clean_enabled', '1' if self.clean_enabled_var.get() else '0'))
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('clean_days', str(self.auto_clean_days_var.get())))

            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('auto_start', '1' if self.auto_start_var.get() else '0'))
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('minimize_to_tray', '1' if self.minimize_to_tray_var.get() else '0'))
            
            conn.commit()
            conn.close()
           
            self.update_autostart()
            
            if show_message:
                self.apply_settings()
                messagebox.showinfo(
                    "Настройки сохранены", 
                    "Настройки успешно сохранены и применены!"
                )
                self.logger.info("Настройки сохранены и применены")
            
        except Error as e:
            self.logger.error(f"Ошибка сохранения настроек: {e}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {e}")
        finally:
            self._saving_settings = False

    def apply_settings(self):
        """Применить настройки без перезапуска программы"""
        self.logger.info("Применение настроек...")
        
        # 1. Обновить интервал мониторинга
        if hasattr(self, 'running') and self.running:
            # Если мониторинг запущен - перезапустим его с новым интервалом
            self.logger.info(f"Перезапуск мониторинга с новым интервалом: {self.interval_var.get()} мин")
            self.stop_monitoring()
            # Небольшая задержка перед запуском
            self.root.after(500, self.start_monitoring)
        else:
            self.logger.info("Мониторинг не активен, интервал будет применен при следующем запуске")
        
        # 2. Обновить название в трее (если нужно)
        if hasattr(self, 'tray_icon'):
            try:
                self.tray_icon.title = "SpeedWatch - Мониторинг скорости"
                self.logger.info("Название в трее обновлено")
            except:
                pass
        
        self.logger.info("Настройки применены")

    def reset_date_filter(self):
        """Сброс фильтра по дате"""
        first_date = self.get_first_measurement_date()
        self.date_from_entry.set_date(first_date)
        self.date_to_entry.set_date(datetime.now().date())
        self.update_log()       
   
# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def update_autostart(self):
        """Добавление/удаление из автозапуска Windows"""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            
            app_name = "InternetSpeedMonitor"
            
            # Путь к pythonw.exe (без окна консоли)
            python_dir = os.path.dirname(sys.executable)
            pythonw_path = os.path.join(python_dir, "pythonw.exe")
            
            if not os.path.exists(pythonw_path):
                pythonw_path = sys.executable
            
            if getattr(sys, 'frozen', False):
                script_path = sys.executable
            else:
                script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "main.py")
            
            if self.auto_start_var.get():
                cmd = f'"{pythonw_path}" "{script_path}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                self.logger.info(f"Добавлено в автозапуск: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            
            winreg.CloseKey(key)
        except Exception as e:
            self.logger.error(f"Ошибка обновления автозапуска: {e}")
# endregion

    def run_speed_test(self):
        """Запуск теста скорости интернета"""
        if self.test_in_progress:
            self.logger.warning("Тест уже выполняется, пропускаем")
            return
            
        self.logger.info("ЗАПУСК ТЕСТА СКОРОСТИ")
        self.test_in_progress = True
        
        # Останавливаем анимацию ожидания
        self.stop_wait_animation()
        
        self.status_var.set("Выполняется тест скорости...")
        self.test_button.config(state='disabled')
        
        # Запускаем анимацию теста
        self.start_test_animation()
        
        # Сбрасываем таймер отсчета
        self.next_test_var.set("--:--:--")
        
        # Запускаем тест в отдельном потоке
        test_thread = threading.Thread(target=self._perform_speed_test, daemon=True)
        test_thread.start()

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def start_test_animation(self):
        """Запуск анимации выполнения теста в статус-баре"""
        if not self.test_in_progress:
            return
            
        # Обновляем статус в окне с анимацией (текст статичный, меняется только слеш)
        self.animation_index = (self.animation_index + 1) % len(self.animation_chars)
        status_text = f"Выполняется тест скорости {self.animation_chars[self.animation_index]}"
        self.status_var.set(status_text)
        
        # Запускаем следующее обновление через 200 мс
        self.animation_job = self.root.after(200, self.start_test_animation)
# endregion

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def start_wait_animation(self):
        """Запуск анимации ожидания следующего теста"""
        if not self.running or self.test_in_progress:
            return
            
        # Обновляем точки
        self.wait_animation_dots = (self.wait_animation_dots % 3) + 1
        dots = '.' * self.wait_animation_dots
        
        self.status_var.set(f"Отсчет времени до следующей проверки{dots}")
        
        # Запускаем следующее обновление через 500 мс
        self.wait_animation_job = self.root.after(500, self.start_wait_animation)
# endregion

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def stop_wait_animation(self):
        """Остановка анимации ожидания"""
        if self.wait_animation_job:
            self.root.after_cancel(self.wait_animation_job)
            self.wait_animation_job = None
# endregion

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def stop_test_animation(self):
        """Остановка анимации теста"""
        if self.animation_job:
            self.root.after_cancel(self.animation_job)
            self.animation_job = None
        
        # Восстанавливаем статус
        if self.running:
            # Если мониторинг работает, запускаем анимацию ожидания
            self.start_wait_animation()
            # Обновляем таймер
            self.update_next_test_timer()
        else:
            self.status_var.set("Ожидание команды")
            if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
                print("\rОжидание команды" + " " * 20, flush=True)
# endregion

    def _perform_speed_test(self):
        """Выполнение теста скорости через внешний openspeedtest-cli"""
        # Определяем переменные ДО try, чтобы они были видны везде
        stop_animation = threading.Event()
        console_animation_thread = None
        process = None  # для timeout
        
        try:
            import os
            import tempfile
            import re
            import subprocess
            
            # Запускаем анимацию в консоли, если она доступна
            if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():  # Проверяем, что вывод идет в консоль
                console_animation_thread = threading.Thread(
                    target=self._console_animation, 
                    args=(stop_animation,),
                    daemon=True
                )
                console_animation_thread.start()
            
            # Проверяем интернет-соединение перед началом
            if not self.check_internet_connection():
                error_msg = "Нет подключения к интернету"
                self.logger.error(error_msg)
                self.root.after(0, lambda: self._update_ui_with_error(error_msg))
                # Останавливаем анимацию
                stop_animation.set()
                if console_animation_thread and console_animation_thread.is_alive():
                    console_animation_thread.join(timeout=1)
                self.test_in_progress = False
                return

            self.root.after(0, lambda: self.status_var.set("Запуск теста скорости..."))
            self.logger.info("Запуск теста скорости через openspeedtest-cli...")

            # Путь к скрипту openspeedtest-cli
            if getattr(sys, 'frozen', False):
                # В EXE режиме файл рядом с exe
                cli_path = os.path.join(os.path.dirname(sys.executable), "openspeedtest-cli-fixed")
            else:
                # В режиме разработки файл в папке src
                cli_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openspeedtest-cli-fixed")

            if not os.path.exists(cli_path):
                error_msg = f"Файл openspeedtest-cli не найден по пути: {cli_path}"
                self.logger.error(error_msg)
                self.root.after(0, lambda: self._update_ui_with_error(error_msg))
                # Останавливаем анимацию
                stop_animation.set()
                if console_animation_thread and console_animation_thread.is_alive():
                    console_animation_thread.join(timeout=1)
                self.test_in_progress = False
                return

            # Запускаем процесс с перенаправлением вывода в файл
            stdout_temp = tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8', delete=False, suffix='.txt')
            stderr_temp = tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8', delete=False, suffix='.txt')
            stdout_temp.close()
            stderr_temp.close()

            # Определяем какой python использовать
            if getattr(sys, 'frozen', False):
                # В EXE режиме используем python из системы
                python_exe = "C:\\Python312\\python.exe"
                if not os.path.exists(python_exe):
                    # Пробуем найти python через where
                    try:
                        result = subprocess.run(["where", "python"], capture_output=True, text=True, shell=True)
                        if result.returncode == 0 and result.stdout.strip():
                            python_exe = result.stdout.strip().split('\n')[0]
                            self.logger.info(f"Python found via where: {python_exe}")
                    except Exception as e:
                        self.logger.warning(f"Error finding python: {e}")
            else:
                python_exe = sys.executable

            with open(stdout_temp.name, 'w', encoding='utf-8') as out_f, \
                 open(stderr_temp.name, 'w', encoding='utf-8') as err_f:

                process = subprocess.Popen(
                    [python_exe, cli_path],
                    stdout=out_f,
                    stderr=err_f,
                    text=True,
                    shell=True
                )

                process.wait(timeout=120)

            # Читаем результаты
            with open(stdout_temp.name, 'rb') as f:
                stdout_bytes = f.read()            
           
            stdout = None
            for encoding in ['utf-8', 'cp1251', 'cp866']:
                try:
                    stdout = stdout_bytes.decode(encoding)
                    self.logger.info(f"Декодировано в {encoding}")
                    break
                except:
                    continue

            with open(stderr_temp.name, 'rb') as f:
                stderr_bytes = f.read()
            stderr = stderr_bytes.decode('utf-8', errors='ignore')
            
            if stderr:
                self.logger.warning(f"CLI stderr: {stderr}")

            os.unlink(stdout_temp.name)
            os.unlink(stderr_temp.name)

            # Парсим информацию о сервере и IP
            server_name = "OpenSpeedTest"
            server_city = "Неизвестно"
            server_provider = "Неизвестно"
            client_ip = "Неизвестно"
            
            lines = stdout.split('\n')
            for line in lines:
                if "Лучший сервер найден:" in line:
                    try:
                        full = line.split("Лучший сервер найден:", 1)[1].strip()
                        clean = re.sub(r'\s*\(\d+\.?\d*\s*мс\s*\)\s*$', '', full)
                        
                        # Пытаемся выделить город и провайдера
                        if '(' in clean:
                            # Формат: "Москва, Россия (СПУТНИК)"
                            parts = clean.split('(', 1)
                            city_country = parts[0].strip()
                            provider = parts[1].rstrip(')').strip()
                        elif ',' in clean:
                            # Формат: "Москва, Россия, СПУТНИК" или "Москва, Россия"
                            parts = clean.split(',', 1)
                            city_country = parts[0].strip()
                            remaining = parts[1].strip() if len(parts) > 1 else ""
                            
                            if ',' in remaining:
                                # Еще одна запятая - значит есть провайдер
                                subparts = remaining.split(',', 1)
                                provider = subparts[1].strip()
                            else:
                                provider = remaining if remaining else "Неизвестно"
                        else:
                            city_country = clean
                            provider = "Неизвестно"
                        
                        server_name = clean
                        server_city = city_country
                        server_provider = provider
                        break
                    except Exception as e:
                        self.logger.warning(f"Error parsing server info: {e}")
                
                # Парсим внешний IP (если есть в выводе)
                if "Your IP:" in line or "Client IP:" in line or "IP:" in line:
                    try:
                        parts = line.split(':', 1)
                        if len(parts) > 1:
                            ip_candidate = parts[1].strip()
                            # Простая проверка что это похоже на IP
                            if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip_candidate):
                                client_ip = ip_candidate
                    except:
                        pass
            
            self.logger.info(f"Server: {server_name}, City: {server_city}, Provider: {server_provider}, Client IP: {client_ip}")

            # Парсим значения (инициализируем как None, чтобы отличать от 0)
            download_speed = None
            upload_speed = None
            ping = None
            jitter = None

            lines = stdout.split('\n')[-50:]
            for line in lines:
                line = line.strip()
                
                if "Download:" in line and download_speed is None:
                    numbers = re.findall(r"(\d+\.?\d*)", line)
                    if numbers:
                        download_speed = float(numbers[-1])
                        self.logger.info(f"Download: {download_speed:.2f} Mbps")
                
                if "Upload:" in line and upload_speed is None:
                    numbers = re.findall(r"(\d+\.?\d*)", line)
                    if numbers:
                        upload_speed = float(numbers[-1])
                        self.logger.info(f"Upload: {upload_speed:.2f} Mbps")
                
                if "Ping:" in line and ping is None:
                    numbers = re.findall(r"(\d+\.?\d*)", line)
                    if numbers:
                        ping = float(numbers[-1])
                        self.logger.info(f"Ping: {ping:.2f} ms")
                
                if "Jitter:" in line and jitter is None:
                    numbers = re.findall(r"(\d+\.?\d*)", line)
                    if numbers:
                        jitter = float(numbers[-1])
                        self.logger.info(f"Jitter: {jitter:.2f} ms")

            # Проверяем, что получили хотя бы что-то
            if download_speed is None and upload_speed is None and ping is None and jitter is None:
                error_msg = "Не удалось получить данные о скорости из вывода CLI"
                self.logger.error(error_msg)
                self.logger.error(f"Full stdout: {stdout}")
                self.root.after(0, lambda: self._update_ui_with_error(error_msg))
                stop_animation.set()
                if console_animation_thread and console_animation_thread.is_alive():
                    console_animation_thread.join(timeout=1)
                self.test_in_progress = False
                return

            # Останавливаем консольную анимацию
            stop_animation.set()
            if console_animation_thread and console_animation_thread.is_alive():
                console_animation_thread.join(timeout=1)

            # Получаем информацию об IP и провайдере
            ip_info = self.get_external_ip_info()
            client_ip = ip_info.get('ip', 'Неизвестно')
            provider_name = ip_info.get('provider', 'Неизвестно')
            connection_type = ip_info.get('connection_type', 'Неизвестно')
            
            self.logger.info(f"IP Info: {ip_info}")
            self.logger.info(f"Client IP: {client_ip}, Provider: {provider_name}, Type: {connection_type}")
            
            # Сохраняем результаты с полной информацией  <<<--- ТОЛЬКО ЭТОТ
            self.save_test_results(
                download_speed, 
                upload_speed, 
                ping, 
                jitter, 
                server_name,
                server_city,
                server_provider,
                client_ip,
                provider_name,
                connection_type
            )

            # Обновляем интерфейс с полученными значениями
            self.root.after(0, lambda: self._update_ui_with_results_and_status(
                download_speed or 0, 
                upload_speed or 0, 
                ping or 0, 
                jitter or 0, 
                server_name,
                "Тест завершен (частичные данные)" if (download_speed is None or upload_speed is None) else "Тест завершен"
            ))

            self.logger.info(f"Тест завершен: Download={download_speed if download_speed is not None else 'N/A'} Mbps, "
                           f"Upload={upload_speed if upload_speed is not None else 'N/A'} Mbps, "
                           f"Ping={ping if ping is not None else 'N/A'} ms")

        except subprocess.TimeoutExpired:
            if process:
                process.kill()
            error_msg = "Тест превысил время ожидания (60 сек)"
            self.logger.error(error_msg)
            self.root.after(0, lambda: self._update_ui_with_error(error_msg))
            # Останавливаем анимацию
            stop_animation.set()
            if console_animation_thread and console_animation_thread.is_alive():
                console_animation_thread.join(timeout=1)
            self.test_in_progress = False
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Ошибка теста скорости: {error_msg}")
            self.root.after(0, lambda msg=error_msg: self._update_ui_with_error(msg))
            # Останавливаем анимацию
            stop_animation.set()
            if console_animation_thread and console_animation_thread.is_alive():
                console_animation_thread.join(timeout=1)
            self.test_in_progress = False

            # После успешного теста
            self.logger.info(f"Тест завершен. self.running = {self.running}")

        finally:
            self.logger.info(f"FINALLY: self.running = {self.running}, self.test_in_progress = {self.test_in_progress}")
            # Останавливаем анимацию в статус-баре
            self.root.after(0, self.stop_test_animation)
            self.test_in_progress = False
            self.root.after(0, lambda: self.test_button.config(state='normal'))

            # Принудительный сбор мусора
            import gc
            gc.collect()
            gc.collect()  # Дважды для надёжности
            
            # ВАЖНО: После завершения теста проверяем, нужно ли запустить мониторинг
            if self.running:
                self.logger.info("Мониторинг активен, обновляем таймер следующего теста")
                self.root.after(0, self.update_next_test_timer)
            else:
                self.logger.info("Мониторинг не активен, таймер не обновляется")

    def _update_ui_with_results(self, download, upload, ping, jitter, server):
        """Обновление интерфейс с результатами"""
        self.download_var.set(f"{download:.2f} Mbps")
        self.upload_var.set(f"{upload:.2f} Mbps")
        self.ping_var.set(f"{ping:.2f} ms")
        self.jitter_var.set(f"{jitter:.2f} ms")
        # ИЗМЕНЕНО: формат даты с "YYYY-MM-DD HH:MM:SS" на "DD.MM.YY HH:MM"
        self.last_check_var.set(datetime.now().strftime("%d.%m.%y %H:%M"))
        self.status_var.set("Тест завершен")
        self.test_button.config(state='normal')

    def _update_ui_with_results_and_status(self, download, upload, ping, jitter, server, status_message):
        """Обновление интерфейс с результатами и кастомным статусом"""
        self.download_var.set(f"{download:.2f} Mbps" if download is not None else "Ошибка")
        self.upload_var.set(f"{upload:.2f} Mbps" if upload is not None else "Ошибка")
        self.ping_var.set(f"{ping:.2f} ms" if ping is not None else "Ошибка")
        self.jitter_var.set(f"{jitter:.2f} ms" if jitter is not None else "Ошибка")
        self.last_check_var.set(datetime.now().strftime("%d.%m.%y %H:%M"))
        self.status_var.set(status_message)
        self.test_button.config(state='normal')
        self.update_planned_speed_indicator()


    def _update_ui_with_error(self, error_msg):
        """Обновление интерфейс при ошибке"""
        self.download_var.set("Ошибка")
        self.upload_var.set("Ошибка")
        self.ping_var.set("Ошибка")
        self.jitter_var.set("Ошибка")
        self.status_var.set(f"Ошибка: {error_msg}")
        self.test_button.config(state='normal')
        messagebox.showerror("Ошибка", f"Не удалось выполнить тест скорости: {error_msg}")

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def _console_animation(self, stop_event):
        """Анимация в консоли во время теста (мигает только слеш)"""
        chars = ['-', '\\', '|', '/']
        i = 0
        # Печатаем статичный текст один раз
        print("\rТест выполняется ", end='', flush=True)
        while not stop_event.is_set():
            # Обновляем только слеш
            print(f"\rТест выполняется {chars[i % len(chars)]}", end='', flush=True)
            i += 1
            time.sleep(0.2)
        # После завершения очищаем строку
        print("\r" + " " * 30 + "\r", end='', flush=True)
# endregion

    def save_test_results(self, download, upload, ping, jitter, server, server_city="", server_provider="", 
                          client_ip="", client_provider="", connection_type=""):
        """Сохранение результатов теста в БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Проверяем наличие колонок
            cursor.execute("PRAGMA table_info(speed_measurements)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Добавляем новые колонки если их нет
            new_columns = {
                'server_city': 'TEXT',
                'server_provider': 'TEXT',
                'client_ip': 'TEXT',
                'client_provider': 'TEXT',
                'connection_type': 'TEXT'
            }
            
            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    cursor.execute(f'ALTER TABLE speed_measurements ADD COLUMN {col_name} {col_type}')
            
            cursor.execute('''
                INSERT INTO speed_measurements 
                (timestamp, download_speed, upload_speed, ping, jitter, server, 
                 server_city, server_provider, client_ip, client_provider, connection_type) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'), 
                download, upload, ping, jitter, server,
                server_city, server_provider, client_ip, client_provider, connection_type
            ))
            
            conn.commit()
            conn.close()
            
            # ЯВНОЕ ОБНОВЛЕНИЕ ИНТЕРФЕЙСА
            self.download_var.set(f"{download:.2f} Mbps" if download else "0 Mbps")
            self.upload_var.set(f"{upload:.2f} Mbps" if upload else "0 Mbps")
            self.ping_var.set(f"{ping:.2f} ms" if ping else "0 ms")
            self.jitter_var.set(f"{jitter:.2f} ms" if jitter else "0 ms")
            
            # ЯВНОЕ ОБНОВЛЕНИЕ ИНФОРМАЦИИ О ПОДКЛЮЧЕНИИ
            self.provider_var.set(client_provider if client_provider else "—")
            self.connection_type_var.set(connection_type if connection_type else "—")
            self.server_info_var.set(server if server else "—")
            self.ip_address_var.set(client_ip if client_ip else "—")
            
            self.last_check_var.set(datetime.now().strftime("%d.%m.%y %H:%M"))
            self.update_monitor_tab_colors()
            self.update_planned_speed_indicator()
            
            # Принудительное обновление окна
            self.root.update_idletasks()
            
            self.root.after(0, self.update_log)
#           self.root.after(0, self.update_graph)
            
            self.logger.info(f"Сохранены результаты: Download={download}, Upload={upload}, Ping={ping}, Jitter={jitter}")
            self.logger.info(f"UI обновлен: провайдер={client_provider}, тип={connection_type}")
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения результатов: {e}")

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def start_monitoring(self):
        """Запуск периодического мониторинга"""
        if self.running:
            self.logger.info("Мониторинг уже запущен")
            return

        self.logger.info("ЗАПУСК МОНИТОРИНГА")
        self.running = True
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        
        # Сбрасываем таймер следующего теста
        self.next_test_time = datetime.now() + timedelta(minutes=self.interval_var.get())
        self.update_next_test_timer()
        
        # Запускаем поток мониторинга
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        # Выполняем анализ качества при старте мониторинга
        self.root.after(1000, self.analyze_connection_quality)
        
        self.status_var.set("Мониторинг запущен")
        self.logger.info("Мониторинг запущен")
# endregion

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.logger.info("ОСТАНОВКА МОНИТОРИНГА")
        self.running = False
        
        # Останавливаем анимацию ожидания
        self.stop_wait_animation()
        
        # Очищаем консоль
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            print("\r" + " " * 50 + "\r", end='', flush=True)
        
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.test_button.config(state='normal')
        self.status_var.set("Мониторинг остановлен")
        self.next_test_var.set("--:--:--")
        self.logger.info("Мониторинг остановлен")
# endregion

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def _monitoring_loop(self):
        """Цикл периодического мониторинга"""
        while self.running:
            try:
                # Выполняем тест
                self.run_speed_test()
                
                # Ждем указанный интервал
                wait_time = self.interval_var.get() * 60  # Конвертируем в секунды
                for _ in range(wait_time):
                    if not self.running:
                        break
                    time.sleep(1)
                    self.update_next_test_timer()
                    
            except Exception as e:
                self.logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(60)
# endregion

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
    def update_next_test_timer(self):
        """Обновление таймера до следующего теста"""
        if not self.running:
            return
        
        if self.test_in_progress:
            return
            
        now = datetime.now()
        if self.next_test_time:
            time_left = self.next_test_time - now
            if time_left.total_seconds() > 0:
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                timer_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                self.next_test_var.set(timer_text)
                
                if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
                    print(f"\rСледующий тест через: {timer_text}   ", end='', flush=True)
                
                if not self.wait_animation_job:
                    self.start_wait_animation()
            else:
                self.next_test_time = now + timedelta(minutes=self.interval_var.get())
# endregion

    def update_log(self):
        """Обновление журнала измерений"""
        try:
            # Очищаем текущие данные
            for item in self.log_tree.get_children():
                self.log_tree.delete(item)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Строим запрос с фильтром
            query = '''
                SELECT id, timestamp, download_speed, upload_speed, ping, jitter, server 
                FROM speed_measurements 
                WHERE 1=1
            '''
            params = []
            
            # Применяем фильтр по датам
            try:
                date_from = self.date_from_entry.get_date()  # Возвращает datetime.date
                date_to = self.date_to_entry.get_date()
                
                query += " AND date(timestamp) BETWEEN ? AND ?"
                params.extend([date_from.strftime('%Y-%m-%d'), date_to.strftime('%Y-%m-%d')])
            except Exception as e:
                self.logger.error(f"Ошибка обработки дат фильтра: {e}")
            
            query += " ORDER BY timestamp DESC LIMIT 1000"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Сначала рассчитываем средние значения для определения порогов
            if rows:
                # Фильтруем значения которые не None
                download_speeds = [row[2] for row in rows if row[2]]
                upload_speeds = [row[3] for row in rows if row[3]]
                pings = [row[4] for row in rows if row[4]]
                jitters = [row[5] for row in rows if row[5]]
                
                # Рассчитываем средние и пороги (ТОЛЬКО от средней, для журнала)
                avg_download = sum(download_speeds) / len(download_speeds) if download_speeds else 0
                avg_upload = sum(upload_speeds) / len(upload_speeds) if upload_speeds else 0
                avg_ping = sum(pings) / len(pings) if pings else 0
                avg_jitter = sum(jitters) / len(jitters) if jitters else 0
                
                # Пороги только от средней (25% правила)
                threshold_download = avg_download * 0.75  # -25% от средней
                threshold_upload = avg_upload * 0.75      # -25% от средней
                threshold_ping = avg_ping * 1.25          # +25% от средней
                
                self.avg_download_var.set(f"{avg_download:.2f} Mbps")
                self.avg_upload_var.set(f"{avg_upload:.2f} Mbps")
                self.avg_ping_var.set(f"{avg_ping:.2f} ms")
                self.avg_jitter_var.set(f"{avg_jitter:.2f} ms")
            else:
                threshold_download = 0
                threshold_upload = 0
                threshold_ping = 0
                self.avg_download_var.set("0 Mbps")
                self.avg_upload_var.set("0 Mbps")
                self.avg_ping_var.set("0 ms")
                self.avg_jitter_var.set("0 ms")

            # Добавляем данные в таблицу с форматированием
            for row in rows:
                # Форматируем дату из формата "YYYY-MM-DD HH:MM:SS.ffffff" в "DD.MM.YY HH:MM"
                timestamp = row[1]
                if timestamp and isinstance(timestamp, str):
                    try:
                        dt = datetime.strptime(timestamp.split('.')[0], '%Y-%m-%d %H:%M:%S')
                        formatted_timestamp = dt.strftime('%d.%m.%y %H:%M')
                    except:
                        formatted_timestamp = timestamp
                else:
                    formatted_timestamp = "N/A"

                # Форматируем значения с проверкой на низкие значения
                download_str = f"{row[2]:.2f}" if row[2] else "N/A"
                upload_str = f"{row[3]:.2f}" if row[3] else "N/A"
                ping_str = f"{row[4]:.2f}" if row[4] else "N/A"
                jitter_str = f"{row[5]:.2f}" if row[5] else "N/A"
                
                # Проверяем каждое значение и создаем форматированные строки с возможными тегами
                tags = []
                
                # Проверяем загрузку (ниже на 25%)
                if row[2] and row[2] < threshold_download:
                    tags.append('low_download')
                    download_str = f"▼{download_str}"
                
                # Проверяем отдачу (ниже на 25%)
                if row[3] and row[3] < threshold_upload:
                    tags.append('low_upload')
                    upload_str = f"▼{upload_str}"
                
                # Проверяем пинг (выше на 25%)
                if row[4] and row[4] >= threshold_ping:
                    tags.append('high_ping')
                    ping_str = f"▲{ping_str}"
                
                # Проверяем джиттер (выше на 25%)
                if row[5] and row[5] >= threshold_ping * 1.25:
                    tags.append('high_jitter')
                    jitter_str = f"▲{jitter_str}"
                
                # Убираем дубликаты тегов
                tags = list(set(tags))
                
                formatted_row = (
                    row[0],
                    formatted_timestamp,
                    download_str,
                    upload_str,
                    ping_str,
                    jitter_str,
                    row[6] or "N/A"
                )
                
                # Вставляем строку ТОЛЬКО ОДИН РАЗ
                item_id = self.log_tree.insert('', 'end', values=formatted_row, tags=tuple(tags))

            conn.close()
            
            # Обновляем статус
            self.status_var.set(f"Загружено записей: {len(rows)}")
            
        except Error as e:
            self.logger.error(f"Ошибка обновления журнала: {e}")
            self.status_var.set(f"Ошибка загрузки журнала: {e}")

    def auto_resize_columns(self):
        """Автоматическая настройка ширины столбцов в журнале"""
        try:
            columns = self.log_tree['columns']
            for i, col in enumerate(columns):
                max_width = tk.font.Font().measure(col.title())
                for item in self.log_tree.get_children():
                    cell_value = self.log_tree.set(item, col)
                    cell_width = tk.font.Font().measure(str(cell_value))
                    if cell_width > max_width:
                        max_width = cell_width
                
                # Добавляем отступ и устанавливаем ширину с сохранением выравнивания
                new_width = min(max_width + 20, 300)
                
                # Устанавливаем автоширину с возможностью растяжения
                if i >= 0 and i <= 4:  # Столбцы 1-5 (ID, Время, Загрузка, Отдача, Пинг)
                    self.log_tree.column(col, width=new_width, anchor=tk.CENTER, stretch=True)
                else:  # Столец Сервер
                    self.log_tree.column(col, width=new_width, anchor=tk.W, stretch=True)
        except Exception as e:
            self.logger.error(f"Ошибка автонастройки столбцов: {e}")           
          
# region ### Можно осторожно менять
    def update_graph(self):
        """Обновление графиков"""
        # Защита от множественных одновременных вызовов
        if hasattr(self, '_updating_graph') and self._updating_graph:
            print("График уже обновляется, пропускаем")
            return
            
        self._updating_graph = True
        
        try:
            import matplotlib.pyplot as plt
            import gc
            
            # КРИТИЧЕСКИ ВАЖНО: закрываем все старые фигуры matplotlib
            plt.close('all')
            gc.collect()
            
            self.fig.clear()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Определяем период
            period = self.graph_period_var.get()
            
            # ========== ИСПРАВЛЕННЫЙ БЛОК ДЛЯ ПЕРИОДА "ДЕНЬ" ==========
            if period == "День":
                # Выбранная дата
                if hasattr(self, 'graph_date_picker'):
                    selected_date = self.graph_date_picker.get_date()
                    start_date = datetime(selected_date.year, selected_date.month, selected_date.day, 0, 0, 0)
                    end_date = datetime(selected_date.year, selected_date.month, selected_date.day, 23, 59, 59)
                    
                    # !!! ВАЖНО: для дня используем GROUP BY по часам, чтобы уменьшить количество точек
                    cursor.execute('''
                        SELECT 
                            strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
                            AVG(download_speed) as avg_download,
                            AVG(upload_speed) as avg_upload,
                            AVG(ping) as avg_ping,
                            AVG(jitter) as avg_jitter
                        FROM speed_measurements 
                        WHERE timestamp BETWEEN ? AND ?
                        GROUP BY hour
                        ORDER BY hour
                    ''', (start_date.strftime('%Y-%m-%d %H:%M:%S'), 
                          end_date.strftime('%Y-%m-%d %H:%M:%S')))
                    
                    # Явно удаляем переменную даты
                    del selected_date
                else:
                    # Если нет выбора даты, берем последние 24 часа
                    start_date = datetime.now() - timedelta(days=1)
                    end_date = datetime.now()
                    cursor.execute('''
                        SELECT 
                            strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
                            AVG(download_speed) as avg_download,
                            AVG(upload_speed) as avg_upload,
                            AVG(ping) as avg_ping,
                            AVG(jitter) as avg_jitter
                        FROM speed_measurements 
                        WHERE timestamp BETWEEN ? AND ?
                        GROUP BY hour
                        ORDER BY hour
                    ''', (start_date.strftime('%Y-%m-%d %H:%M:%S'), 
                          end_date.strftime('%Y-%m-%d %H:%M:%S')))
            # ========== КОНЕЦ ИСПРАВЛЕННОГО БЛОКА ==========
                    
            elif period == "Неделя":
                # Выбранная неделя
                if hasattr(self, 'graph_week_combo') and hasattr(self, 'graph_year_combo'):
                    week = int(self.graph_week_combo.get())
                    year = int(self.graph_year_combo.get())
                    # Правильный расчет первого дня недели
                    first_day = datetime(year, 1, 1)
                    # Добавляем дни до нужной недели
                    days_to_add = (week - 1) * 7
                    start_date = first_day + timedelta(days=days_to_add)
                    # Корректируем, чтобы первый день был понедельником
                    while start_date.weekday() != 0:  # 0 = понедельник
                        start_date -= timedelta(days=1)
                    end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
                    
                    cursor.execute('''
                        SELECT timestamp, download_speed, upload_speed, ping, jitter 
                        FROM speed_measurements 
                        WHERE timestamp BETWEEN ? AND ?
                        ORDER BY timestamp
                    ''', (start_date.strftime('%Y-%m-%d %H:%M:%S'), 
                          end_date.strftime('%Y-%m-%d %H:%M:%S')))
                    
                    # Явно удаляем временные переменные
                    del week, year, first_day, days_to_add
                else:
                    start_date = datetime.now() - timedelta(days=7)
                    end_date = datetime.now()
                    cursor.execute('''
                        SELECT timestamp, download_speed, upload_speed, ping, jitter 
                        FROM speed_measurements 
                        WHERE timestamp BETWEEN ? AND ?
                        ORDER BY timestamp
                    ''', (start_date.strftime('%Y-%m-%d %H:%M:%S'), 
                          end_date.strftime('%Y-%m-%d %H:%M:%S')))
                    
            elif period == "Месяц":
                # Выбранный месяц (цифрой)
                if hasattr(self, 'graph_month_combo') and hasattr(self, 'graph_month_year_combo'):
                    month = int(self.graph_month_combo.get())
                    year = int(self.graph_month_year_combo.get())
                    start_date = datetime(year, month, 1)
                    if month == 12:
                        end_date = datetime(year+1, 1, 1) - timedelta(seconds=1)
                    else:
                        end_date = datetime(year, month+1, 1) - timedelta(seconds=1)
                    
                    cursor.execute('''
                        SELECT timestamp, download_speed, upload_speed, ping, jitter 
                        FROM speed_measurements 
                        WHERE timestamp BETWEEN ? AND ?
                        ORDER BY timestamp
                    ''', (start_date.strftime('%Y-%m-%d %H:%M:%S'), 
                          end_date.strftime('%Y-%m-%d %H:%M:%S')))
                    
                    # Явно удаляем временные переменные
                    del month, year
                else:
                    start_date = datetime.now() - timedelta(days=30)
                    end_date = datetime.now()
                    cursor.execute('''
                        SELECT timestamp, download_speed, upload_speed, ping, jitter 
                        FROM speed_measurements 
                        WHERE timestamp BETWEEN ? AND ?
                        ORDER BY timestamp
                    ''', (start_date.strftime('%Y-%m-%d %H:%M:%S'), 
                          end_date.strftime('%Y-%m-%d %H:%M:%S')))
                    
            else:  # Все время
                start_date = datetime.now() - timedelta(days=36500)  # 100 лет
                end_date = datetime.now()
                cursor.execute('''
                    SELECT timestamp, download_speed, upload_speed, ping, jitter 
                    FROM speed_measurements 
                    WHERE timestamp BETWEEN ? AND ?
                    ORDER BY timestamp
                ''', (start_date.strftime('%Y-%m-%d %H:%M:%S'), 
                      end_date.strftime('%Y-%m-%d %H:%M:%S')))
            
            # Получаем данные
            data = cursor.fetchall()
            conn.close()
            
            if not data:
                ax = self.fig.add_subplot(111)
                ax.text(0.5, 0.5, 'Нет данных за выбранный период', 
                       ha='center', va='center', transform=ax.transAxes)
                self.canvas.draw()
                
                # Принудительный сбор мусора в конце
                gc.collect()
                self._updating_graph = False
                return
          
            # Подготавливаем данные (для Дня они уже в агрегированном виде)
            if period == "День":
                # Для дня данные уже сгруппированы по часам
                timestamps = [datetime.strptime(row[0], '%Y-%m-%d %H:00:00') for row in data]
                download_speeds = [row[1] for row in data]
                upload_speeds = [row[2] for row in data]
                pings = [row[3] for row in data]
                jitters = [row[4] for row in data]
            else:
                # Для остальных периодов - как обычно
                timestamps = [row[0] for row in data]
                download_speeds = [row[1] for row in data]
                upload_speeds = [row[2] for row in data]
                pings = [row[3] for row in data]
                jitters = [row[4] for row in data]
                
                # Преобразуем строки времени в datetime
                if isinstance(timestamps[0], str):
                    try:
                        timestamps = [datetime.strptime(ts, '%Y-%m-%d %H:%M:%S.%f') for ts in timestamps]
                    except ValueError:
                        timestamps = [datetime.strptime(ts, '%Y-%m-%d %H:%M:%S') for ts in timestamps]
            
            # Фильтруем N/A значения (None, 0 или пустые) для всех метрик
            download_valid = [(t, v) for t, v in zip(timestamps, download_speeds) if v and v > 0]
            upload_valid = [(t, v) for t, v in zip(timestamps, upload_speeds) if v and v > 0]
            ping_valid_all = [(t, v) for t, v in zip(timestamps, pings) if v and v > 0]
            jitter_valid_all = [(t, v) for t, v in zip(timestamps, jitters) if v and v >= 0]
            
            # Вычисляем средние для всех метрик (используем все валидные данные)
            avg_download = sum(v for _, v in download_valid) / len(download_valid) if download_valid else 0
            avg_upload = sum(v for _, v in upload_valid) / len(upload_valid) if upload_valid else 0
            avg_ping = sum(v for _, v in ping_valid_all) / len(ping_valid_all) if ping_valid_all else 0
            avg_jitter = sum(v for _, v in jitter_valid_all) / len(jitter_valid_all) if jitter_valid_all else 0
            
            # Фильтруем выбросы ТОЛЬКО для отображения на графиках пинга и джиттера
            if ping_valid_all:
                ping_valid = [(t, v) for t, v in ping_valid_all if v <= avg_ping * 3]
            else:
                ping_valid = []
            
            if jitter_valid_all:
                jitter_valid = [(t, v) for t, v in jitter_valid_all if v <= avg_jitter * 3]
            else:
                jitter_valid = []
            
            # Разделяем обратно на timestamps и values
            if download_valid:
                download_ts, download_vals = zip(*download_valid)
            else:
                download_ts, download_vals = [], []
            
            if upload_valid:
                upload_ts, upload_vals = zip(*upload_valid)
            else:
                upload_ts, upload_vals = [], []
            
            if ping_valid:
                ping_ts, ping_vals = zip(*ping_valid)
            else:
                ping_ts, ping_vals = [], []
            
            if jitter_valid:
                jitter_ts, jitter_vals = zip(*jitter_valid)
            else:
                jitter_ts, jitter_vals = [], []
           
            # Очищаем фигуру перед созданием новых графиков
            self.fig.clear()
            
            # Создаем графики
            ax1 = self.fig.add_subplot(211)
            ax2 = self.fig.add_subplot(212)
            
            # Настраиваем шрифты для подписей осей 
            label_fontsize = 8
            title_fontsize = 11
            
            # График скорости
            if download_vals:
                ax1.plot(download_ts, download_vals, 'b-', label='Загрузка', linewidth=2)
            if upload_vals:
                ax1.plot(upload_ts, upload_vals, 'r-', label='Отдача', linewidth=2)

            # Добавляем средние значения
            if avg_download > 0:
                ax1.axhline(y=avg_download, color='b', linestyle='--', linewidth=1, alpha=0.6)
            if avg_upload > 0:
                ax1.axhline(y=avg_upload, color='r', linestyle='--', linewidth=1, alpha=0.6)

            # Добавляем линию заявленной скорости (зеленая штрих-пунктирная)
            planned = self.planned_speed_var.get() if hasattr(self, 'planned_speed_var') else 0
            if planned > 0:
                ax1.axhline(y=planned, color='green', linestyle='-.', linewidth=2, alpha=0.8, label=f'Тариф ({planned} Mbps)')

            ax1.set_title('Скорость интернета', fontsize=title_fontsize)
            ax1.set_ylabel('Скорость (Mbps)', fontsize=label_fontsize)
            ax1.legend(fontsize=label_fontsize, loc='lower right')
            ax1.grid(True, alpha=0.3)
            ax1.tick_params(axis='both', labelsize=label_fontsize)
            
            # Форматируем ось X в зависимости от выбранного периода
            import matplotlib.dates as mdates
            
            if period == "День":
                ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
                ax1.tick_params(axis='x', rotation=45)
            else:
                # Для остальных периодов показываем дату
                ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%y'))
                if period == "Неделя":
                    ax1.xaxis.set_major_locator(mdates.DayLocator(interval=1))
                elif period == "Месяц":
                    ax1.xaxis.set_major_locator(mdates.DayLocator(interval=3))
                ax1.tick_params(axis='x', rotation=45)
            
            # График пинга и джиттера
            if ping_vals:
                ax2.plot(ping_ts, ping_vals, color='purple', linestyle='-', label='Пинг', linewidth=2)
            if jitter_vals:
                ax2.plot(jitter_ts, jitter_vals, color='orange', label='Джиттер', linewidth=2)
            
            # Добавляем средние значения
            if avg_ping > 0:
                ax2.axhline(y=avg_ping, color='purple', linestyle='--', linewidth=1, alpha=0.6)
            if avg_jitter >= 0:
                ax2.axhline(y=avg_jitter, color='orange', linestyle='--', linewidth=1, alpha=0.6)

            # Добавляем пороговые линии
            ax2.axhline(y=60, color='purple', linestyle='-.', linewidth=1.5, alpha=0.5, label='Порог пинга (60 мс)')
            ax2.axhline(y=15, color='orange', linestyle='-.', linewidth=1.5, alpha=0.5, label='Порог джиттера (15 мс)')

            ax2.set_title('Пинг и Джиттер', fontsize=title_fontsize)
            ax2.set_xlabel('', fontsize=label_fontsize)
            ax2.set_ylabel('Значение (ms)', fontsize=label_fontsize)
            ax2.legend(fontsize=label_fontsize, loc='upper right')
            ax2.grid(True, alpha=0.3)
            ax2.tick_params(axis='both', labelsize=label_fontsize)
            
            # Форматируем ось X для второго графика
            if period == "День":
                ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                ax2.xaxis.set_major_locator(mdates.HourLocator(interval=2))
                ax2.tick_params(axis='x', rotation=45)
            else:
                ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%y'))
                if period == "Неделя":
                    ax2.xaxis.set_major_locator(mdates.DayLocator(interval=1))
                elif period == "Месяц":
                    ax2.xaxis.set_major_locator(mdates.DayLocator(interval=3))
                ax2.tick_params(axis='x', rotation=45)
            
            # Автоматическое форматирование дат
            self.fig.autofmt_xdate()
            
            # Настраиваем layout
            self.fig.tight_layout()
            
            # Обновляем canvas
            self.canvas.draw()
            
            self.status_var.set(f"График обновлен. Показано точек: {len(data)}")
            
            # Явно удаляем большие списки данных
            del timestamps, download_speeds, upload_speeds, pings, jitters
            del download_valid, upload_valid, ping_valid_all, jitter_valid_all
            del download_ts, download_vals, upload_ts, upload_vals
            del ping_ts, ping_vals, jitter_ts, jitter_vals
            
            # Финальный сбор мусора
            gc.collect()
            gc.collect()
            
        except Exception as e:
            self.logger.error(f"Ошибка обновления графика: {e}")
            self.status_var.set(f"Ошибка обновления графика: {e}")
        finally:
            self._updating_graph = False
# endregion

    def export_graph(self):
        """Экспорт графика в PNG"""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
                initialfile=f"internet_speed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            
            if filename:
                self.fig.savefig(filename, dpi=300, bbox_inches='tight')
                self.status_var.set(f"График экспортирован: {filename}")
                self.logger.info(f"График экспортирован в {filename}")
                messagebox.showinfo("Успех", f"График сохранен в файл:\n{filename}")
                
        except Exception as e:
            self.logger.error(f"Ошибка экспорта графика: {e}")
            messagebox.showerror("Ошибка", f"Не удалось экспортировать график: {e}")

# region ### Можно осторожно менять
    def export_log(self):
        """Экспорт журнала в CSV (сырые данные из БД)"""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=f"internet_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            
            if filename:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('SELECT id, timestamp, download_speed, upload_speed, ping, jitter, server FROM speed_measurements ORDER BY timestamp DESC')
                rows = cursor.fetchall()
                conn.close()
                
                import csv
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['ID', 'Timestamp', 'Download (Mbps)', 'Upload (Mbps)', 'Ping (ms)', 'Jitter (ms)', 'Server'])
                    
                    for row in rows:
                        # Форматируем дату из "YYYY-MM-DD HH:MM:SS.ffffff" в "dd-mm-yyyy HH:MM:SS"
                        timestamp = row[1]
                        if timestamp and isinstance(timestamp, str):
                            try:
                                dt = datetime.strptime(timestamp.split('.')[0], '%Y-%m-%d %H:%M:%S')
                                formatted_timestamp = dt.strftime('%d-%m-%Y %H:%M:%S')
                            except:
                                formatted_timestamp = timestamp
                        else:
                            formatted_timestamp = str(timestamp) if timestamp else ""
                        
                        # Форматируем значения
                        download = f"{row[2]:.2f}" if row[2] is not None else ""
                        upload = f"{row[3]:.2f}" if row[3] is not None else ""
                        ping = f"{row[4]:.1f}" if row[4] is not None else ""
                        jitter = f"{row[5]:.1f}" if row[5] is not None else ""
                        server = row[6] or ""
                        
                        formatted_row = (
                            row[0],
                            formatted_timestamp,
                            download,
                            upload,
                            ping,
                            jitter,
                            server
                        )
                        
                        writer.writerow(formatted_row)
                
                self.status_var.set(f"Журнал экспортирован: {filename}")
                self.logger.info(f"Журнал экспортирован в {filename}")
                messagebox.showinfo("Успех", f"Журнал сохранен в файл:\n{filename}")
                
        except Exception as e:
            self.logger.error(f"Ошибка экспорта журнала: {e}")
            messagebox.showerror("Ошибка", f"Не удалось экспортировать журнал: {e}")
# endregion

    def clear_log(self):
        """Очистка журнала"""
        if messagebox.askyesno("Подтверждение", 
                              "Вы уверены, что хотите очистить весь журнал?\nЭта операция необратима."):
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM speed_measurements')
                conn.commit()
                conn.close()
                
                self.update_log()
                self.update_graph()
                
                self.status_var.set("Журнал очищен")
                self.logger.info("Журнал очищен")
                messagebox.showinfo("Успех", "Журнал успешно очищен")
                
            except Exception as e:
                self.logger.error(f"Ошибка очистки журнала: {e}")
                messagebox.showerror("Ошибка", f"Не удалось очистить журнал: {e}")


    def show_window(self):
        """Показать окно из трея"""
        self.root.deiconify()
        self.root.attributes('-topmost', True)
        self.root.after_idle(lambda: self.root.attributes('-topmost', False))
        self.logger.info("Приложение открыто")
        self.status_var.set("Ожидание команды")

    def minimize_to_tray(self):
        """Сворачивание в системный трей"""
        # Просто сворачиваем окно, независимо от настройки
        # Настройка влияет только на автоматическое сворачивание при запуске
        self.root.withdraw()
        self.root.attributes('-alpha', 1.0)
        self.root.update_idletasks()
        self.status_var.set("Ожидание команды")
        self.logger.info("Приложение свернуто в трей")

    def handle_window_close(self):
        """Обработка закрытия окна пользователем (крестик)"""
        # Всегда сворачиваем в трей при нажатии на крестик
        self.minimize_to_tray()
        self.update_tray_menu()          
    ###
    def quit_app(self):
        """Завершение работы приложения"""
        self.logger.info("Завершение работы приложения...")
        self.running = False
        
        # Закрываем консоль
        self.close_console()
        
        # Останавливаем мониторинг если он запущен
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)
        
        # Закрываем иконку в трее (с проверкой)
        try:
            if hasattr(self, 'tray_icon'):
                # Даем время иконке запуститься
                time.sleep(0.5)
                self.tray_icon.stop()
        except Exception as e:
            self.logger.error(f"Ошибка закрытия иконки трея: {e}")
        
        # Закрываем все окна tkinter
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
        
        # Принудительно завершаем процесс
        self.logger.info("Приложение завершено")
        os._exit(0)

    def restart_app(self):
        """Перезапуск приложения"""
        self.logger.info("Перезапуск программы...")
        
        # Сохраняем настройки перед перезапуском
        self.save_settings(restart=False, show_message=False)
        
        # Небольшая задержка для завершения операций
        time.sleep(1)
        
        if getattr(sys, 'frozen', False):
            # EXE режим - запускаем exe
            executable = sys.executable
            args = [executable]
            self.logger.info(f"Запуск EXE: {executable}")
        else:
            # Режим разработки - запускаем через python
            python = sys.executable
            script_path = os.path.abspath(__file__)
            args = [python, script_path]
            self.logger.info(f"Запуск скрипта: {python} {script_path}")
        
        self.logger.info(f"Команда: {' '.join(args)}")
        
        # Запускаем новый процесс
        try:
            subprocess.Popen(args, shell=True)
            self.logger.info("Новый процесс запущен")
        except Exception as e:
            self.logger.error(f"Ошибка запуска нового процесса: {e}")
            return
        
        # Завершаем текущий процесс
        self.logger.info("Завершение текущего процесса")
        self.root.quit()
        self.root.destroy()
        os._exit(0)

# region PROTECTED - НЕ ИЗМЕНЯТЬ!!!
def check_if_already_running():
    """Проверка через файловую блокировку - не запущено ли уже приложение"""
    global _lock_file
    
    print(f"[DEBUG] Текущий PID: {os.getpid()}")
    
    # Проверяем существующий файл лока
    if os.path.exists(_lock_file_path):
        try:
            with open(_lock_file_path, 'r') as f:
                old_pid = f.read().strip()
            print(f"[DEBUG] Найден файл лока с PID: {old_pid}")
            
            # Проверяем, существует ли процесс с этим PID
            try:
                os.kill(int(old_pid), 0)  # Сигнал 0 только проверяет существование
                print(f"[DEBUG] Процесс {old_pid} существует")
            except OSError:
                print(f"[DEBUG] Процесс {old_pid} не существует, удаляем старый лок")
                os.remove(_lock_file_path)
        except:
            pass
    
    # Даем время предыдущему экземпляру полностью завершиться
    time.sleep(1)
    
    try:
        if sys.platform == 'win32':
            import msvcrt
            print(f"[DEBUG] Попытка захватить файловый лок: {_lock_file_path}")
            
            # Проверяем время создания файла лока
            if os.path.exists(_lock_file_path):
                file_time = os.path.getmtime(_lock_file_path)
                if time.time() - file_time < 2:  # Если файл создан менее 2 секунд назад
                    print(f"[DEBUG] Файл лока слишком свежий ({(time.time()-file_time):.1f} сек), ждем...")
                    time.sleep(1)
            
            # Открываем файл для добавления/чтения
            lock_f = open(_lock_file_path, 'a+')
            
            try:
                # Пытаемся захватить эксклюзивный лок на первый байт
                msvcrt.locking(lock_f.fileno(), msvcrt.LK_NBLCK, 1)
                # Успешно захватили - других экземпляров нет
                print(f"[DEBUG] Лок захвачен успешно, процесс может продолжать")
                _lock_file = lock_f  # Сохраняем файл - держим блокировку
                return False  # Возвращаем False = нет других запущенных экземпляров
            except (OSError, IOError, BlockingIOError) as e:
                # Не удалось захватить лок - другой процесс его удерживает
                print(f"[DEBUG] Лок уже занят другим процессом: {e}")
                lock_f.close()
                return True  # Возвращаем True = приложение уже запущено
        else:
            # Unix
            import fcntl
            print(f"[DEBUG] Попытка захватить файловый лок (Unix): {_lock_file_path}")
            
            lock_f = open(_lock_file_path, 'w')
            try:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                print(f"[DEBUG] Лок захвачен успешно, процесс может продолжать")
                _lock_file = lock_f
                return False
            except IOError as e:
                print(f"[DEBUG] Лок уже занят другим процессом: {e}")
                lock_f.close()
                return True
    
    except Exception as e:
        print(f"[DEBUG] Ошибка при проверке лока: {e}")
        # Если ошибка - даем разрешение на запуск (лучше двойной запуск, чем запирание)
        return False
# endregion

def parse_arguments():
    """Парсинг аргументов командной строки"""
    import argparse
    parser = argparse.ArgumentParser(description='SpeedWatch - Мониторинг скорости интернета')
    parser.add_argument('--test-mode', action='store_true', 
                       help='Запуск в тестовом режиме (без GUI, вывод в консоль)')
    return parser.parse_args()

# Парсим аргументы при запуске
ARGS = parse_arguments()
TEST_MODE = ARGS.test_mode

def main():
    global _lock_file

    # Диагностика автозапуска
    safe_print(f"[DEBUG] Запуск из: {os.path.abspath(sys.argv[0])}")
    safe_print(f"[DEBUG] Рабочая директория: {os.getcwd()}")
    safe_print(f"[DEBUG] Python: {sys.executable}")

    # Тестовый режим - быстрая проверка работоспособности
    if TEST_MODE:
        safe_print("\n" + "="*50)
        safe_print("ТЕСТОВЫЙ РЕЖИМ")
        safe_print("="*50)
        
        # Проверка 1: Создание директории данных
        if getattr(sys, 'frozen', False):
            test_dir = os.path.join(os.environ.get('APPDATA', ''), 'SpeedWatch', 'data')
        else:
            test_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
        
        safe_print(f"Директория данных: {test_dir}")
        os.makedirs(test_dir, exist_ok=True)
        safe_print(f"✓ Директория данных создана/существует")
        
        # Проверка 2: Подключение к БД
        try:
            import sqlite3
            test_db = os.path.join(test_dir, "test.db")
            conn = sqlite3.connect(test_db)
            conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
            conn.close()
            os.remove(test_db)
            safe_print(f"✓ SQLite работает")
        except Exception as e:
            safe_print(f"✗ Ошибка SQLite: {e}")
        
        # Проверка 3: Импорт всех библиотек
        libs = ['tkinter', 'matplotlib', 'PIL', 'pystray', 'psutil', 'requests']
        for lib in libs:
            try:
                __import__(lib)
                safe_print(f"✓ {lib} импортирован")
            except Exception as e:
                safe_print(f"✗ {lib} не импортирован: {e}")
        
        safe_print("\n" + "="*50)
        safe_print("ТЕСТ ЗАВЕРШЕН")
        safe_print("="*50)
        return  # Выход после теста

    try:
        # Проверка через файловую блокировку
        if check_if_already_running():
            root = tk.Tk()
            root.withdraw()  # Скрываем основное окно
            messagebox.showwarning("Внимание", "Приложение уже запущено!")
            root.destroy()
            return
        
        root = tk.Tk()
        app = InternetSpeedMonitor(root)
        root.mainloop()
        
    except Exception as e:
        # Записываем ошибку в файл
        error_msg = f"Критическая ошибка: {e}\n"
        error_msg += "".join(traceback.format_exc())
        
        with open("crash_error.log", "w", encoding="utf-8") as f:
            f.write(error_msg)
        
        # Пытаемся показать сообщение пользователю
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Критическая ошибка", 
                                f"Программа аварийно завершилась.\n\n"
                                f"Ошибка: {e}\n\n"
                                f"Подробности в файле crash_error.log")
            root.destroy()
        except:
            safe_print(error_msg)
            input("Нажмите Enter для выхода...")

    finally:
        # Гарантированное освобождение лока при выходе
        if _lock_file:
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    try:
                        msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass  # Иногда уже разблокирован
                else:
                    import fcntl
                    try:
                        fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                
                _lock_file.close()
                _lock_file = None
                safe_print("[DEBUG] Лок освобожден при выходе")
            except Exception as e:
                safe_print(f"[DEBUG] Ошибка освобождения лока: {e}")
        
        # Гарантированно удаляем файл лока
        try:
            if os.path.exists(_lock_file_path):
                os.remove(_lock_file_path)
                safe_print(f"[DEBUG] Файл лока удален: {_lock_file_path}")
        except Exception as e:
            safe_print(f"[DEBUG] Ошибка удаления файла лока: {e}")


if __name__ == "__main__":
    main()