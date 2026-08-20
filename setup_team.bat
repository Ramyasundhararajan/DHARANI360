@echo off
REM ===================================================================
REM  DHARANI 360 - one-time team setup
REM  Adds the five staff members as login accounts + employee files.
REM  Close the DHARANI 360 app before running this.
REM  Safe to run more than once - anyone already there is skipped.
REM ===================================================================
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" setup_team.py
) else (
    python setup_team.py
)

echo.
pause
