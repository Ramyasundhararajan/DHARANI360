@echo off
REM DHARANI 360 - make a backup.
REM Double-click this, or point Windows Task Scheduler at it to run daily:
REM   Task Scheduler > Create Basic Task > Daily > Start a program > this file.
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe backup.py create
) else (
  python backup.py create
)
echo.
pause
