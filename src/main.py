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


class InternetSpeedMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Internet Speed Monitor")
        self.root.geometry("700x500+20+20")
        
        # Установка иконки
        try:
            self.root.iconbitmap('src/icon.ico')
        except:
            self.create_icon()
        
        self.running = False
        self.monitor_thread = None
        self.db_path = "../data/internet_speed.db"
        self.setup_logging()
        self.setup_database()
        
        # Управление консолью
        self.console_visible = False  # Начинаем со скрытой консоли
        self.setup_console()
        
        # Создание интерфейса
        self.create_widgets()
        
        ##
        # Загружаем время последнего измерения
        last_time = self.get_last_measurement_time()
        self.last_check_var.set(last_time)        
        ##      
        
        # Загрузка настроек
        self.load_settings()
        
        # Защита от дублирования запуска
        if self.check_already_running():
            return
        
        # Создание меню для трея
        self.create_tray_icon()
        
        # При закрытии окна - сворачиваем в трей
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        
        # Запуск мониторинга если настроен автостарт
        if self.auto_start_var.get():
            self.start_monitoring()
        
        # Сразу сворачиваем в трей без показа окна
        self.minimize_to_tray()
        
        # Скрываем консоль после создания трея
        self.hide_console_on_start()
        
        # Запускаем главный цикл Tkinter
        self.root.after(100, self.check_tray_icon)


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
                server TEXT
            )
        ''')
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
    def update_tray_menu(self):
        """Обновление меню в трее"""
        try:
            from functools import partial
            
            # Определяем текст для консоли
            console_text = "Скрыть консоль" if self.console_visible else "Показать консоль"
            
            # Определяем текст для окна
            window_text = "Окно программы скрыть" if self.root.winfo_viewable() else "Окно программы показать"
            
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
    ###

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
        # Создаем Notebook (вкладки)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
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
        current_frame = ttk.LabelFrame(self.monitor_frame, text="Текущая скорость", padding=10)
        current_frame.pack(fill='x', padx=10, pady=5)
        
        # Скорость загрузки
        ttk.Label(current_frame, text="Скорость загрузки:", font=('Arial', 12)).grid(row=0, column=0, sticky='w', pady=5)
        self.download_var = tk.StringVar(value="0 Mbps")
        ttk.Label(current_frame, textvariable=self.download_var, font=('Arial', 14, 'bold')).grid(row=0, column=1, padx=10)
        
        # Скорость отдачи
        ttk.Label(current_frame, text="Скорость отдачи:", font=('Arial', 12)).grid(row=1, column=0, sticky='w', pady=5)
        self.upload_var = tk.StringVar(value="0 Mbps")
        ttk.Label(current_frame, textvariable=self.upload_var, font=('Arial', 14, 'bold')).grid(row=1, column=1, padx=10)
        
        # Пинг
        ttk.Label(current_frame, text="Пинг:", font=('Arial', 12)).grid(row=2, column=0, sticky='w', pady=5)
        self.ping_var = tk.StringVar(value="0 ms")
        ttk.Label(current_frame, textvariable=self.ping_var, font=('Arial', 14, 'bold')).grid(row=2, column=1, padx=10)
        
        # Время последнего измерения
        ttk.Label(current_frame, text="Последнее измерение:", font=('Arial', 12)).grid(row=3, column=0, sticky='w', pady=5)
        self.last_check_var = tk.StringVar(value="Никогда")
        ttk.Label(current_frame, textvariable=self.last_check_var, font=('Arial', 10)).grid(row=3, column=1, padx=10)
        
        # Фрейм с управлением
        control_frame = ttk.Frame(self.monitor_frame)
        control_frame.pack(fill='x', padx=10, pady=20)
        
        # Кнопки управления
        self.start_button = ttk.Button(control_frame, text="Запуск мониторинга", command=self.start_monitoring)
        self.start_button.pack(side='left', padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="Остановить", command=self.stop_monitoring, state='disabled')
        self.stop_button.pack(side='left', padx=5)
        
        self.test_button = ttk.Button(control_frame, text="Тест сейчас", command=self.run_speed_test)
        self.test_button.pack(side='left', padx=5)
        
        # Информация о следующем тесте
        ttk.Label(control_frame, text="Следующий тест через:").pack(side='left', padx=20)
        self.next_test_var = tk.StringVar(value="--:--:--")
        ttk.Label(control_frame, textvariable=self.next_test_var, font=('Arial', 10, 'bold')).pack(side='left')
        
        # Статус бар ПОД кнопками управления
        self.status_var = tk.StringVar()
        self.status_var.set("Готов к работе")
        status_bar = ttk.Label(self.monitor_frame, textvariable=self.status_var, relief=tk.SUNKEN, padding=5)
        status_bar.pack(fill='x', padx=10, pady=(0, 10))
    ###

    def setup_graph_tab(self):
        """Настройка вкладки с графиками"""
        # Панель управления графиками
        control_frame = ttk.Frame(self.graph_frame)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        # Выбор периода
        ttk.Label(control_frame, text="Период:").pack(side='left')
        
        self.period_var = tk.StringVar(value="1 день")
        periods = ["1 день", "7 дней", "30 дней", "Все время"]
        self.period_combo = ttk.Combobox(control_frame, textvariable=self.period_var, values=periods, state='readonly', width=10)
        self.period_combo.pack(side='left', padx=5)
        
        # Кнопка обновления
        ttk.Button(control_frame, text="Обновить график", command=self.update_graph).pack(side='left', padx=10)
        
        # Кнопка экспорта
        ttk.Button(control_frame, text="Экспорт PNG", command=self.export_graph).pack(side='left')
        
        # Область для графиков
        self.graph_canvas_frame = ttk.Frame(self.graph_frame)
        self.graph_canvas_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Создаем фигуру для matplotlib
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_canvas_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)


    def setup_log_tab(self):
        """Настройка вкладки журнала"""
        # Панель управления журналом
        log_control_frame = ttk.Frame(self.log_frame)
        log_control_frame.pack(fill='x', padx=10, pady=10)
        
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
        
        # Таблица журнала
        columns = ('ID', 'Время', 'Загрузка (Mbps)', 'Отдача (Mbps)', 'Пинг (ms)', 'Сервер')
        
        # Создаем Treeview с полосой прокрутки
        tree_frame = ttk.Frame(self.log_frame)
        tree_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Вертикальная полоса прокрутки
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side='right', fill='y')
        
        # Горизонтальная полоса прокрутки
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side='bottom', fill='x')
        
        self.log_tree = ttk.Treeview(tree_frame, columns=columns, show='headings',
                                    yscrollcommand=vsb.set, xscrollcommand=hsb.set)  
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
            else:  # Сервер
                self.log_tree.column(col, width=235, anchor=tk.W, stretch=False)
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
        settings_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
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
        ttk.Button(settings_frame, text="Восстановить по умолчанию", 
                  command=self.reset_settings).grid(row=3, column=1, pady=20)
        
        # Информация о программе
        info_frame = ttk.LabelFrame(self.settings_frame, text="Информация", padding=20)
        info_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(info_frame, text="Internet Speed Monitor v1.0").pack()
        ttk.Label(info_frame, text="Мониторинг скорости интернет-соединения").pack()
        ttk.Label(info_frame, text="© 2024").pack()


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
            self.logger.info("Иконка трея запущена")
        except Exception as e:
            self.logger.error(f"Ошибка создания иконки трея: {e}")


    def toggle_window_visibility(self):
        """Переключение видимости окна программы"""
        if self.root.state() == 'withdrawn' or not self.root.winfo_viewable():
            self.show_window()
        else:
            self.minimize_to_tray()
        
        # Обновляем меню
        self.update_tray_menu()


    def check_already_running(self):
        """Проверка, не запущено ли уже приложение"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('localhost', 12345))
            # Если смогли забиндиться на порт, значит приложение не запущено
            s.close()
            return False
        except:
            messagebox.showwarning("Внимание", "Приложение уже запущено!")
            self.root.quit()
            return True


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


    def save_settings(self):
        """Сохранение настроек в БД"""
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
            
            messagebox.showinfo("Успех", "Настройки сохранены!")
            self.logger.info("Настройки сохранены")
        except Error as e:
            self.logger.error(f"Ошибка сохранения настроек: {e}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {e}")


    def reset_settings(self):
        """Сброс настроек к значениям по умолчанию"""
        self.interval_var.set(60)
        self.auto_start_var.set(False)
        self.minimize_to_tray_var.set(True)
        self.save_settings()
    ###
    def reset_date_filter(self):
        """Сброс фильтра по дате"""
        today = datetime.now()
        self.date_from_entry.set_date(today)
        self.date_to_entry.set_date(today)
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
            app_path = os.path.abspath(sys.argv[0])
            
            if self.auto_start_var.get():
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
                self.logger.info("Добавлено в автозапуск")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    self.logger.info("Удалено из автозапуска")
                except:
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
        """Выполнение теста скорости через OpenSpeedTest"""
        try:
            # Обновляем статус на каждом этапе
            self.root.after(0, lambda: self.status_var.set("Запуск теста скорости через OpenSpeedTest..."))
            self.logger.info("Запуск теста скорости через OpenSpeedTest...")
            time.sleep(0.5)  # Небольшая задержка для отображения
            
            # Импортируем из нашего скрипта
            import openspeedtest as ost
            
            # Читаем API ключ из .env
            api_key = None
            try:
                with open('.env', 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("OPENSPEEDTEST_API_KEY="):
                            api_key = line.strip().split("=", 1)[1]
                            break
            except Exception as e:
                self.logger.error(f"Ошибка чтения .env: {e}")
            
            if not api_key:
                raise Exception("API ключ не найден в файле .env")
            
            # Конфиг для API
            config = {"api_key": api_key}
            
            # Получаем серверы
            self.root.after(0, lambda: self.status_var.set("Получение списка серверов..."))
            self.logger.info("Получение списка серверов...")
            servers = ost.fetch_servers_from_api(config)
            
            if not servers:
                raise Exception("Не удалось получить список серверов")
            
            # Находим лучший сервер
            self.root.after(0, lambda: self.status_var.set("Поиск лучшего сервера..."))
            self.logger.info("Поиск лучшего сервера...")
            server = ost.find_best_server(servers)
            server_name = server['name']
            
            # Получаем пинг и джиттер
            ping = server.get('ping', 0)
            jitter = server.get('jitter', 0)
            
            # Тест скачивания
            self.root.after(0, lambda: self.status_var.set("Тест скачивания..."))
            self.logger.info("Тест скачивания...")
            download_speed = ost.download_test(server, duration=5, threads=4)
            
            # Тест загрузки
            self.root.after(0, lambda: self.status_var.set("Тест загрузки..."))
            self.logger.info("Тест загрузки...")
            upload_speed = ost.upload_test(server, duration=5, threads=4)
            
            # Сохраняем результаты
            self.save_test_results(download_speed, upload_speed, ping, server_name)
            
            # Обновляем интерфейс с завершающим сообщением
            self.root.after(0, lambda: self._update_ui_with_results_and_status(
                download_speed, upload_speed, ping, server_name,
                f"Тест завершен"
            ))
            
            self.logger.info(f"Тест завершен: Download={download_speed:.2f} Mbps, "
                           f"Upload={upload_speed:.2f} Mbps, Ping={ping:.2f} ms")
            
        except Exception as e:
            self.logger.error(f"Ошибка теста скорости: {e}")
            self.root.after(0, lambda: self._update_ui_with_error(str(e)))

    ###
    def _update_ui_with_results(self, download, upload, ping, server):
        """Обновление интерфейс с результатами"""
        self.download_var.set(f"{download:.2f} Mbps")
        self.upload_var.set(f"{upload:.2f} Mbps")
        self.ping_var.set(f"{ping:.2f} ms")
        # ИЗМЕНЕНО: формат даты с "YYYY-MM-DD HH:MM:SS" на "DD.MM.YY HH:MM"
        self.last_check_var.set(datetime.now().strftime("%d.%m.%y %H:%M"))
        self.status_var.set("Тест завершен")
        self.test_button.config(state='normal')
    ###
    def _update_ui_with_results_and_status(self, download, upload, ping, server, status_message):
        """Обновление интерфейс с результатами и кастомным статусом"""
        self.download_var.set(f"{download:.2f} Mbps")
        self.upload_var.set(f"{upload:.2f} Mbps")
        self.ping_var.set(f"{ping:.2f} ms")
        self.last_check_var.set(datetime.now().strftime("%d.%m.%y %H:%M"))
        self.status_var.set(status_message)
        self.test_button.config(state='normal')

    ###
    def _update_ui_with_error(self, error_msg):
        """Обновление интерфейс при ошибке"""
        self.download_var.set("Ошибка")
        self.upload_var.set("Ошибка")
        self.ping_var.set("Ошибка")
        self.status_var.set(f"Ошибка: {error_msg}")
        self.test_button.config(state='normal')
        messagebox.showerror("Ошибка", f"Не удалось выполнить тест скорости: {error_msg}")

    ###
    def save_test_results(self, download, upload, ping, server):
        """Сохранение результатов теста в БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO speed_measurements 
                (timestamp, download_speed, upload_speed, ping, server) 
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'), download, upload, ping, server))
            
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
                SELECT id, timestamp, download_speed, upload_speed, ping, server 
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
            
            # Добавляем данные в таблицу
            for row in rows:
                ###
                # Форматируем дату из формата "YYYY-MM-DD HH:MM:SS.ffffff" в "DD.MM.YY HH:MM"
                timestamp = row[1]
                if timestamp and isinstance(timestamp, str):
                    try:
                        # Парсим оригинальную дату
                        dt = datetime.strptime(timestamp.split('.')[0], '%Y-%m-%d %H:%M:%S')
                        # Форматируем в нужный формат
                        formatted_timestamp = dt.strftime('%d.%m.%y %H:%M')
                    except:
                        formatted_timestamp = timestamp
                else:
                    formatted_timestamp = "N/A"

                formatted_row = (
                    row[0],
                    formatted_timestamp,  # НОВЫЙ ФОРМАТ ДАТЫ
                    f"{row[2]:.2f}" if row[2] else "N/A",
                    f"{row[3]:.2f}" if row[3] else "N/A",
                    f"{row[4]:.2f}" if row[4] else "N/A",
                    row[5] or "N/A"
                )
                ###
                self.log_tree.insert('', 'end', values=formatted_row)            
            
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
                SELECT timestamp, download_speed, upload_speed, ping 
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
            
            # Преобразуем строки времени в datetime
            if isinstance(timestamps[0], str):
                try:
                    timestamps = [datetime.strptime(ts, '%Y-%m-%d %H:%M:%S.%f') for ts in timestamps]
                except ValueError:
                    timestamps = [datetime.strptime(ts, '%Y-%m-%d %H:%M:%S') for ts in timestamps]
            
            # Создаем графики
            ax1 = self.fig.add_subplot(211)
            ax2 = self.fig.add_subplot(212)
            
            # Настраиваем шрифты для подписей осей 
            label_fontsize = 8  # Размер шрифта по умолчанию около 12, 
            title_fontsize = 11
            
            # График скорости
            ax1.plot(timestamps, download_speeds, 'b-', label='Загрузка', linewidth=2)
            ax1.plot(timestamps, upload_speeds, 'r-', label='Отдача', linewidth=2)
            ax1.set_title('Скорость интернета', fontsize=title_fontsize)
            ax1.set_ylabel('Скорость (Mbps)', fontsize=label_fontsize)
            ax1.legend(fontsize=label_fontsize)
            ax1.grid(True, alpha=0.3)
            ax1.tick_params(axis='both', labelsize=label_fontsize)
            
            # Форматируем ось X для дат в формате дд.мм.гг чч:мм
            import matplotlib.dates as mdates
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%y %H:%M'))
            
            # График пинга
            ax2.plot(timestamps, pings, 'g-', label='Пинг', linewidth=2)
            ax2.set_title('Пинг', fontsize=title_fontsize)
            ax2.set_xlabel('', fontsize=label_fontsize)
            ax2.set_ylabel('Пинг (ms)', fontsize=label_fontsize)
            ax2.legend(fontsize=label_fontsize)
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


    def export_log(self):
        """Экспорт журнала в CSV"""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=f"internet_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            
            if filename:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM speed_measurements ORDER BY timestamp DESC')
                rows = cursor.fetchall()
                conn.close()
                
                import csv
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    # Заголовки
                    writer.writerow(['ID', 'Timestamp', 'Download (Mbps)', 'Upload (Mbps)', 'Ping (ms)', 'Server'])
                    # Данные
                    for row in rows:
                        writer.writerow(row)
                
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


    def minimize_to_tray(self):
        """Сворачивание в системный трей"""
        if self.minimize_to_tray_var.get():
            self.root.withdraw()
            self.status_var.set("Свернуто в трей")
            self.logger.info("Приложение свернуто в трей")
        else:
            self.quit_app()


    def quit_app(self):
        """Завершение работы приложения"""
        self.running = False
        
        # Закрываем иконку в трее
        try:
            if hasattr(self, 'tray_icon'):
                self.tray_icon.stop()
        except:
            pass
        
        # Сохраняем настройки
        self.save_settings()
        
        # Закрываем приложение
        self.root.quit()
        self.logger.info("Приложение завершено")


def main():
    root = tk.Tk()
    app = InternetSpeedMonitor(root)
    root.mainloop()


if __name__ == "__main__":
    main()