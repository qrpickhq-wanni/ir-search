@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

if not exist ".venv\Scripts\activate.bat" (
  echo [.venv] not found. Create it first: python -m venv .venv
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat

echo === MICE MVP env check ===
if defined SONGDO_OPENAPI_KEY (echo SONGDO_OPENAPI_KEY=SET) else (echo SONGDO_OPENAPI_KEY=UNSET)
if defined GG_OPENAPI_KEY (echo GG_OPENAPI_KEY=SET) else (echo GG_OPENAPI_KEY=UNSET)
if defined GG_KINTEX_OPENAPI_SERVICE (echo GG_KINTEX_OPENAPI_SERVICE=SET) else (echo GG_KINTEX_OPENAPI_SERVICE=UNSET)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i
if not exist "logs" mkdir logs
set LOG=logs\%TODAY%_mice_mvp.log

echo Logging to %LOG%
python app\run_mice_mvp.py
set EXITCODE=%ERRORLEVEL%

echo.
echo Pipeline exit code: %EXITCODE%
echo   0 = all sources OK
echo   2 = partial / some source failed
echo   1 = pipeline / test failure
echo.
pause
exit /b %EXITCODE%
