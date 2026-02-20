# Setup logging
$logFile = "build_log_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
Start-Transcript -Path $logFile -Append

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SpeedWatch.exe Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Log file: $logFile" -ForegroundColor Yellow
Write-Host ""

# Check last exit code
function Test-ExitCode {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR! Code: $LASTEXITCODE" -ForegroundColor Red
        Stop-Transcript
        exit $LASTEXITCODE
    }
}

# Step 1: Check Python 3.12
Write-Host "[1/8] Checking Python 3.12..." -ForegroundColor Yellow
$pythonCmd = "C:\Python312\python.exe"
try {
    & $pythonCmd --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  + Python 3.12 found" -ForegroundColor Green
    } else {
        throw "Python 3.12 not found"
    }
} catch {
    Write-Host "  - Python 3.12 not installed!" -ForegroundColor Red
    Stop-Transcript
    exit 1
}

# Step 2: Update pip
Write-Host "[2/8] Updating pip..." -ForegroundColor Yellow
& $pythonCmd -m pip install --upgrade pip
Test-ExitCode
Write-Host "  + pip updated" -ForegroundColor Green

# Step 3: Install dependencies
Write-Host "[3/8] Installing dependencies..." -ForegroundColor Yellow
& $pythonCmd -m pip install -r requirements.txt
Test-ExitCode
& $pythonCmd -m pip install pyinstaller
Test-ExitCode
Write-Host "  + All dependencies installed" -ForegroundColor Green

# Step 3.5: Kill any running speedwatch processes
Write-Host "[3.5/8] Killing any running speedwatch processes..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.ProcessName -like "*speedwatch*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Write-Host "  + Old processes terminated" -ForegroundColor Green

# Step 4: Clean previous builds
Write-Host "[4/8] Cleaning previous builds..." -ForegroundColor Yellow

# Пытаемся удалить папки
if (Test-Path "src\dist") {
    try {
        Remove-Item -Recurse -Force "src\dist" -ErrorAction Stop
        Write-Host "  + src\dist folder removed" -ForegroundColor Green
    } catch {
        Write-Host "  - Could not remove src\dist (might be in use)" -ForegroundColor Yellow
        # Пробуем переименовать и удалить позже
        Rename-Item "src\dist" "src\dist_old" -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        Remove-Item -Recurse -Force "src\dist_old" -ErrorAction SilentlyContinue
    }
}

if (Test-Path "src\build") {
    Remove-Item -Recurse -Force "src\build" -ErrorAction SilentlyContinue
    Write-Host "  + src\build folder removed" -ForegroundColor Green
}

if (Test-Path "*.spec") {
    Remove-Item -Force "*.spec" -ErrorAction SilentlyContinue
    Write-Host "  + .spec files removed" -ForegroundColor Green
}

# Step 5: Run PyInstaller
Write-Host "[5/8] Running PyInstaller..." -ForegroundColor Yellow
Write-Host "  This may take several minutes..." -ForegroundColor Gray

Push-Location src
& $pythonCmd -m PyInstaller main.spec --clean
$buildResult = $LASTEXITCODE
Pop-Location

if ($buildResult -ne 0) {
    Write-Host "  - PyInstaller failed!" -ForegroundColor Red
    Stop-Transcript
    exit $buildResult
}
Write-Host "  + PyInstaller finished" -ForegroundColor Green

# Step 5.5: Force copy required files to dist (ПОСЛЕ того как dist создан)
Write-Host "[5.5/8] Force copying required files to dist..." -ForegroundColor Yellow

# Создаем папку dist если её вдруг нет
if (-not (Test-Path "src\dist")) {
    New-Item -ItemType Directory -Path "src\dist" -Force | Out-Null
    Write-Host "  + Created src\dist directory" -ForegroundColor Yellow
}

$requiredFiles = @(
    @{Source="src\icon.ico"; Destination="src\dist\icon.ico"},
    @{Source="src\openspeedtest-cli-fixed"; Destination="src\dist\openspeedtest-cli-fixed"}
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file.Source) {
        Copy-Item $file.Source $file.Destination -Force
        Write-Host "  + Copied $($file.Source) to dist" -ForegroundColor Green
    } else {
        Write-Host "  - Source file $($file.Source) not found!" -ForegroundColor Red
    }
}

# Проверяем результат
Write-Host "  Final dist contents:" -ForegroundColor Yellow
if (Test-Path "src\dist") {
    Get-ChildItem src\dist | ForEach-Object { Write-Host "    - $($_.Name)" }
} else {
    Write-Host "    - dist folder still not found!" -ForegroundColor Red
}

# Step 6: Check created files
Write-Host "[6/8] Checking created files..." -ForegroundColor Yellow

$exeFiles = @(
    "src\dist\speedwatch.exe",
    "src\dist\speedwatch_w.exe"
)

$allFound = $true
foreach ($file in $exeFiles) {
    if (Test-Path $file) {
        $size = (Get-Item $file).Length / 1MB
        Write-Host ("  + " + $file + " (" + [math]::Round($size, 2) + " MB)") -ForegroundColor Green
    } else {
        Write-Host ("  - " + $file + " not found!") -ForegroundColor Red
        $allFound = $false
    }
}

if (-not $allFound) {
    Write-Host "  - Not all files created!" -ForegroundColor Red
    Stop-Transcript
    exit 1
}

# Step 7: Test mode
Write-Host "[7/8] Testing speedwatch.exe (--test-mode)..." -ForegroundColor Yellow

$testOutput = & "src\dist\speedwatch.exe" --test-mode 2>&1 | Out-String

if ($LASTEXITCODE -eq 0) {
    Write-Host "  + Test mode successful" -ForegroundColor Green
    Write-Host ""
    Write-Host "Test results:" -ForegroundColor Gray
    Write-Host $testOutput -ForegroundColor Gray
} else {
    Write-Host "  - Test mode failed!" -ForegroundColor Red
    Write-Host $testOutput -ForegroundColor Red
    Stop-Transcript
    exit 1
}

# Step 8: Check tzdata in requirements.txt
Write-Host "[8/8] Checking requirements.txt for tzdata..." -ForegroundColor Yellow
if (Select-String -Path "requirements.txt" -Pattern "tzdata" -Quiet) {
    Write-Host "  + tzdata found in requirements.txt" -ForegroundColor Green
} else {
    Write-Host "  - tzdata not found! Adding..." -ForegroundColor Yellow
    Add-Content -Path "requirements.txt" -Value "`ntzdata>=2025.1"
    Write-Host "  + tzdata added to requirements.txt" -ForegroundColor Green
}

# Final message
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   BUILD SUCCESSFUL!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Files created in: src\dist\" -ForegroundColor White
Write-Host "  + speedwatch.exe     - with console (debug)" -ForegroundColor Cyan
Write-Host "  + speedwatch_w.exe   - without console (production)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Run program:" -ForegroundColor White
Write-Host "  src\dist\speedwatch_w.exe" -ForegroundColor Yellow
Write-Host ""
Write-Host "Test mode:" -ForegroundColor White
Write-Host "  src\dist\speedwatch.exe --test-mode" -ForegroundColor Yellow
Write-Host ""
Write-Host "Logs and DB saved to:" -ForegroundColor White
Write-Host "  %APPDATA%\SpeedWatch\data\" -ForegroundColor Yellow
Write-Host ""
Write-Host "Build log saved to: $logFile" -ForegroundColor Green
Stop-Transcript