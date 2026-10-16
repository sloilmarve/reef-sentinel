@echo off
chcp 65001 >nul
title 珊瑚哨兵 Reef Sentinel - 本地预览
setlocal
rem 解释器查找顺序：py 启动器（Windows 官方安装自带）-> PATH 里的 python -> python3
set "PY="
for /f "delims=" %%i in ('where py 2^>nul') do set "PY=py"
if not defined PY for /f "delims=" %%i in ('where python 2^>nul') do set "PY=python"
if not defined PY for /f "delims=" %%i in ('where python3 2^>nul') do set "PY=python3"
if not defined PY (
  echo  没有找到 Python。请安装 Python 3.10 以上版本，或直接双击 demo\index.html 查看成品页（无需 Python）。
  pause
  exit /b 1
)
echo.
echo  ============================================================
echo    珊瑚哨兵 Reef Sentinel  -  仙本那珊瑚礁气候预警台
echo  ============================================================
echo    预览地址 : http://127.0.0.1:8788/
echo    数据窗口 : 2022-11-01  到  2026-10-15  （1445 天）
echo    项目目录 : %~dp0
echo  ------------------------------------------------------------
echo    正在启动本地服务器，2 秒后自动打开浏览器……
echo    看完后关闭这个窗口即可停止服务。
echo  ============================================================
echo.
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8788/'"
"%PY%" -m http.server 8788 --bind 127.0.0.1 --directory "%~dp0demo"
echo.
echo  服务已停止。
pause
