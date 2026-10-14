@echo off
title DHARANI 360
cd /d "%~dp0"

echo Checking for Python...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo Python was not found on this computer.
    echo Please install Python from https://www.python.org/downloads/
    echo During installation, make sure to check "Add python.exe to PATH".
    echo Then run this file again.
    echo.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Setting up DHARANI 360 for the first time - this only happens once...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing/checking requirements...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo Starting DHARANI 360...
echo Your browser will open automatically. If it doesn't, go to http://127.0.0.1:5000
echo.
echo Keep this window open while you are using DHARANI 360.
echo Close this window (or press Ctrl+C) to stop the system.
echo.

REM Wait until the server is actually listening before opening the browser.
REM Opening it immediately shows "localhost refused to connect" on the first
REM run, because pip install has not finished yet.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "$n=0; while($n -lt 180){ try { $t=New-Object Net.Sockets.TcpClient; $t.Connect('127.0.0.1',5000); $t.Close(); Start-Process 'http://127.0.0.1:5000'; break } catch { Start-Sleep -Seconds 2; $n++ } }"
python app.py

pause
