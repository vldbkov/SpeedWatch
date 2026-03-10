# encrypted_db.py
"""
Модуль для работы с зашифрованной базой данных SQLCipher
"""
import os
import base64
import hashlib
from sqlcipher3 import dbapi2 as sqlcipher

class EncryptedDB:
    """Класс для работы с зашифрованной SQLite базой данных"""
    
    # Мастер-ключ собирается из частей (обфускация)
    @staticmethod
    def _get_master_key():
        """Получение мастер-ключа (обфусцировано)"""
        # Часть 1: из hex строки
        part1 = bytes.fromhex('737065656477617463685f6d6173746572').decode()  # "speedwatch_master"
        
        # Часть 2: из base64
        part2 = base64.b64decode(b'a2V5XzIwMjY=').decode()  # "key_2026"
        
        # Часть 3: из ASCII кодов
        part3 = ''.join(chr(x) for x in [95, 115, 101, 99, 114, 101, 116])  # "_secret"
        
        # Часть 4: из математической операции
        hash_part = hashlib.md5(b"SpeedWatch").hexdigest()[:4]  # первые 4 символа md5
        
        # Собираем ключ
        return f"{part1}_{part2}{part3}_{hash_part}"
    
    def __init__(self, db_path):
        self.db_path = db_path
        self.connection = None
        self.cursor = None
        self.master_key = self._get_master_key()
    
    def connect(self):
        """Установка соединения с БД и расшифровка мастер-ключом"""
        try:
            self.connection = sqlcipher.connect(self.db_path)
            self.connection.execute(f"PRAGMA key = '{self.master_key}';")
            self.cursor = self.connection.cursor()
            return self.connection
        except Exception as e:
            print(f"Ошибка подключения к БД: {e}")
            raise
    
    def close(self):
        """Закрытие соединения"""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.cursor = None
    
    def execute(self, query, params=None):
        """Выполнение SQL-запроса"""
        if not self.connection:
            self.connect()
        
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        
        return self.cursor
    
    def commit(self):
        """Подтверждение изменений"""
        if self.connection:
            self.connection.commit()
    
    def create_tables(self):
        """Создание таблиц при первом запуске"""
        # Таблица измерений скорости
        self.execute('''
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
        
        # Таблица настроек
        self.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        self.commit()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()