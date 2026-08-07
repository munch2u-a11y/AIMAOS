@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch AIMAOS.ps1"
exit /b %ERRORLEVEL%
