@echo off
chcp 65001 >nul
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
echo  珊瑚哨兵 Reef Sentinel - 一键刷新（重新取数并重画成品页）
echo  ------------------------------------------------------------
echo  这一步会访问 Open-Meteo 公开 API 取最新数据，然后重算指标与模型，
echo  最后重画 demo\index.html。全程约 1 到 3 分钟，请勿关闭本窗口。
echo.
"%PY%" "%~dp0pipeline\refresh.py"
echo.
echo  刷新结束。成品页：%~dp0demo\index.html
echo  直接双击该文件即可查看最新版本，或运行 启动预览.bat 在浏览器里看。
echo.
pause
