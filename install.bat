@echo off
setlocal EnableDelayedExpansion
title Лектор - установка
cd /d "%~dp0"

echo ==========================================================
echo   ЛЕКТОР: установка - один раз, нужен интернет, ~10 минут
echo   Дальше программа будет работать полностью офлайн
echo ==========================================================
echo.

REM ---------- Python ----------
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "!PY!" (
  where python >nul 2>nul
  if not errorlevel 1 (
    rem пропускаем заглушку Microsoft Store из WindowsApps
    for /f "delims=" %%i in ('where python') do (
      echo %%i | findstr /I "WindowsApps" >nul || if not exist "!PY!" set "PY=%%i"
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
  echo Установите Python 3.11 с сайта python.org/downloads/ и запустите install.bat снова.
  echo ВАЖНО: при установке отметьте галочку Add python.exe to PATH.
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

REM ---------- PyTorch: ускорение только для NVIDIA; для AMD и Intel - CPU ----------
for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name" 2^>nul') do echo Найдена видеокарта: %%i
nvidia-smi >nul 2>nul
if not errorlevel 1 (
  echo Видеокарта NVIDIA: ставлю PyTorch с ускорением, ~2.5 ГБ
  "!VPY!" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
) else (
  echo Видеокарта не NVIDIA - это AMD или Intel, либо её нет.
  echo Для них ускорение PyTorch недоступно: ставлю компактный CPU-вариант.
  echo Не страшно: движок Silero отлично и быстро работает на процессоре.
  "!VPY!" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
)
if errorlevel 1 (
  echo.
  echo Не удалось установить PyTorch. Проверьте интернет и запустите install.bat снова.
  pause
  exit /b 1
)

echo.
echo Устанавливаю библиотеки обработки текста и аудио...
"!VPY!" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Ошибка установки библиотек. Проверьте интернет и запустите install.bat снова.
  pause
  exit /b 1
)

echo.
echo Скачиваю голосовую модель Silero, ~130 МБ, лицензия MIT, 29 голосов ...
"!VPY!" -m lektor.download_models
echo.
echo Дополнительный HD-голос Chatterbox - по желанию, командой:
echo     .venv\Scripts\python.exe -m lektor.download_models --chatterbox
echo На NVIDIA он быстрый; на AMD и процессоре - работает, но собирает
echo аудио в 5-10 раз дольше реального времени. Основной движок - Silero.
echo.

echo ==========================================================
echo   Установка завершена.
echo   Запускайте программу двойным кликом: ЛЕКТОР.bat
echo ==========================================================
pause
