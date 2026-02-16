# update_cli.ps1
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Настройка openspeedtest-cli" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Шаг 1: Скачивание
Write-Host "[1/4] Скачивание последней версии CLI..." -ForegroundColor Yellow
curl.exe -sLo openspeedtest-cli.new https://openspeedtest.ru/cli/openspeedtest-cli

if (-not (Test-Path openspeedtest-cli.new)) {
    Write-Host "ОШИБКА: Не удалось скачать файл!" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Файл скачан" -ForegroundColor Green

# Шаг 2: Создание исправленной версии
Write-Host "[2/4] Создание исправленной версии (без Unicode символов)..." -ForegroundColor Yellow
$bytes = [System.IO.File]::ReadAllBytes("openspeedtest-cli.new")
$text = [System.Text.Encoding]::UTF8.GetString($bytes)
$text = $text -replace '✔', '+' -replace '✗', 'x' -replace '✓', '+' -replace '✘', 'x'
[System.IO.File]::WriteAllText("openspeedtest-cli-fixed", $text, [System.Text.UTF8Encoding]::new($false))
Remove-Item openspeedtest-cli.new
Write-Host "  ✓ Исправленная версия сохранена как openspeedtest-cli-fixed" -ForegroundColor Green

# Шаг 3: Поиск API ключа
Write-Host "[3/4] Поиск API ключа..." -ForegroundColor Yellow
$apiKey = $null

# Проверяем наличие .env файла
if (Test-Path "..\.env") {
    $envContent = Get-Content "..\.env" -Encoding UTF8
    foreach ($line in $envContent) {
        if ($line -match 'OPENSPEEDTEST_API_KEY=(.+)') {
            $apiKey = $matches[1].Trim()
            break
        }
    }
}

if ($apiKey) {
    Write-Host "  ✓ API ключ найден в .env файле" -ForegroundColor Green
} else {
    Write-Host "  ⚠ API ключ не найден в .env" -ForegroundColor Yellow
    $apiKey = Read-Host "Введите ваш API ключ (64 символа)"
}

# Шаг 4: Настройка ключа в CLI
Write-Host "[4/4] Настройка API ключа в CLI..." -ForegroundColor Yellow

# Создаем временный Python скрипт для настройки
$configScript = @"
import json
import os
import sys

# Путь к конфигу
home = os.path.expanduser("~")
config_dir = os.path.join(home, ".config", "openspeedtest-cli")
config_file = os.path.join(config_dir, "config.json")

# Создаем директорию если нужно
os.makedirs(config_dir, mode=0o750, exist_ok=True)

# Сохраняем ключ
config_data = {"api_key": "$apiKey"}
with open(config_file, 'w') as f:
    json.dump(config_data, f, indent=2)

os.chmod(config_file, 0o600)
print("✓ API ключ сохранен в", config_file)
"@

$configScript | py -3.12

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   Настройка завершена!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Теперь можно запустить тест для проверки:" -ForegroundColor White
Write-Host "  py -3.12 .\openspeedtest-cli-fixed" -ForegroundColor Cyan
Write-Host ""
Write-Host "Или просто запустите программу:" -ForegroundColor White
Write-Host "  py -3.12 main.py" -ForegroundColor Cyan