# license.py
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import hashlib
import hmac
import secrets
from datetime import datetime
import json
import os

class LicenseManager:
    """Управление лицензионными ключами"""
    
    # Мастер-ключ разработчика (знаете только вы)
    _MASTER_SECRET = "SPEEDWATCH_EXPORT_2026_SECRET"  # Можете изменить на свой
    
    # Версия программы для привязки ключей
    _VERSION = "1.1.0"
    
    @staticmethod
    def validate_key(license_key: str) -> bool:
        """Проверка валидности ключа (без сервера)"""
        if not license_key:
            return False
        
        try:
            # Ожидаемый формат: XXXX-XXXX-XXXX-XXXX
            parts = license_key.split('-')
            if len(parts) != 4:
                return False
            
            # Проверяем подпись
            data_to_check = f"{parts[0]}{parts[1]}:{LicenseManager._VERSION}"
            expected = hmac.new(
                LicenseManager._MASTER_SECRET.encode(),
                data_to_check.encode(),
                hashlib.sha256
            ).hexdigest()[:4].upper()
            
            # Последняя часть ключа должна совпадать с подписью
            return parts[3] == expected
            
        except Exception:
            return False
    
    @staticmethod
    def generate_key(user_identifier: str) -> str:
        """
        Генерация ключа (используется только разработчиком)
        user_identifier: email или telegram пользователя
        """
        # Генерируем уникальную часть
        random_part = secrets.token_hex(6).upper()
        
        # Разбиваем на две части
        part1 = random_part[:4]
        part2 = random_part[4:8]
        part3 = random_part[8:12]
        
        # Создаем подпись
        data_to_sign = f"{part1}{part2}:{LicenseManager._VERSION}"
        signature = hmac.new(
            LicenseManager._MASTER_SECRET.encode(),
            data_to_sign.encode(),
            hashlib.sha256
        ).hexdigest()[:4].upper()
        
        # Формируем ключ: XXXX-XXXX-XXXX-XXXX
        license_key = f"{part1}-{part2}-{part3}-{signature}"
        
        # Сохраняем информацию о ключе (опционально)
        LicenseManager._save_key_info(license_key, user_identifier)
        
        return license_key
    
    @staticmethod
    def _save_key_info(key: str, user: str):
        """Сохранение информации о выданном ключе"""
        try:
            keys_file = "issued_keys.json"
            
            keys = []
            if os.path.exists(keys_file):
                with open(keys_file, 'r', encoding='utf-8') as f:
                    keys = json.load(f)
            
            keys.append({
                'key': key,
                'user': user,
                'date': datetime.now().isoformat(),
                'version': LicenseManager._VERSION
            })
            
            with open(keys_file, 'w', encoding='utf-8') as f:
                json.dump(keys, f, indent=2)
                
            print(f"✅ Ключ {key} сохранен для {user}")
            
        except Exception as e:
            print(f"❌ Ошибка сохранения ключа: {e}")


def show_premium_dialog(parent, callback):
    """
    Показать диалог ввода ключа для премиум-функции
    """
    # Создаем диалоговое окно
    dialog = tk.Toplevel(parent)
    dialog.title("🔐 Премиум-функция")
    dialog.geometry("450x280")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()
    
    # Центрируем
    dialog.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - 450) // 2
    y = parent.winfo_y() + (parent.winfo_height() - 280) // 2
    dialog.geometry(f"+{x}+{y}")
    
    # Заголовок
    ttk.Label(dialog, text="⚡ Экспорт в CSV", 
              font=('Arial', 14, 'bold')).pack(pady=(15, 5))
    
    # Пояснение
    ttk.Label(dialog, 
             text="Экспорт данных в CSV — это премиум-функция.\n"
                  "Введите ключ активации для доступа.",
             font=('Arial', 10), justify='center').pack(pady=(0, 15))
    
    # Поле ввода ключа
    frame = ttk.Frame(dialog)
    frame.pack(pady=10)
    
    ttk.Label(frame, text="Ключ активации:", 
              font=('Arial', 10)).pack(side='left', padx=(0, 5))
    
    key_var = tk.StringVar()
    key_entry = ttk.Entry(frame, textvariable=key_var, width=20, 
                          font=('Arial', 11, 'bold'))
    key_entry.pack(side='left')
    key_entry.focus()
    
    # Кнопки
    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=20)
    
    def on_activate():
        key = key_var.get().strip()
        if LicenseManager.validate_key(key):
            dialog.destroy()
            callback(key)  # Вызываем функцию экспорта
        else:
            messagebox.showerror("Ошибка", 
                               "❌ Неверный ключ активации.\n\n"
                               "Проверьте правильность ввода или обратитесь к разработчику.")
    
    ttk.Button(btn_frame, text="Активировать", 
               command=on_activate).pack(side='left', padx=5)
    
    ttk.Button(btn_frame, text="Отмена", 
               command=dialog.destroy).pack(side='left', padx=5)
    
    # Ссылка на разработчика (копирование в буфер)
    link_frame = ttk.Frame(dialog)
    link_frame.pack(pady=(10, 0))
    
    ttk.Label(link_frame, text="Нет ключа? Напишите разработчику: ", 
              font=('Arial', 9)).pack(side='left')
    
    # Создаем метку с email (выглядит как ссылка)
    email_label = tk.Label(link_frame, text="vldbkov@gmail.com", 
                          fg="blue", cursor="hand2",
                          font=('Arial', 9, 'underline'))
    email_label.pack(side='left')
    
    def copy_email(event=None):
        """Копирование email в буфер обмена"""
        try:
            # Копируем в буфер обмена
            dialog.clipboard_clear()
            dialog.clipboard_append("vldbkov@gmail.com")
            
            # Показываем уведомление
            messagebox.showinfo("Скопировано", 
                              "✅ Email скопирован!\n\n"
                              "Напишите нам\n"
                              "и мы пришлём вам ключ.")
        except Exception as e:
            print(f"Ошибка копирования: {e}")
    
    # Привязываем события
    email_label.bind("<Button-1>", copy_email)
    email_label.bind("<Enter>", lambda e: email_label.config(cursor="hand2"))
    
    # Комментарий под ссылкой
    ttk.Label(dialog, text="(нажмите на адрес, чтобы скопировать)",
              font=('Arial', 8), foreground='gray').pack(pady=(2, 0))
    
    # Примечание
    ttk.Label(dialog, text="Ключ действует для всех функций экспорта",
              font=('Arial', 8), foreground='gray').pack(pady=(15, 0))