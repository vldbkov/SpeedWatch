#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль-обертка для openspeedtest-cli
Исправленная версия с захватом вывода
"""

import sys
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
    
    def run_test(self, duration=10, threads=8, no_submit=True, status_callback=None):
        """
        Запуск теста скорости с захватом вывода
        """
        print("\n" + "="*50)
        print("SpeedTestRunner.run_test() ИСПРАВЛЕННАЯ ВЕРСИЯ")
        print("="*50)
        
        # Сохраняем оригинальные аргументы
        original_argv = sys.argv.copy()
        
        # Устанавливаем аргументы для openspeedtest_cli
        sys.argv = ['openspeedtest_cli.py', 
                   f'--duration={duration}', 
                   f'--threads={threads}']
        
        if no_submit:
            sys.argv.append('--no-submit')
        
        print(f"Аргументы: {sys.argv}")
        
        # Сохраняем оригинальные stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        # Создаем буферы для захвата вывода
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        
        # Для callback будем также дублировать вывод в буфер
        all_output = []
        
        class TeeOutput(io.StringIO):
            def __init__(self, callback=None, buffer=None):
                super().__init__()
                self.callback = callback
                self.buffer = buffer
                self.line_buffer = ""
            
            def write(self, s):
                # Сохраняем в основной буфер
                if self.buffer:
                    self.buffer.write(s)
                
                # Сохраняем все строки для парсинга
                all_output.append(s)
                
                # Для callback - отправляем КАЖДУЮ строку немедленно
                if self.callback:
                    # Разбиваем на строки и отправляем каждую
                    lines = s.split('\n')
                    for line in lines:
                        if line.strip():
                            # Очищаем от ANSI
                            clean_line = self._clean_ansi(line.strip())
                            if clean_line:
                                # Отправляем ВСЕ clean_line без фильтрации
                                self.callback(clean_line)
                
                return len(s)

            def _clean_ansi(self, text):
                """Удаляет ANSI escape последовательности"""
                import re
                ansi_escape = re.compile(r'\x1B\[[0-9;]*[a-zA-Z]|\x1B\[[0-9;]*')
                return ansi_escape.sub('', text)
        
        try:
            # Перенаправляем stdout/stderr
            sys.stdout = TeeOutput(callback=status_callback, buffer=stdout_buffer)
            sys.stderr = TeeOutput(callback=status_callback, buffer=stderr_buffer)
            
            print("Попытка импорта openspeedtest_cli...")
            # Импортируем и запускаем
            import openspeedtest_cli
            print("openspeedtest_cli импортирован")
            
            # Запускаем main
            print("Запуск openspeedtest_cli.main()...")
            openspeedtest_cli.main()
            print("openspeedtest_cli.main() завершен")
            
        except SystemExit:
            print("Поймано SystemExit (нормально)")
            pass
        except Exception as e:
            print(f"ИСКЛЮЧЕНИЕ: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # Восстанавливаем stdout/stderr и аргументы
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.argv = original_argv
            print("stdout/stderr восстановлены")
        
        # Получаем полный вывод
        stdout = stdout_buffer.getvalue()
        stderr = stderr_buffer.getvalue()
        
        # Объединяем весь вывод для парсинга
        full_output = stdout + '\n'.join(all_output)
        
        print(f"\nПолучено {len(stdout)} символов stdout")
        print(f"Получено {len(stderr)} символов stderr")
        
        if stderr:
            print(f"STDERR: {stderr[:200]}...")
        
        if not stdout and not all_output:
            print("ОШИБКА: вывод пустой!")
            return None
        
        # Парсим результаты
        print("Парсинг результатов...")
        result = self._parse_results(full_output)
        print(f"Результат парсинга: {result}")
        
        return result
    
    def _clean_ansi(self, text):
        """Удаляет ANSI escape последовательности из текста"""
        import re
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
        
        # Парсим сервер
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
        
        # Парсим значения
        for line in lines:
            line = line.strip()
            
            if "Ping:" in line:
                match = re.search(r'Ping:\s+(\d+\.?\d*)', line)
                if match:
                    result['ping'] = float(match.group(1))
            
            if "Jitter:" in line:
                match = re.search(r'Jitter:\s+(\d+\.?\d*)', line)
                if match:
                    result['jitter'] = float(match.group(1))
            
            if "Download:" in line:
                match = re.search(r'Download:\s+(\d+\.?\d*)', line)
                if match:
                    val = float(match.group(1))
                    if val > 0:
                        result['download'] = val
            
            if "Upload:" in line:
                match = re.search(r'Upload:\s+(\d+\.?\d*)', line)
                if match:
                    val = float(match.group(1))
                    if val > 0:
                        result['upload'] = val
        
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