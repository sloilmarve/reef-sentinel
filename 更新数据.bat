@echo off
rem ---------------------------------------------------------------------------
rem This file is deliberately ASCII-only. See the preview .bat for the reason:
rem cmd.exe loses sync on UTF-8 bytes after "chcp 65001". The Chinese banner and
rem all logic live in tools\launch.ps1 (UTF-8 with BOM).
rem ---------------------------------------------------------------------------
chcp 65001 >nul
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\launch.ps1" -Mode refresh
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
