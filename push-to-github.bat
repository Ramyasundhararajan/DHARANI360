@echo off
title DHARANI 360 - push to GitHub
cd /d "%~dp0"

echo.
echo  ================================================================
echo   DHARANI 360  -  push the code to your private GitHub repository
echo  ================================================================
echo.

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo  Git is not installed on this computer.
    echo  Download it from https://git-scm.com/download/win
    echo  Install it, then run this file again.
    echo.
    pause
    exit /b 1
)

REM Tidy up any leftover lock or temp files from the initial setup.
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>nul
git gc --prune=now --quiet >nul 2>nul

echo  Files that will be sent:
git ls-files --cached | find /c /v "" 
echo.
echo  Files deliberately NOT sent: the database, every attachment and
echo  staff photo, your Supabase keys, and dashboard.mp4.
echo.

git rev-parse HEAD >nul 2>nul
if %errorlevel% neq 0 (
    echo  Making the first commit...
    git commit -q -m "DHARANI 360 - initial commit"
    if %errorlevel% neq 0 (
        echo  Commit failed. Read the message above.
        pause
        exit /b 1
    )
    echo  Done.
) else (
    echo  Saving any changes since the last time...
    git add -A
    git commit -q -m "Update" 2>nul
)

git branch -M main

git remote get-url origin >nul 2>nul
if %errorlevel% neq 0 (
    git remote add origin https://github.com/Ramyasundhararajan/DHARANI360.git
)

echo.
echo  Pushing. A GitHub sign-in window may appear - sign in there.
echo.
git push -u origin main
if %errorlevel% neq 0 (
    echo.
    echo  The push did not complete. The message above says why.
    echo  Most common cause: the repository name or username is wrong.
    echo  To change it:   git remote set-url origin https://github.com/USER/REPO.git
    echo.
    pause
    exit /b 1
)

echo.
echo  ================================================================
echo   Done. Your code is on GitHub, privately.
echo   Run this file again any time you want to save new changes.
echo  ================================================================
echo.
pause
