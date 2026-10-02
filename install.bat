@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Лектор — установка
cd /d "%~dp0"

echo ==========================================================
echo   ЛЕКТОР: установка (один раз, нужен интернет, ~10 минут)
echo   Дальше программа будет работать полностью офлайн
echo ==========================================================
echo.

REM ---------- Python ----------
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "!PY!" (
  where python >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%i in ('where python') do (
      if not exist "!PY!" set "PY=%%i"
    )
  )
)
if not exist "!PY!" (
  where py >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%i in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%i"
  )
)
if not exist "!PY!" (
  echo Python не найден. Устанавливаю Python 3.11 через winget...
  winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
  set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)
if not exist "!PY!" (
  echo.
  echo Не удалось найти или установить Python.
  echo Установите Python 3.11 с https://www.python.org/downloads/ и запустите install.bat снова.
  echo ВАЖНО: при установке отметьте галочку "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Использую Python: !PY!
echo.

REM ---------- виртуальное окружение ----------
if not exist ".venv\Scripts\python.exe" (
  echo Создаю изолированное окружение .venv ...
  "!PY!" -m venv .venv
)
set "VPY=.venv\Scripts\python.exe"
if not exist "!VPY!" (
  echo Не удалось создать окружение. Проверьте, что Python установлен корректно.
  pause
  exit /b 1
)

"!VPY!" -m pip install --upgrade pip

REM ---------- PyTorch: с ускорением NVIDIA или компактный ----------
nvidia-smi >nul 2>nul
if not errorlevel 1 (
  echo Найдена видеокарта NVIDIA: ставлю PyTorch с ускорением ^(~2.5 ГБ^)
  "!VPY!" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
) else (
  echo Видеокарты NVIDIA не найдено: ставлю компактный CPU-вариант PyTorch
  "!VPY!" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
)
if errorlevel 1 (
  echo Не удалось установить PyTorch. Проверьте интернет и запустите install.bat снова.
  pause
  exit /b 1
)

echo.
echo Устанавливаю библиотеки обработки текста и аудио...
"!VPY!" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Ошибка установки библиотек. Проверьте интернет и запустите install.bat снова.
  pause
  exit /b 1
)

echo.
echo Скачиваю голосовую модель Silero ^(~130 МБ, лицензия MIT, 29 голосов^)...
"!VPY!" -m lektor.download_models
echo.
echo Если у вас видеокарта NVIDIA и вы хотите самый живой голос HD,
echo запустите один раз:  .venv\Scripts\python.exe -m lektor.download_models --chatterbox
echo.

echo ==========================================================
echo   Установка завершена.
echo   Запускайте программу двойным кликом: ЛЕКТОР.bat
echo ==========================================================
pause
