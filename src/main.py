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
__version__ = "1.0.0"

# Определяем корневую директорию проекта
if getattr(sys, 'frozen', False):
    # Запуск из exe
    base_dir = os.path.dirname(sys.executable)
else:
    # Запуск из скрипта - поднимаемся на уровень выше src
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Меняем рабочую директорию
os.chdir(base_dir)
print(f"[AUTOSTART] Установлена рабочая директория: {os.getcwd()}")

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
        else:
            # Запуск из скрипта - поднимаемся на уровень выше src
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

        # Проверяем целостность БД при запуске
        self.check_database_integrity()

        # Управление консолью
        self.console_visible = False  # Начинаем со скрытой консоли
        self.setup_console()
        ###
        # Создание интерфейса
        self.create_widgets()
        
        # Устанавливаем начальные даты в фильтре журнала
        first_date = self.get_first_measurement_date()
        self.date_from_entry.set_date(first_date)
        self.date_to_entry.set_date(datetime.now().date())
        
        # Устанавливаем период "Все время" на вкладке графиков
        self.period_var.set("Все время")
        
        # Устанавливаем начальный статус
        self.status_var.set("Ожидание команды")
        
        # Загружаем время последнего измерения
        last_time = self.get_last_measurement_time()
        self.last_check_var.set(last_time)

        # Обновляем график с периодом "Все время"
        self.root.after(500, self.update_graph)  # Небольшая задержка для полной загрузки интерфейса     
          
        
        # Загрузка настроек
        self.is_first_load = True  # Флаг первого запуска
        self.load_settings()

        # Загружаем последние значения измерений
        self.load_last_measurement()

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
        """Настройка логирования"""
        log_path = os.path.join(self.base_dir, "data", "speed_monitor.log")
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler()
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
    ##
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
            cursor.execute('''
                SELECT download_speed, upload_speed, ping, jitter 
                FROM speed_measurements 
                ORDER BY timestamp DESC LIMIT 1
            ''')
            result = cursor.fetchone()
            conn.close()
            
            if result:
                download, upload, ping, jitter = result
                self.download_var.set(f"{download:.2f} Mbps")
                self.upload_var.set(f"{upload:.2f} Mbps")
                self.ping_var.set(f"{ping:.2f} ms")
                self.jitter_var.set(f"{jitter:.2f} ms")
                self.logger.info(f"Загружены последние значения: Download={download:.2f} Mbps")
            else:
                self.logger.info("Нет сохраненных измерений")
                
        except Exception as e:
            self.logger.error(f"Ошибка загрузки последнего измерения: {e}")

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
                    SUM(CASE WHEN jitter > 15 THEN 1 ELSE 0 END) as bad_count
                FROM speed_measurements 
                WHERE timestamp >= ?
            ''', (week_ago,))
            
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
            
            # Проверяем условия
            issues = []
            
            # Условие 1: Скорость скачивания ниже на 25%+
            if prev_avg_download > 0 and avg_download < prev_avg_download * 0.75:
                drop_percent = (1 - avg_download / prev_avg_download) * 100
                issues.append(f"• Скорость скачивания упала на {drop_percent:.1f}% (с {prev_avg_download:.1f} до {avg_download:.1f} Mbps)")
            
            # Условие 2: Пинг выше на 100%+
            if prev_avg_ping > 0 and avg_ping > prev_avg_ping * 2:
                increase_percent = (avg_ping / prev_avg_ping - 1) * 100
                issues.append(f"• Пинг вырос на {increase_percent:.1f}% (с {prev_avg_ping:.1f} до {avg_ping:.1f} ms)")
            
            # Условие 3: Джиттер часто превышает норму (более 30% измерений)
            if total_jitter > 0 and bad_jitter > 0 and (bad_jitter / total_jitter) > 0.3:
                issues.append(f"• Джиттер часто превышает норму: в {bad_jitter} из {total_jitter} измерений (среднее {avg_jitter:.1f} ms)")
            elif avg_jitter > 15:  # Если средний джиттер высокий, но нечастый
                issues.append(f"• Средний джиттер превышает норму: {avg_jitter:.1f} ms")
            
            # Если есть проблемы, показываем окно
            if issues:
                self.show_quality_warning(issues, avg_download, avg_upload, avg_ping, avg_jitter, count)
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа соединения: {e}")
        finally:
            # Гарантированно закрываем соединение, если оно еще открыто
            if conn:
                conn.close()

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

    def setup_console(self):
        """Настройка консоли Windows"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Получаем хендл консоли
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            self.hwnd = kernel32.GetConsoleWindow()
            
            if self.hwnd:
                # Убираем ТОЛЬКО кнопку закрытия (крестик), оставляем свернуть и развернуть
                user32 = ctypes.WinDLL('user32', use_last_error=True)
                GWL_STYLE = -16
                
                # Получаем текущие стили
                style = user32.GetWindowLongW(self.hwnd, GWL_STYLE)
                
                # Убираем только системное меню (крестик), оставляем остальные кнопки
                style = style & ~0x00080000  # Убираем WS_SYSMENU
                style = style | 0x00020000   # Добавляем WS_MINIMIZEBOX (если не было)
                style = style | 0x00010000   # Добавляем WS_MAXIMIZEBOX (если не было)
                
                user32.SetWindowLongW(self.hwnd, GWL_STYLE, style)
                
                # Обновляем окно
                user32.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0, 
                                  0x0001 | 0x0002 | 0x0020)  # SWP_NOSIZE | SWP_NOMOVE | SWP_FRAMECHANGED
                
                self.logger.info("Кнопка закрытия консоли отключена, кнопки свернуть/развернуть активны")
        except Exception as e:
            self.logger.error(f"Ошибка настройки консоли: {e}")


    def hide_console_on_start(self):
        """Скрыть консоль при старте"""
        try:
            import ctypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            
            if hasattr(self, 'hwnd') and self.hwnd:
                user32.ShowWindow(self.hwnd, 0)  # SW_HIDE = 0
                self.console_visible = False
        except Exception as e:
            self.logger.error(f"Ошибка скрытия консоли при старте: {e}")

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

    def toggle_console(self, icon, item):
        """Переключение видимости консоли"""
        try:
            import ctypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            
            if hasattr(self, 'hwnd') and self.hwnd:
                if self.console_visible:
                    # Скрыть консоль
                    user32.ShowWindow(self.hwnd, 0)  # SW_HIDE = 0
                    self.console_visible = False
                else:
                    # Показать консоль (SW_RESTORE = 9)
                    user32.ShowWindow(self.hwnd, 9)  # SW_RESTORE - восстанавливает окно
                    self.console_visible = True
                
                # Обновляем меню с новым текстом
                self.update_tray_menu()
                    
        except Exception as e:
            self.logger.error(f"Ошибка переключения консоли: {e}")
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
        
      
        # Заполняем вкладку мониторинга
        self.setup_monitor_tab()
        
        # Заполняем вкладку графиков
        self.setup_graph_tab()
        
        # Заполняем вкладку журнала
        self.setup_log_tab()
        
        # Заполняем вкладку настроек
        self.setup_settings_tab()

    def setup_monitor_tab(self):
        """Настройка вкладки мониторинга"""
        # Фрейм с текущими показателями
        current_frame = ttk.LabelFrame(self.monitor_frame, text="Параметры соединения", padding=self.scale_value(15))
        current_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))
        
        # Скорость загрузки
        ttk.Label(current_frame, text="Скорость загрузки:", font=self.scale_font('Arial', 12)).grid(row=0, column=0, sticky='w', pady=5)
        self.download_var = tk.StringVar(value="0 Mbps")
        ttk.Label(current_frame, textvariable=self.download_var, font=self.scale_font('Arial', 16) + ('bold',)).grid(row=0, column=1, padx=10)
        
        # Скорость отдачи
        ttk.Label(current_frame, text="Скорость отдачи:", font=self.scale_font('Arial', 12)).grid(row=1, column=0, sticky='w', pady=5)
        self.upload_var = tk.StringVar(value="0 Mbps")
        ttk.Label(current_frame, textvariable=self.upload_var, font=self.scale_font('Arial', 16) + ('bold',)).grid(row=1, column=1, padx=10)
        
        # Пинг
        ttk.Label(current_frame, text="Пинг:", font=self.scale_font('Arial', 12)).grid(row=2, column=0, sticky='w', pady=5)
        self.ping_var = tk.StringVar(value="0 ms")
        ttk.Label(current_frame, textvariable=self.ping_var, font=self.scale_font('Arial', 16) + ('bold',)).grid(row=2, column=1, padx=10)
        
        # Jitter
        ttk.Label(current_frame, text="Джиттер:", font=self.scale_font('Arial', 12)).grid(row=3, column=0, sticky='w', pady=5)
        self.jitter_var = tk.StringVar(value="0 ms")
        ttk.Label(current_frame, textvariable=self.jitter_var, font=self.scale_font('Arial', 16) + ('bold',)).grid(row=3, column=1, padx=10)
        
        # Время последнего измерения
        ttk.Label(current_frame, text="Последнее измерение:", font=self.scale_font('Arial', 12)).grid(row=4, column=0, sticky='w', pady=5)
        self.last_check_var = tk.StringVar(value="Никогда")
        ttk.Label(current_frame, textvariable=self.last_check_var, font=self.scale_font('Arial', 11)).grid(row=4, column=1, padx=10)
        
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
        self.next_test_var = tk.StringVar(value="--:--:--")
        ttk.Label(control_frame, textvariable=self.next_test_var, font=self.scale_font('Arial', 11) + ('bold',)).pack(side='left')
        
        # Статус бар ПОД кнопками управления
        self.status_var = tk.StringVar()
        self.status_var.set("Готов к работе")
        status_bar = ttk.Label(self.monitor_frame, textvariable=self.status_var, relief=tk.SUNKEN, padding=5)
        status_bar.pack(fill='x', padx=self.scale_value(15), pady=(0, self.scale_value(15)))


    def setup_graph_tab(self):
        """Настройка вкладки с графиками"""
        # Панель управления графиками
        control_frame = ttk.Frame(self.graph_frame)
        control_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))
        
        # Выбор периода
        ttk.Label(control_frame, text="Период:").pack(side='left')
        
        self.period_var = tk.StringVar(value="1 день")
        periods = ["1 день", "7 дней", "30 дней", "Все время"]
        self.period_combo = ttk.Combobox(control_frame, textvariable=self.period_var, values=periods, state='readonly', width=10)
        self.period_combo.pack(side='left', padx=5)
        
        # Кнопка обновления
        ttk.Button(control_frame, text="Обновить график", command=self.update_graph).pack(side='left', padx=self.scale_value(10))
        
        # Кнопка экспорта
        ttk.Button(control_frame, text="Экспорт PNG", command=self.export_graph).pack(side='left')
        
        # Область для графиков
        self.graph_canvas_frame = ttk.Frame(self.graph_frame)
        self.graph_canvas_frame.pack(fill='both', expand=True, padx=self.scale_value(15), pady=self.scale_value(15))
        
        # Создаем фигуру для matplotlib
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_canvas_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)


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


    def setup_settings_tab(self):
        """Настройка вкладки настроек"""
        settings_frame = ttk.LabelFrame(self.settings_frame, text="Настройки мониторинга", padding=20)
        settings_frame.pack(fill='both', expand=True, padx=self.scale_value(15), pady=self.scale_value(15))
        
        # Интервал проверки
        ttk.Label(settings_frame, text="Интервал проверки (минут):").grid(row=0, column=0, sticky='w', pady=10)
        self.interval_var = tk.IntVar(value=60)
        ttk.Spinbox(settings_frame, from_=1, to=1440, textvariable=self.interval_var, width=10).grid(row=0, column=1, padx=10)
        
        # Автозапуск
        self.auto_start_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Автозапуск при старте Windows", 
                       variable=self.auto_start_var).grid(row=1, column=0, columnspan=2, sticky='w', pady=10)
        
        # Минимализация в трей
        self.minimize_to_tray_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Сворачивать в системный трей", 
                       variable=self.minimize_to_tray_var).grid(row=2, column=0, columnspan=2, sticky='w', pady=10)
        
        # Кнопки сохранения настроек
        ttk.Button(settings_frame, text="Сохранить настройки", 
                  command=self.save_settings).grid(row=3, column=0, pady=20)
        
        # Информация о программе
        info_frame = ttk.LabelFrame(self.settings_frame, text="Информация", padding=20)
        info_frame.pack(fill='x', padx=self.scale_value(15), pady=self.scale_value(10))
        
        # Название программы с версией
        version_text = f"SpeedWatch v{__version__}"
        ttk.Label(info_frame, text=version_text, font=self.scale_font('Arial', 14) + ('bold',)).pack(pady=(0, 5))
        
        # Описание
        ttk.Label(info_frame, text="Мониторинг скорости интернет-соединения", 
                 font=self.scale_font('Arial', 10)).pack(pady=(0, 5))
        
        # Год
        current_year = datetime.now().year
        ttk.Label(info_frame, text=f"© {current_year}", 
                 font=self.scale_font('Arial', 9)).pack()


    def create_tray_icon(self):
        """Создание иконки в системном трее"""
        try:
            ###
            # Загружаем иконку из файла
            try:
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

    ###
    def save_settings(self, restart=True, show_message=True):
        """Сохранение настроек в БД"""
        # Защита от повторного вызова
        if hasattr(self, '_saving_settings') and self._saving_settings:
            return
        self._saving_settings = True
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Сохраняем интервал
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('interval', str(self.interval_var.get())))
            
            # Сохраняем автозапуск
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('auto_start', '1' if self.auto_start_var.get() else '0'))
            
            # Сохраняем настройку трея
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         ('minimize_to_tray', '1' if self.minimize_to_tray_var.get() else '0'))
            
            conn.commit()
            conn.close()
           
            # Обновляем автозапуск в реестре
            self.update_autostart()
            
            if restart and show_message:
                messagebox.showinfo(
                    "Настройки сохранены", 
                    "Настройки успешно сохранены!\n\n"
                    "Программа будет перезапущена для применения изменений."
                )
                self.logger.info("Настройки сохранены, выполняю перезапуск")
                
                # Откладываем перезапуск, чтобы окно сообщения закрылось
                self.root.after(100, self.restart_app)
            elif show_message:
                messagebox.showinfo("Настройки сохранены", "Настройки успешно сохранены!")
                self.logger.info("Настройки сохранены")
            
        except Error as e:
            self.logger.error(f"Ошибка сохранения настроек: {e}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {e}")
        finally:
            self._saving_settings = False
            
    def reset_date_filter(self):
        """Сброс фильтра по дате"""
        first_date = self.get_first_measurement_date()
        self.date_from_entry.set_date(first_date)
        self.date_to_entry.set_date(datetime.now().date())
        self.update_log()       
    ###    

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
            
            # Если pythonw.exe не найден, используем python.exe
            if not os.path.exists(pythonw_path):
                pythonw_path = sys.executable
            
            # ПРАВИЛЬНЫЙ путь к скрипту (src/main.py)
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "main.py")
            
            # Проверяем существование файла
            if not os.path.exists(script_path):
                # Если не нашли, используем текущий файл
                script_path = os.path.abspath(__file__)
                self.logger.warning(f"Путь по умолчанию не найден, использую: {script_path}")
            
            if self.auto_start_var.get():
                # Формируем команду
                cmd = f'"{pythonw_path}" "{script_path}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                self.logger.info(f"Добавлено в автозапуск: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    self.logger.info("Удалено из автозапуска")
                except FileNotFoundError:
                    pass
            
            winreg.CloseKey(key)
                
        except Exception as e:
            self.logger.error(f"Ошибка обновления автозапуска: {e}")


    def run_speed_test(self):
        """Запуск теста скорости интернета"""
        if self.test_in_progress:
            self.logger.warning("Тест уже выполняется, пропускаем")
            return
            
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

    def stop_wait_animation(self):
        """Остановка анимации ожидания"""
        if self.wait_animation_job:
            self.root.after_cancel(self.wait_animation_job)
            self.wait_animation_job = None

    def stop_test_animation(self):
        """Остановка анимации теста"""
        if self.animation_job:
            self.root.after_cancel(self.animation_job)
            self.animation_job = None
        
        # Восстанавливаем статус
        if self.running:
            # Если мониторинг работает, запускаем анимацию ожидания
            self.start_wait_animation()
        else:
            self.status_var.set("Ожидание команды")
            if sys.stdout.isatty():
                print("\rОжидание команды" + " " * 20, flush=True)
        
        # Восстанавливаем статус
        if self.running:
            # Если мониторинг работает, запускаем анимацию ожидания
            self.start_wait_animation()
        else:
            self.status_var.set("Ожидание команды")

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
            
            # Запускаем анимацию в консоли, если она доступна
            if sys.stdout.isatty():  # Проверяем, что вывод идет в консоль
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

            with open(stdout_temp.name, 'w', encoding='utf-8') as out_f, \
                 open(stderr_temp.name, 'w', encoding='utf-8') as err_f:

                process = subprocess.Popen(
                    [sys.executable, cli_path],
                    stdout=out_f,
                    stderr=err_f,
                    text=True
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

            os.unlink(stdout_temp.name)
            os.unlink(stderr_temp.name)

            # Парсим название сервера
            server_name = "OpenSpeedTest"
            lines = stdout.split('\n')
            for line in lines:
                if "Лучший сервер найден:" in line:
                    try:
                        full = line.split("Лучший сервер найден:", 1)[1].strip()
                        clean = re.sub(r'\s*\(\d+\.?\d*\s*мс\s*\)\s*$', '', full)
                        if '(' in clean and clean.count('(') > 1:
                            parts = clean.split('(', 2)
                            server_name = parts[0].strip() + ' (' + parts[1].strip()
                        else:
                            server_name = clean
                        break
                    except:
                        pass

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
                raise Exception("Не удалось получить данные о скорости из вывода CLI")

            # Останавливаем консольную анимацию
            stop_animation.set()
            if console_animation_thread and console_animation_thread.is_alive():
                console_animation_thread.join(timeout=1)

            # Сохраняем результаты (даже частичные)
            self.save_test_results(download_speed, upload_speed, ping, jitter, server_name)

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
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Ошибка теста скорости: {error_msg}")
            self.root.after(0, lambda msg=error_msg: self._update_ui_with_error(msg))
            # Останавливаем анимацию
            stop_animation.set()
            if console_animation_thread and console_animation_thread.is_alive():
                console_animation_thread.join(timeout=1)
        finally:
            # Останавливаем анимацию в статус-баре
            self.root.after(0, self.stop_test_animation)
            self.test_in_progress = False
            self.root.after(0, lambda: self.test_button.config(state='normal'))


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


    def _update_ui_with_error(self, error_msg):
        """Обновление интерфейс при ошибке"""
        self.download_var.set("Ошибка")
        self.upload_var.set("Ошибка")
        self.ping_var.set("Ошибка")
        self.jitter_var.set("Ошибка")
        self.status_var.set(f"Ошибка: {error_msg}")
        self.test_button.config(state='normal')
        messagebox.showerror("Ошибка", f"Не удалось выполнить тест скорости: {error_msg}")

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

    def save_test_results(self, download, upload, ping, jitter, server):
        """Сохранение результатов теста в БД (поддерживает частичные данные)"""
        try:
            # Подготавливаем значения: None заменяем на NULL в БД
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO speed_measurements 
                (timestamp, download_speed, upload_speed, ping, jitter, server) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'), 
                download,  # может быть None
                upload,    # может быть None
                ping,      # может быть None
                jitter,    # может быть None
                server
            ))
            
            conn.commit()
            conn.close()
            
            # Обновляем время последнего измерения (если есть хоть какие-то данные)
            if download is not None or upload is not None or ping is not None or jitter is not None:
                current_time = datetime.now().strftime('%d.%m.%y %H:%M')
                self.last_check_var.set(current_time)

            # Обновляем отображение текущих значений (None заменяем на 0)
            self.download_var.set(f"{download:.2f} Mbps" if download is not None else "0 Mbps")
            self.upload_var.set(f"{upload:.2f} Mbps" if upload is not None else "0 Mbps")
            self.ping_var.set(f"{ping:.2f} ms" if ping is not None else "0 ms")
            self.jitter_var.set(f"{jitter:.2f} ms" if jitter is not None else "0 ms")
            
            # Обновляем журнал и графики
            self.root.after(0, self.update_log)
            self.root.after(0, self.update_graph)
            
            # Логируем что сохранили
            self.logger.info(f"Сохранены результаты: Download={download}, Upload={upload}, Ping={ping}, Jitter={jitter}")
            
        except Error as e:
            self.logger.error(f"Ошибка сохранения результатов: {e}")


    def start_monitoring(self):
        """Запуск периодического мониторинга"""
        if self.running:
            return

        # Выполняем анализ качества при старте мониторинга
        self.root.after(1000, self.analyze_connection_quality)

        self.running = True
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        
        # Сбрасываем таймер следующего теста
        self.next_test_time = datetime.now() + timedelta(minutes=self.interval_var.get())
        self.update_next_test_timer()
        
        # Запускаем поток мониторинга
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        self.status_var.set("Мониторинг запущен")
        self.logger.info("Мониторинг запущен")

    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.running = False
        
        # Останавливаем анимацию ожидания
        self.stop_wait_animation()
        
        # Очищаем консоль
        if sys.stdout.isatty():
            print("\r" + " " * 50 + "\r", end='', flush=True)
        
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.test_button.config(state='normal')
        self.status_var.set("Мониторинг остановлен")
        self.next_test_var.set("--:--:--")
        self.logger.info("Мониторинг остановлен")

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


    def update_next_test_timer(self):
        """Обновление таймера до следующего теста"""
        if not self.running:
            return
        
        # НЕ обновляем статус, если выполняется тест
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
                
                # Анимация в консоли (если она открыта)
                if sys.stdout.isatty():
                    dots = '.' * ((int(time.time()) % 3) + 1)
                    print(f"\rСледующий тест через: {timer_text}{dots}   ", end='', flush=True)
                
                # Запускаем анимацию ожидания в GUI, если она еще не запущена
                if not self.wait_animation_job:
                    self.start_wait_animation()
            else:
                # Время пришло, обновляем следующее время
                self.next_test_time = now + timedelta(minutes=self.interval_var.get())

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
                
                # Рассчитываем средние и пороги
                # Для скоростей: 75% от среднего = ниже на 25%
                # Для пинга: 125% от среднего = выше на 25%
                avg_download = sum(download_speeds) / len(download_speeds) if download_speeds else 0
                avg_upload = sum(upload_speeds) / len(upload_speeds) if upload_speeds else 0
                avg_ping = sum(pings) / len(pings) if pings else 0
                avg_jitter = sum(jitters) / len(jitters) if jitters else 0
                
                threshold_download = avg_download * 0.75
                threshold_upload = avg_upload * 0.75
                threshold_ping = avg_ping * 1.25
                
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
          

    def update_graph(self):
        """Обновление графиков"""
        try:
            self.fig.clear()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Определяем период
            period = self.period_var.get()
            if period == "1 день":
                days = 1
            elif period == "7 дней":
                days = 7
            elif period == "30 дней":
                days = 30
            else:
                days = 36500  # Все время (100 лет)
            
            cutoff_date = datetime.now() - timedelta(days=days)
            
            cursor.execute('''
                SELECT timestamp, download_speed, upload_speed, ping, jitter 
                FROM speed_measurements 
                WHERE timestamp >= ? 
                ORDER BY timestamp
            ''', (cutoff_date,))
            
            data = cursor.fetchall()
            conn.close()
            
            if not data:
                ax = self.fig.add_subplot(111)
                ax.text(0.5, 0.5, 'Нет данных за выбранный период', 
                       ha='center', va='center', transform=ax.transAxes)
                self.canvas.draw()
                return
          
            # Подготавливаем данные
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
            
            # Разделяем обратно на timestamps и values для отображения
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
            
            # Добавляем средние значения как пунктирные линии (без текста в легенде)
            if download_valid or upload_valid:
                time_range = [min(list(download_ts) + list(upload_ts)), 
                             max(list(download_ts) + list(upload_ts))]
                if avg_download > 0:
                    ax1.axhline(y=avg_download, color='b', linestyle='--', linewidth=1, alpha=0.6)
                if avg_upload > 0:
                    ax1.axhline(y=avg_upload, color='r', linestyle='--', linewidth=1, alpha=0.6)
            
            ax1.set_title('Скорость интернета', fontsize=title_fontsize)
            ax1.set_ylabel('Скорость (Mbps)', fontsize=label_fontsize)
            ax1.legend(fontsize=label_fontsize, loc='best')
            ax1.grid(True, alpha=0.3)
            ax1.tick_params(axis='both', labelsize=label_fontsize)
            
            # Форматируем ось X для дат в формате дд.мм.гг
            import matplotlib.dates as mdates
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%y'))
            
            # График пинга и джиттера
            if ping_vals:
                ax2.plot(ping_ts, ping_vals, 'g-', label='Пинг', linewidth=2)
            if jitter_vals:
                ax2.plot(jitter_ts, jitter_vals, color='orange', label='Джиттер', linewidth=2)
            
            # Добавляем средние значения как пунктирные линии (без текста в легенде)
            if ping_valid or jitter_valid:
                if avg_ping > 0:
                    ax2.axhline(y=avg_ping, color='g', linestyle='--', linewidth=1, alpha=0.6)
                if avg_jitter >= 0:
                    ax2.axhline(y=avg_jitter, color='orange', linestyle='--', linewidth=1, alpha=0.6)
            
            ax2.set_title('Пинг и Джиттер', fontsize=title_fontsize)
            ax2.set_xlabel('', fontsize=label_fontsize)
            ax2.set_ylabel('Значение (ms)', fontsize=label_fontsize)
            ax2.legend(fontsize=label_fontsize, loc='best')
            ax2.grid(True, alpha=0.3)
            ax2.tick_params(axis='both', labelsize=label_fontsize)
            
            # Форматируем ось X для дат в формате дд.мм.гг
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%y'))
            
            # Автоматическое форматирование дат
            self.fig.autofmt_xdate()
            
            # Настраиваем layout
            self.fig.tight_layout()
            
            # Обновляем canvas
            self.canvas.draw()
            
            self.status_var.set(f"График обновлен. Показано точек: {len(data)}")
            
        except Exception as e:
            self.logger.error(f"Ошибка обновления графика: {e}")
            self.status_var.set(f"Ошибка обновления графика: {e}")


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
        
        # Определяем путь к скрипту
        if getattr(sys, 'frozen', False):
            script_path = sys.executable
        else:
            script_path = os.path.abspath(__file__)  # Текущий файл (main.py)
        
        # Перезапускаем программу
        python = sys.executable
        self.logger.info(f"Запуск: {python} {script_path}")
        subprocess.Popen([python, script_path])
        
        # Завершаем текущий процесс
        os._exit(0)

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


def main():
    global _lock_file

    # Диагностика автозапуска
    print(f"[DEBUG] Запуск из: {os.path.abspath(sys.argv[0])}")
    print(f"[DEBUG] Рабочая директория: {os.getcwd()}")
    print(f"[DEBUG] Python: {sys.executable}")

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
            print(error_msg)
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
                print("[DEBUG] Лок освобожден при выходе")
            except Exception as e:
                print(f"[DEBUG] Ошибка освобождения лока: {e}")
        
        # Гарантированно удаляем файл лока
        try:
            if os.path.exists(_lock_file_path):
                os.remove(_lock_file_path)
                print(f"[DEBUG] Файл лока удален: {_lock_file_path}")
        except Exception as e:
            print(f"[DEBUG] Ошибка удаления файла лока: {e}")


if __name__ == "__main__":
    main()