@echo off
title Лектор - самодиагностика
cd /d "%~dp0"

echo ==========================================================
echo   ЛЕКТОР: проверка установки (модули, словари, модель голоса)
echo ==========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Не найден .venv - сначала запустите install.bat
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -X utf8 -m lektor --doctor
echo.
pause
