#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль-обертка для openspeedtest-cli
Позволяет вызывать тест скорости как функцию, а не внешний процесс
"""

import sys
import os
import io
import contextlib
import re
from datetime import datetime

class SpeedTestRunner:
    """Класс для запуска speedtest без внешнего процесса"""
    
    def __init__(self, logger=None):
        self.logger = logger
        
    def log(self, msg):
        if self.logger:
            self.logger.info(f"[SpeedTest] {msg}")
        else:
            print(f"[SpeedTest] {msg}")
    
    def run_test(self, duration=10, threads=8, no_submit=True):
        """
        Запуск теста скорости через импортированный модуль
        Возвращает словарь с результатами
        """
        # Сохраняем оригинальные аргументы
        original_argv = sys.argv.copy()
        
        # Устанавливаем аргументы для openspeedtest_cli
        sys.argv = ['openspeedtest_cli.py', 
                   f'--duration={duration}', 
                   f'--threads={threads}']
        
        if no_submit:
            sys.argv.append('--no-submit')
        
        # Перехватываем stdout
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        # Сохраняем оригинальные stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        try:
            # Перенаправляем stdout/stderr
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            # Импортируем и запускаем
            import openspeedtest_cli
            
            # Запускаем main
            openspeedtest_cli.main()
            
        except SystemExit:
            # main может вызывать sys.exit() - это нормально
            pass
        except Exception as e:
            self.log(f"Ошибка при запуске теста: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # Восстанавливаем stdout/stderr и аргументы
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.argv = original_argv
        
        # Получаем вывод
        stdout = stdout_capture.getvalue()
        stderr = stderr_capture.getvalue()        
       
        if stderr:
            self.log(f"STDERR: {stderr}")
        
        if not stdout:
            self.log("ОШИБКА: stdout пустой!")
            return None
        
        # Парсим результаты
        return self._parse_results(stdout)
    
    def _clean_ansi(self, text):
        """Удаляет ANSI escape последовательности из текста"""
        import re
        # Удаляем все ESC-последовательности
        ansi_escape = re.compile(r'\x1B\[[0-9;]*[a-zA-Z]|\x1B\[[0-9;]*')
        return ansi_escape.sub('', text)
    
    def _parse_results(self, output):
        """Парсинг результатов из вывода"""
        # Очищаем от ANSI последовательностей
        output = self._clean_ansi(output)
        
        result = {
            'ping': None,
            'jitter': None,
            'download': None,
            'upload': None,
            'server': 'Unknown',
            'server_city': 'Unknown',
            'server_provider': 'Unknown'
        }
        
        lines = output.split('\n')
        
        # Парсим сервер (оставляем как есть)
        for line in lines:
            if "Лучший сервер найден:" in line:
                try:
                    full = line.split("Лучший сервер найден:", 1)[1].strip()
                    clean = re.sub(r'\s*\(\d+\.?\d*\s*мс\s*\)\s*$', '', full)
                    
                    if '(' in clean:
                        parts = clean.split('(', 1)
                        city_country = parts[0].strip()
                        provider = parts[1].rstrip(')').strip()
                    elif ',' in clean:
                        parts = clean.split(',', 1)
                        city_country = parts[0].strip()
                        provider = parts[1].strip() if len(parts) > 1 else "Unknown"
                    else:
                        city_country = clean
                        provider = "Unknown"
                    
                    result['server'] = clean
                    result['server_city'] = city_country
                    result['server_provider'] = provider
                    break
                except:
                    pass
        
        # Парсим значения - ищем во всех строках, но предпочитаем последние
        for line in lines:
            line = line.strip()
            
            # Пинг
            if "Ping:" in line:
                match = re.search(r'Ping:\s+(\d+\.?\d*)', line)
                if match:
                    result['ping'] = float(match.group(1))
            
            # Джиттер
            if "Jitter:" in line:
                match = re.search(r'Jitter:\s+(\d+\.?\d*)', line)
                if match:
                    result['jitter'] = float(match.group(1))
            
            # Download
            if "Download:" in line:
                match = re.search(r'Download:\s+(\d+\.?\d*)', line)
                if match:
                    # Берем последнее ненулевое значение
                    val = float(match.group(1))
                    if val > 0:
                        result['download'] = val
            
            # Upload
            if "Upload:" in line:
                match = re.search(r'Upload:\s+(\d+\.?\d*)', line)
                if match:
                    val = float(match.group(1))
                    if val > 0:
                        result['upload'] = val
        
        # Если не нашли в процессе, ищем в финальном блоке (последние 20 строк)
        last_lines = lines[-20:]
        for line in last_lines:
            if "Ping:" in line and result['ping'] is None:
                match = re.search(r'Ping:\s+(\d+\.?\d*)', line)
                if match:
                    result['ping'] = float(match.group(1))
            
            if "Jitter:" in line and result['jitter'] is None:
                match = re.search(r'Jitter:\s+(\d+\.?\d*)', line)
                if match:
                    result['jitter'] = float(match.group(1))
        
        return result

# Для тестирования
if __name__ == "__main__":
    runner = SpeedTestRunner()
    result = runner.run_test()
    if result:
        print("\nРезультаты:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    else:
        print("Тест не удался")