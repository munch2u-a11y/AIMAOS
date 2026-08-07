@echo off
title AIMAOS Desktop Workstation
echo ====================================================================
echo LAUNCHING AIMAOS ALL-IN-ONE SYSTEM ^& DASHBOARD
echo ====================================================================
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" aimaos_app.py %*
) else if exist "Alix-AI\.venv\Scripts\python.exe" (
    "Alix-AI\.venv\Scripts\python.exe" aimaos_app.py %*
) else (
    python aimaos_app.py %*
)
pause
