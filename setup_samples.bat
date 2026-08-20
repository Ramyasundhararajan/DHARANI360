@echo off
REM ===================================================================
REM  DHARANI 360 - sample data for Chat and Calls
REM  Loads sample chat messages and client call records.
REM  Close the DHARANI 360 app before running this.
REM  Safe to run more than once - anyone already there is skipped.
REM ===================================================================
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" setup_samples.py
) else (
    python setup_samples.py
)

echo.
pause
