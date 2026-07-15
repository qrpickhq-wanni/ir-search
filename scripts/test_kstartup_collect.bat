@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."

REM QRPick Phase-1: K-Startup collect smoke test
REM Does not modify skills/ir-search source. Writes dated raw + logs only.

set "LOG_DIR=logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"

set "RAW_DIR=data\raw\%TODAY%"
set "OUT_FILE=%RAW_DIR%\kstartup_all.jsonl"
set "LOG_FILE=%LOG_DIR%\%TODAY%_kstartup_test.log"

if not exist "%RAW_DIR%" mkdir "%RAW_DIR%"

echo ========================================
echo  K-Startup collect test
echo  Date   : %TODAY%
echo  Output : %OUT_FILE%
echo  Log    : %LOG_FILE%
echo ========================================

(
  echo ==== K-Startup collect test ====
  echo started: %DATE% %TIME%
  echo cwd: %CD%
  echo output: %OUT_FILE%
) > "%LOG_FILE%"

if not exist ".venv\Scripts\python.exe" (
  echo [FAIL] .venv not found. Create with: python -m venv .venv
  echo [FAIL] .venv not found >> "%LOG_FILE%"
  exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [FAIL] could not activate .venv
  echo [FAIL] activate.bat failed >> "%LOG_FILE%"
  exit /b 1
)

echo [INFO] running kstartup_crawl.py list ...
".venv\Scripts\python.exe" "skills\ir-search\scripts\kstartup_crawl.py" list -o "%OUT_FILE%" >> "%LOG_FILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
  echo [FAIL] crawl exited with code %EXITCODE%
  echo finished: %DATE% %TIME% FAIL exit=%EXITCODE% >> "%LOG_FILE%"
) else (
  echo [OK] crawl process finished
  echo finished: %DATE% %TIME% OK exit=0 >> "%LOG_FILE%"
)

if exist "%OUT_FILE%" (
  for /f %%c in ('powershell -NoProfile -Command "(Get-Content -LiteralPath '%CD%\%OUT_FILE%' -ErrorAction Stop | Measure-Object -Line).Lines"') do set "COUNT=%%c"
  echo [OK] result file exists: %OUT_FILE%
  echo [OK] item count: !COUNT!
  echo result_exists=yes >> "%LOG_FILE%"
  echo item_count=!COUNT! >> "%LOG_FILE%"
) else (
  echo [FAIL] result file missing: %OUT_FILE%
  echo result_exists=no >> "%LOG_FILE%"
  echo item_count=0 >> "%LOG_FILE%"
  if "%EXITCODE%"=="0" set "EXITCODE=2"
)

echo ========================================
echo  Done. See log: %LOG_FILE%
echo ========================================
exit /b %EXITCODE%
