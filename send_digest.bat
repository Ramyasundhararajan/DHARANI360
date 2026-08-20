@echo off
REM DHARANI 360 - runs the compliance email digest once, then exits.
REM Point Windows Task Scheduler at this file to send it automatically
REM every morning. See README.md, "Automated compliance email reminders".
cd /d "%~dp0"
if not exist ".venv" (
    echo DHARANI 360 has not been set up yet - run start.bat once first.
    exit /b 1
)
call .venv\Scripts\activate.bat
python email_digest.py
