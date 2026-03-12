# report_generator.py
from datetime import datetime
import os

class ReportGenerator:
    """Генератор детальных отчетов для провайдера"""
    
    def __init__(self, db, parent):
        self.db = db
        self.parent = parent  # ссылка на InternetSpeedMonitor для доступа к данным
    
    def generate_report(self, period_name, start_date, end_date, stats):
        """Генерация текстового отчета"""
        
        # Заголовок
        report = []
        report.append("="*50)
        report.append("         SPEEDWATCH - ОТЧЕТ КАЧЕСТВА")
        report.append(f"              за {period_name}")
        report.append("="*50)
        report.append("")
        
        # Общая статистика
        report.append("📊 ОБЩАЯ СТАТИСТИКА")
        report.append("-"*40)
        report.append(f"📅 Период: {start_date} - {end_date}")
        report.append(f"📊 Всего измерений: {stats['count']}")
        report.append("")
        
        # Скорость
        report.append("📈 СКОРОСТЬ (Mbps)")
        report.append("-"*40)
        report.append(f"📥 Загрузка:  {stats['avg_download']:.1f} (сред.)")
        report.append(f"   Лучшая:    {stats['max_download']:.1f}")
        report.append(f"   Худшая:    {stats['min_download']:.1f}")
        report.append(f"📤 Отдача:    {stats['avg_upload']:.1f} (сред.)")
        
        # Сравнение с тарифом
        planned = self.parent.planned_speed_var.get() if hasattr(self.parent, 'planned_speed_var') else 0
        if planned > 0:
            percent = (stats['avg_download'] / planned) * 100
            report.append(f"📋 Тариф:     {planned} Mbps")
            report.append(f"📉 Соответствие: {percent:.1f}%")
        report.append("")
        
        # Пинг и джиттер
        report.append("📶 ПИНГ И ДЖИТТЕР (ms)")
        report.append("-"*40)
        report.append(f"📶 Пинг:      {stats['avg_ping']:.1f} (сред.)")
        report.append(f"   Макс:      {stats['max_ping']:.1f}")
        report.append(f"   Мин:       {stats['min_ping']:.1f}")
        report.append(f"📊 Джиттер:   {stats['avg_jitter']:.1f} (сред.)")
        report.append(f"   Макс:      {stats['max_jitter']:.1f}")
        report.append("")
        
        # Проблемные периоды
        report.append("⏰ ПРОБЛЕМНЫЕ ПЕРИОДЫ")
        report.append("-"*40)
        
        if stats.get('hourly'):
            # Худший час
            worst_hour = min(stats['hourly'], key=lambda x: x[1])
            hour = int(worst_hour[0])
            report.append(f"🕐 Худшее время: {hour:02d}:00 - {hour+1:02d}:00")
            report.append(f"   Скорость: {worst_hour[1]:.1f} Mbps")
        
        if stats.get('daily'):
            # Худший день
            worst_day = min(stats['daily'], key=lambda x: x[2])
            days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
            day_name = days[int(worst_day[0])]
            report.append(f"📉 Худший день: {day_name} ({worst_day[1][8:10]}.{worst_day[1][5:7]})")
            report.append(f"   Скорость: {worst_day[2]:.1f} Mbps")
        report.append("")
        
        # Распределение по тарифу
        if planned > 0:
            report.append("📊 СООТВЕТСТВИЕ ТАРИФУ")
            report.append("-"*40)
            
            # Простой анализ по hourly данным
            if stats.get('hourly'):
                good_hours = sum(1 for h in stats['hourly'] if h[1] >= planned * 0.9)
                medium_hours = sum(1 for h in stats['hourly'] if planned * 0.7 <= h[1] < planned * 0.9)
                bad_hours = sum(1 for h in stats['hourly'] if h[1] < planned * 0.7)
                total_hours = len(stats['hourly'])
                
                if total_hours > 0:
                    report.append(f"✅ Соответствует (≥90%): {good_hours/total_hours*100:.0f}%")
                    report.append(f"⚠️ Ниже нормы (70-90%): {medium_hours/total_hours*100:.0f}%")
                    report.append(f"❌ Критично (<70%): {bad_hours/total_hours*100:.0f}%")
            report.append("")
        
        # Подпись
        report.append("="*50)
        report.append("📊 Графики прилагаются в отдельном файле")
        report.append(f"📅 Отчет сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        report.append("="*50)
        
        return "\n".join(report)
    
    def save_report(self, filename, content):
        """Сохранение отчета в файл"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"Ошибка сохранения отчета: {e}")
            return False