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
    def validate_key_with_email(email: str, license_key: str) -> bool:
        
        if not email or not license_key:
            return False
        
        try:
            # Сначала пробуем проверить как старый ключ (без email)
            if LicenseManager.validate_key(license_key):
                return True
            
            # Если не прошел, пробуем проверить с email
            expected = LicenseManager.generate_key(email)
            
            return license_key == expected
        except Exception as e:
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
    Показать диалог ввода email и ключа для премиум-функции
    """
    dialog = tk.Toplevel(parent)
    dialog.title("🔐 Премиум-активация")
    dialog.geometry("380x320")  # было 400x320
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()
    
    # Центрируем
    dialog.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - 400) // 2
    y = parent.winfo_y() + (parent.winfo_height() - 320) // 2
    dialog.geometry(f"+{x}+{y}")
    
    # Заголовок
    ttk.Label(dialog, text="⚡ Активация премиум-доступа", 
              font=('Arial', 12, 'bold')).pack(pady=(15, 10))
    
    # Пояснение
    ttk.Label(dialog, 
             text="Введите email и ключ, полученный от разработчика",
             font=('Arial', 9), justify='center').pack(pady=(0, 15))
    
    # Email
    frame_email = ttk.Frame(dialog)
    frame_email.pack(pady=5, padx=20)
    
    ttk.Label(frame_email, text="Email:", font=('Arial', 10)).pack(anchor='w')
    email_var = tk.StringVar()
    email_entry = ttk.Entry(frame_email, textvariable=email_var, width=28, 
                            font=('Arial', 10))
    email_entry.pack(pady=2)
    
    # Ключ
    frame_key = ttk.Frame(dialog)
    frame_key.pack(pady=5, padx=20)
    
    ttk.Label(frame_key, text="Ключ:", font=('Arial', 10)).pack(anchor='w')
    key_var = tk.StringVar()
    key_entry = ttk.Entry(frame_key, textvariable=key_var, width=28, 
                          font=('Arial', 10, 'bold'), show='*')
    key_entry.pack(pady=2)
    
    # Кнопки
    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=20)
    
    def on_activate():
        email = email_var.get().strip()
        key = key_var.get().strip()
        
        if not email or not key:
            messagebox.showerror("Ошибка", "Введите email и ключ")
            return
        
        if LicenseManager.validate_key_with_email(email, key):
            dialog.destroy()
            callback(key, email)  # передаем и ключ и email
        else:
            messagebox.showerror("Ошибка", 
                               "❌ Неверный email или ключ активации.\n\n"
                               "Проверьте правильность ввода или обратитесь к разработчику.")
    
    ttk.Button(btn_frame, text="Активировать", 
               command=on_activate).pack(side='left', padx=5)
    
    ttk.Button(btn_frame, text="Отмена", 
               command=dialog.destroy).pack(side='left', padx=5)
    
    # Ссылка на разработчика
    link_frame = ttk.Frame(dialog)
    link_frame.pack(pady=(10, 0))
    
    ttk.Label(link_frame, text="Нет ключа? Напишите разработчику: ", 
              font=('Arial', 9)).pack(side='left')
    
    email_link = tk.Label(link_frame, text="vldbkov@gmail.com", 
                          fg="blue", cursor="hand2",
                          font=('Arial', 9, 'underline'))
    email_link.pack(side='left')
    
    def copy_email(event=None):
        dialog.clipboard_clear()
        dialog.clipboard_append("vldbkov@gmail.com")
        messagebox.showinfo("Скопировано", "✅ Email скопирован!\n\nНапишите нам и мы пришлём вам ключ.")
    
    email_link.bind("<Button-1>", copy_email)
    
    # Примечание
    ttk.Label(dialog, text="Ключ привязан к email и действует для всех функций экспорта",
              font=('Arial', 8), foreground='gray').pack(pady=(15, 0))
    
    # Фокус на поле email
    email_entry.focus()