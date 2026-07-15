@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."

REM Phase-2: normalize + rule filter + reports (does not modify skills/ir-search or data/raw)

set "LOG_DIR=logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"
set "LOG_FILE=%LOG_DIR%\%TODAY%_phase2.log"

echo ========================================
echo  QRPick Phase-2 pipeline
echo  Date : %TODAY%
echo  Log  : %LOG_FILE%
echo ========================================

(
  echo ==== Phase-2 pipeline ====
  echo started: %DATE% %TIME%
  echo cwd: %CD%
) > "%LOG_FILE%"

if not exist ".venv\Scripts\python.exe" (
  echo [FAIL] .venv not found
  echo [FAIL] .venv not found >> "%LOG_FILE%"
  pause
  exit /b 1
)

REM Pick latest data\raw\YYYY-MM-DD
set "RAW_DIR="
for /f "delims=" %%d in ('powershell -NoProfile -Command "Get-ChildItem -Directory 'data\raw' | Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } | Sort-Object Name | Select-Object -Last 1 -ExpandProperty FullName"') do set "RAW_DIR=%%d"

if not defined RAW_DIR (
  echo [FAIL] no dated folder under data\raw
  echo [FAIL] no dated raw folder >> "%LOG_FILE%"
  pause
  exit /b 1
)

if not exist "%RAW_DIR%\kstartup_all.jsonl" (
  echo [FAIL] missing "%RAW_DIR%\kstartup_all.jsonl"
  echo [FAIL] missing kstartup_all.jsonl >> "%LOG_FILE%"
  pause
  exit /b 1
)
if not exist "%RAW_DIR%\sources_all.jsonl" (
  echo [FAIL] missing "%RAW_DIR%\sources_all.jsonl"
  echo [FAIL] missing sources_all.jsonl >> "%LOG_FILE%"
  pause
  exit /b 1
)

echo [INFO] raw_dir=%RAW_DIR%
echo raw_dir=%RAW_DIR% >> "%LOG_FILE%"

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [FAIL] activate.bat
  echo [FAIL] activate >> "%LOG_FILE%"
  pause
  exit /b 1
)

REM Ensure PyYAML available
".venv\Scripts\python.exe" -c "import yaml" 1>nul 2>nul
if errorlevel 1 (
  echo [INFO] installing requirements...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOG_FILE%" 2>&1
)

set "STATS_JSON=data\normalized\%TODAY%\phase2_result.json"
".venv\Scripts\python.exe" "app\run_phase2.py" --raw-dir "%RAW_DIR%" --today "%TODAY%" --json-out "%STATS_JSON%" >> "%LOG_FILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
  echo [FAIL] phase2 exit=%EXITCODE%
  echo finished FAIL exit=%EXITCODE% >> "%LOG_FILE%"
  type "%LOG_FILE%"
  pause
  exit /b %EXITCODE%
)

echo [OK] phase2 finished
echo finished OK >> "%LOG_FILE%"
echo.
echo --- Result excerpt ---
".venv\Scripts\python.exe" -c "import json; from pathlib import Path; p=Path(r'%STATS_JSON%'); d=json.loads(p.read_text(encoding='utf-8')); n=d['normalize']; print('input_total', n['input_total']); print('representative_count', n['representative_count']); print('auto_merge_groups', n['auto_merge_groups']); print('error_count', n['error_count']); print('status_counts', d.get('status_counts')); print('report_dir', d.get('report_dir'))"

echo.
echo Log: %LOG_FILE%
echo Report: reports\%TODAY%\collection-summary.md
echo ========================================
pause
exit /b 0
