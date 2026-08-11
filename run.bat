@echo off
rem ASCII only, deliberately. cmd.exe miscomputes where to resume reading a
rem batch file that contains multi-byte characters, so every Chinese message
rem lives in scripts\*.txt and is printed with `type` -- bytes the batch
rem parser never sees.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem A polluted PYTHONPATH makes uv import packages from outside the project.
set "PYTHONPATH="

if exist "frontend\dist\index.html" goto serve

where npm >nul 2>nul
if errorlevel 1 goto nonode
call npm install
if errorlevel 1 goto failed
call npm run build
if errorlevel 1 goto failed

:serve
call uv sync
if errorlevel 1 goto failed
type "scripts\run-ready.txt"
call uv run externaltranslate-serve
goto :eof

:nonode
type "scripts\run-no-node.txt"
pause
exit /b 1

:failed
type "scripts\run-failed.txt"
pause
exit /b 1
