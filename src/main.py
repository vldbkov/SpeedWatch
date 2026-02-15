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
        print("[DEBUG] InternetSpeedMonitor __init__ started")
        try:
            self.dpi_scale = get_dpi_scale_factor()
            # ... остальной код метода
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
        self.root.title("Internet Speed Monitor")
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
        self.monitor_thread = None
        self.db_path = "../data/internet_speed.db"
        self.lock_file = None
        self.lock_file_path = os.path.join(tempfile.gettempdir(), "internet_monitor.lock")
        self.setup_logging()
        self.setup_database()
        
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
        self.is_first_load = False  # Сбрасываем после загрузки
        self.update_log()         # Обновляем журнал принудительно
       
        
        # Создание меню для трея
        self.create_tray_icon()
        
        # При закрытии окна - сворачиваем в трей и обновляем меню трея
        self.root.protocol("WM_DELETE_WINDOW", self.handle_window_close)
        
        # Запуск мониторинга если настроен автостарт
        if self.auto_start_var.get():
            self.start_monitoring()
        
        # Сворачиваем в трей если включена настройка
        if self.minimize_to_tray_var.get():
            self.minimize_to_tray()

        # Обновляем меню трея, чтобы текст пункта соответствовал текущему состоянию окна
        try:
            self.update_tray_menu()
        except Exception:
            pass
        
        ###
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
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('../data/speed_monitor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)


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
    ##
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
    ##
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
                    # Показать консоль
                    user32.ShowWindow(self.hwnd, 1)  # SW_SHOW = 1
                    self.console_visible = True
                
                # Обновляем меню с новым текстом
                self.update_tray_menu()
                    
        except Exception as e:
            self.logger.error(f"Ошибка переключения консоли: {e}")
    ###
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
    ###
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

    ###
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
    ###
    ###
    def setup_monitor_tab(self):
        """Настройка вкладки мониторинга"""
        # Фрейм с текущими показателями
        current_frame = ttk.LabelFrame(self.monitor_frame, text="Текущая скорость", padding=self.scale_value(15))
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
    ###

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
                self.log_tree.column(col, width=50, anchor=tk.CENTER, stretch=False)
            elif i == 1:  # Время
                self.log_tree.column(col, width=90, anchor=tk.CENTER, stretch=False)
            elif i == 2:  # Загрузка
                self.log_tree.column(col, width=100, anchor=tk.CENTER, stretch=False)
            elif i == 3:  # Отдача
                self.log_tree.column(col, width=100, anchor=tk.CENTER, stretch=False)
            elif i == 4:  # Пинг
                self.log_tree.column(col, width=70, anchor=tk.CENTER, stretch=False)
            elif i == 5:  # Джиттер
                self.log_tree.column(col, width=80, anchor=tk.CENTER, stretch=False)
            else:  # Сервер
                self.log_tree.column(col, width=200, anchor=tk.W, stretch=False)
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
        
        ttk.Label(info_frame, text="Internet Speed Monitor v1.0", font=self.scale_font('Arial', 12) + ('bold',)).pack()
        ttk.Label(info_frame, text="Мониторинг скорости интернет-соединения", font=self.scale_font('Arial', 10)).pack()
        ttk.Label(info_frame, text="© 2026", font=self.scale_font('Arial', 9)).pack()


    def create_tray_icon(self):
        """Создание иконки в системном трее"""
        try:
            # Создаем простое изображение для иконки
            image = Image.new('RGB', (64, 64), color='blue')
            draw = ImageDraw.Draw(image)
            draw.text((20, 25), "SPD", fill='white')
            
            self.tray_icon = pystray.Icon(
                "internet_speed_monitor", 
                image, 
                "Internet Speed Monitor"
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
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            
            app_name = "InternetSpeedMonitor"
            
            # Путь к pythonw.exe (без окна консоли)
            python_dir = os.path.dirname(sys.executable)
            pythonw_path = os.path.join(python_dir, "pythonw.exe")
            
            # Проверяем существование pythonw.exe
            if not os.path.exists(pythonw_path):
                pythonw_path = sys.executable  # fallback на python.exe
            
            # Путь к скрипту
            script_path = os.path.abspath(sys.argv[0])
            
            if self.auto_start_var.get():
                # Формируем команду: pythonw.exe путь_к_скрипту
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

    ###
    def run_speed_test(self):
        """Запуск теста скорости интернета"""
        self.status_var.set("Выполняется тест скорости...")
        self.test_button.config(state='disabled')
        
        # Сбрасываем таймер отсчета
        self.next_test_var.set("--:--:--")
        
        # Запускаем тест в отдельном потоке
        test_thread = threading.Thread(target=self._perform_speed_test, daemon=True)
        test_thread.start()

    ###
    def _perform_speed_test(self):
        """Выполнение теста скорости через OpenSpeedTest с проверками соединения"""
        try:
            # Проверяем интернет-соединение перед началом
            if not self.check_internet_connection():
                error_msg = "Нет подключения к интернету"
                self.logger.error(error_msg)
                self.root.after(0, lambda: self._update_ui_with_error(error_msg))
                return
            
            # Обновляем статус
            self.root.after(0, lambda: self.status_var.set("Запуск теста скорости через OpenSpeedTest..."))
            self.logger.info("Запуск теста скорости через OpenSpeedTest...")
            time.sleep(0.5)
            
            # Импортируем из нашего скрипта
            import openspeedtest as ost
            
            # Читаем API ключ из .env
            api_key = None
            # Определяем путь к .env (на уровень выше папки src)
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            self.logger.info(f"Поиск .env по пути: {env_path}")
            
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("OPENSPEEDTEST_API_KEY="):
                            api_key = line.strip().split("=", 1)[1]
                            break
                if api_key:
                    self.logger.info(f"API ключ найден")
                else:
                    self.logger.error("API ключ не найден в файле .env")
            except FileNotFoundError:
                self.logger.error(f"Файл .env не найден по пути: {env_path}")
                # Пробуем найти в текущей директории
                try:
                    with open('.env', 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith("OPENSPEEDTEST_API_KEY="):
                                api_key = line.strip().split("=", 1)[1]
                                break
                    if api_key:
                        self.logger.info(f"API ключ найден в текущей директории")
                except:
                    pass
            except Exception as e:
                self.logger.error(f"Ошибка чтения .env: {e}")
            
            if not api_key:
                raise Exception(f"API ключ не найден в файле .env")
            
            # Конфиг для API
            config = {"api_key": api_key}
            
            # Проверка соединения перед получением серверов
            if not self.check_internet_connection():
                raise Exception("Потеряно соединение с интернетом")
            
            # Получаем серверы
            self.root.after(0, lambda: self.status_var.set("Получение списка серверов..."))
            self.logger.info("Получение списка серверов...")
            servers = ost.fetch_servers_from_api(config)
            
            if not servers:
                raise Exception("Не удалось получить список серверов")
            
            # Проверка соединения перед поиском сервера
            if not self.check_internet_connection():
                raise Exception("Потеряно соединение с интернетом")
            
            # Находим лучший сервер
            self.root.after(0, lambda: self.status_var.set("Поиск лучшего сервера..."))
            self.logger.info("Поиск лучшего сервера...")
            
            # Запускаем поиск сервера с таймаутом
            import concurrent.futures
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(ost.find_best_server, servers)
                try:
                    server = future.result(timeout=30)  # Таймаут 30 секунд
                except concurrent.futures.TimeoutError:
                    raise Exception("Поиск сервера занял слишком много времени. Возможно, проблемы с сетью.")
                except Exception as e:
                    raise Exception(f"Ошибка при поиске сервера: {e}")

            server_name = server['name']
            
            # Получаем пинг и джиттер
            ping = server.get('ping', 0)
            jitter = server.get('jitter', 0)
            
            duration = 10  # фиксированная длительность теста
            
            # Проверка соединения перед тестом скачивания
            if not self.check_internet_connection():
                raise Exception("Потеряно соединение с интернетом перед тестом скачивания")
            
            # Тест скачивания
            self.root.after(0, lambda: self.status_var.set("Тест скачивания..."))
            self.logger.info("Тест скачивания...")
            try:
                download_speed = ost.download_test(server, duration=duration, threads=4)
            except Exception as e:
                if "connection" in str(e).lower() or "timeout" in str(e).lower():
                    raise Exception("Соединение прервано во время теста скачивания")
                raise
            
            # Проверка соединения перед тестом загрузки
            if not self.check_internet_connection():
                raise Exception("Потеряно соединение с интернетом перед тестом загрузки")
            
            # Тест загрузки
            self.root.after(0, lambda: self.status_var.set("Тест загрузки..."))
            self.logger.info("Тест загрузки...")
            try:
                upload_speed = ost.upload_test(server, duration=duration, threads=4)
            except Exception as e:
                if "connection" in str(e).lower() or "timeout" in str(e).lower():
                    raise Exception("Соединение прервано во время теста загрузки")
                raise
            
            # Сохраняем результаты
            self.save_test_results(download_speed, upload_speed, ping, jitter, server_name)
            
            # Обновляем интерфейс
            self.root.after(0, lambda: self._update_ui_with_results_and_status(
                download_speed, upload_speed, ping, jitter, server_name,
                "Тест завершен"
            ))
            
            self.logger.info(f"Тест завершен: Download={download_speed:.2f} Mbps, "
                           f"Upload={upload_speed:.2f} Mbps, Ping={ping:.2f} ms, Jitter={jitter:.2f} ms")
            
        except Exception as e:
            self.logger.error(f"Ошибка теста скорости: {e}")
            error_msg = str(e)
            self.root.after(0, lambda: self._update_ui_with_error(error_msg))
    ###
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
    ###
    def _update_ui_with_results_and_status(self, download, upload, ping, jitter, server, status_message):
        """Обновление интерфейс с результатами и кастомным статусом"""
        self.download_var.set(f"{download:.2f} Mbps")
        self.upload_var.set(f"{upload:.2f} Mbps")
        self.ping_var.set(f"{ping:.2f} ms")
        self.jitter_var.set(f"{jitter:.2f} ms")
        self.last_check_var.set(datetime.now().strftime("%d.%m.%y %H:%M"))
        self.status_var.set(status_message)
        self.test_button.config(state='normal')

    ###
    def _update_ui_with_error(self, error_msg):
        """Обновление интерфейс при ошибке"""
        self.download_var.set("Ошибка")
        self.upload_var.set("Ошибка")
        self.ping_var.set("Ошибка")
        self.jitter_var.set("Ошибка")
        self.status_var.set(f"Ошибка: {error_msg}")
        self.test_button.config(state='normal')
        messagebox.showerror("Ошибка", f"Не удалось выполнить тест скорости: {error_msg}")

    ###
    def save_test_results(self, download, upload, ping, jitter, server):
        """Сохранение результатов теста в БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO speed_measurements 
                (timestamp, download_speed, upload_speed, ping, jitter, server) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'), download, upload, ping, jitter, server))
            
            conn.commit()
            conn.close()
            
            # Обновляем время последнего измерения
            current_time = datetime.now().strftime('%d.%m.%y %H:%M')
            self.last_check_var.set(current_time)
            
            # Обновляем журнал и графики
            self.root.after(0, self.update_log)
            self.root.after(0, self.update_graph)
            
        except Error as e:
            self.logger.error(f"Ошибка сохранения результатов: {e}")
    ###

    def start_monitoring(self):
        """Запуск периодического мониторинга"""
        if self.running:
            return
        
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
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.test_button.config(state='normal')  # Добавить эту строку
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

    ##
    def update_next_test_timer(self):
        """Обновление таймера до следующего теста"""
        if not self.running:
            return
        
        now = datetime.now()
        if self.next_test_time:
            time_left = self.next_test_time - now
            if time_left.total_seconds() > 0:
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                timer_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                self.next_test_var.set(timer_text)
                
                # Добавляем статус с отсчетом времени
                self.status_var.set(f"Отсчет времени до следующей проверки")
            else:
                # Время пришло, обновляем следующее время
                self.next_test_time = now + timedelta(minutes=self.interval_var.get())
    ###

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
###
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
###
            conn.close()
            
            # Обновляем статус
            self.status_var.set(f"Загружено записей: {len(rows)}")
            
        except Error as e:
            self.logger.error(f"Ошибка обновления журнала: {e}")
            self.status_var.set(f"Ошибка загрузки журнала: {e}")
    ###
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
          
    ###
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
            
            # Фильтруем N/A значения (None, 0 или пустые)
            # Для скорости загрузки/отдачи
            download_valid = [(t, v) for t, v in zip(timestamps, download_speeds) if v and v > 0]
            upload_valid = [(t, v) for t, v in zip(timestamps, upload_speeds) if v and v > 0]
            # Для пинга и джиттера
            ping_valid = [(t, v) for t, v in zip(timestamps, pings) if v and v > 0]
            jitter_valid = [(t, v) for t, v in zip(timestamps, jitters) if v and v >= 0]
            
            # Вычисляем средние значения
            avg_download = sum(v for _, v in download_valid) / len(download_valid) if download_valid else 0
            avg_upload = sum(v for _, v in upload_valid) / len(upload_valid) if upload_valid else 0
            avg_ping = sum(v for _, v in ping_valid) / len(ping_valid) if ping_valid else 0
            avg_jitter = sum(v for _, v in jitter_valid) / len(jitter_valid) if jitter_valid else 0
            
            # Разделяем обратно на timestamps и values из отфильтрованных данных
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
            
            # Форматируем ось X для дат в формате дд.мм.гг чч:мм
            import matplotlib.dates as mdates
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%y %H:%M'))
            
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
            
            # Форматируем ось X для дат в формате дд.мм.гг чч:мм
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%y %H:%M'))
            
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
    ###

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

    ###
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
                        # Записываем как есть, без форматирования
                        writer.writerow(row)
                
                self.status_var.set(f"Журнал экспортирован: {filename}")
                self.logger.info(f"Журнал экспортирован в {filename}")
                messagebox.showinfo("Успех", f"Журнал сохранен в файл:\n{filename}")
                
        except Exception as e:
            self.logger.error(f"Ошибка экспорта журнала: {e}")
            messagebox.showerror("Ошибка", f"Не удалось экспортировать журнал: {e}")
###

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
        
        # Закрываем консоль
        self.close_console()
        
        # Останавливаем мониторинг если он запущен
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)
        
        # Закрываем иконку в трее
        try:
            if hasattr(self, 'tray_icon'):
                self.tray_icon.stop()
        except:
            pass
        
        # Закрываем основное окно
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
        
        # Перезапускаем программу
        python = sys.executable
        script = os.path.abspath(sys.argv[0])
        subprocess.Popen([python, script])
        
        # Завершаем текущий процесс
        os._exit(0)

def check_if_already_running():
    """Проверка через файловую блокировку - не запущено ли уже приложение"""
    global _lock_file
    
    try:
        if sys.platform == 'win32':
            import msvcrt
            print(f"[DEBUG] Попытка захватить файловый лок: {_lock_file_path}")
            
            # Открываем файл для добавления/чтения
            lock_f = open(_lock_file_path, 'a+')
            
            try:
                # Пытаемся захватить эксклюзивный лок на первый байт
                msvcrt.locking(lock_f.fileno(), msvcrt.LK_NBLCK, 1)
                # Успешно захватили - других экземпляров нет
                print(f"[DEBUG] ✓ Лок захвачен успешно, процесс может продолжать")
                _lock_file = lock_f  # Сохраняем файл - держим блокировку
                return False  # Возвращаем False = нет других запущенных экземпляров
            except (OSError, IOError, BlockingIOError) as e:
                # Не удалось захватить лок - другой процесс его удерживает
                print(f"[DEBUG] ✗ Лок уже занят другим процессом: {e}")
                lock_f.close()
                return True  # Возвращаем True = приложение уже запущено
        else:
            # Unix
            import fcntl
            print(f"[DEBUG] Попытка захватить файловый лок (Unix): {_lock_file_path}")
            
            lock_f = open(_lock_file_path, 'w')
            try:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                print(f"[DEBUG] ✓ Лок захвачен успешно, процесс может продолжать")
                _lock_file = lock_f
                return False
            except IOError as e:
                print(f"[DEBUG] ✗ Лок уже занят другим процессом: {e}")
                lock_f.close()
                return True
    
    except Exception as e:
        print(f"[DEBUG] Ошибка при проверке лока: {e}")
        # Если ошибка - даем разрешение на запуск (лучше двойной запуск, чем запирание)
        return False


def main():
    global _lock_file
    
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