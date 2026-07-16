@echo off
setlocal
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app\run_g2b_mice_mvp.py %*
) else (
  python app\run_g2b_mice_mvp.py %*
)
endlocal
