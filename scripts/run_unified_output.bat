@echo off
setlocal
for %%I in ("%~dp0\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 (
  echo ERROR: Cannot enter repository root: "%REPO_ROOT%" 1>&2
  endlocal & exit /b 1
)

set "PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" "%REPO_ROOT%\app\run_unified_output.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

endlocal & exit /b %EXIT_CODE%
