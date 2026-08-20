@echo off
REM DHARANI 360 - one-time sign-in setup. Run this after filling in
REM supabase_config.json. See SUPABASE_SETUP.md.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" setup_signin.py %*
) else (
    python setup_signin.py %*
)
echo.
pause
