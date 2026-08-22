@echo off
REM DHARANI 360 - open a preview with sample data.
REM Double-click this any time you want to see the system without touching
REM your real records. Add --fresh to rebuild the sample data.
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe preview.py %*
) else (
  python preview.py %*
)
echo.
pause
