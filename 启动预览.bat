@echo off
rem ---------------------------------------------------------------------------
rem This file is deliberately ASCII-only.
rem cmd.exe reads batch files by byte offset; after "chcp 65001" a UTF-8
rem multi-byte character that straddles the read buffer makes it lose sync and
rem split a line in half -- round 48 measured a stray "is not recognized as an
rem internal or external command" line printed in the console. UTF-8 with a BOM
rem fails the same way, and GBK would break the UTF-8 rule for text files.
rem All Chinese text and all logic therefore live in tools\launch.ps1
rem (UTF-8 with BOM), which this file only calls.
rem ---------------------------------------------------------------------------
chcp 65001 >nul
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\launch.ps1" -Mode preview
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
