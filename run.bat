@echo off
setlocal
cd /d "%~dp0"
rem A polluted PYTHONPATH makes uv import packages from outside the project.
set "PYTHONPATH="

if exist "frontend\dist\index.html" goto serve

echo 前端尚未建置。
where npm >nul 2>nul
if errorlevel 1 (
    echo.
    echo 這台機器沒有 npm，兩個選擇：
    echo   1. 安裝 Node.js 後重新執行本檔
    echo   2. 在有 Node 的機器上執行 npm install 與 npm run build，
    echo      再把整個 frontend\dist 資料夾複製到這台的相同位置
    echo.
    pause
    exit /b 1
)
call npm install
if errorlevel 1 goto failed
call npm run build
if errorlevel 1 goto failed

:serve
call uv sync
if errorlevel 1 goto failed
echo.
echo   控制台： http://127.0.0.1:8765/
echo   字幕頁： http://127.0.0.1:8765/overlay
echo.
echo   關閉這個視窗就會停止服務。
echo.
call uv run externaltranslate-serve
goto :eof

:failed
echo.
echo 啟動失敗，請看上面的訊息。
pause
exit /b 1
