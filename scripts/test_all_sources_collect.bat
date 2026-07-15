@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."

REM QRPick Phase-1: multi-source collect smoke test (bizinfo/NIPA/KOCCA/SMTECH)
REM Does not modify skills/ir-search source. Writes dated raw + logs only.

set "LOG_DIR=logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"

set "RAW_DIR=data\raw\%TODAY%"
set "OUT_FILE=%RAW_DIR%\sources_all.jsonl"
set "LOG_FILE=%LOG_DIR%\%TODAY%_sources_test.log"

if not exist "%RAW_DIR%" mkdir "%RAW_DIR%"

echo ========================================
echo  All sources collect test
echo  Date   : %TODAY%
echo  Output : %OUT_FILE%
echo  Log    : %LOG_FILE%
echo ========================================

(
  echo ==== All sources collect test ====
  echo started: %DATE% %TIME%
  echo cwd: %CD%
  echo output: %OUT_FILE%
  echo command: sources_crawl.py list all
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

echo [INFO] running sources_crawl.py list all ...
".venv\Scripts\python.exe" "skills\ir-search\scripts\sources_crawl.py" list all -o "%OUT_FILE%" >> "%LOG_FILE%" 2>&1
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

  REM Per-source counts (best-effort; does not alter raw file)
  ".venv\Scripts\python.exe" -c "import json,collections; from pathlib import Path; p=Path(r'%OUT_FILE%'); c=collections.Counter(json.loads(l).get('source','?') for l in p.read_text(encoding='utf-8').splitlines() if l.strip()); print('per_source:', dict(c))" >> "%LOG_FILE%" 2>&1
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
