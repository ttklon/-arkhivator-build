# -*- coding: utf-8 -*-
"""Пересоздаёт .bat-файлы в кодировке CP866 с переводами строк CRLF.

cmd.exe гарантированно разбирает однобайтовые файлы в кодировке консоли
(на русской Windows это CP866) — без смены кодировки посреди файла,
на которой паркер cmd теряет позицию и исполняет обрывки строк.
"""
import io
import os

BATS = {
    "install.bat": '''\
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
set "PY=%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe"
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
  set "PY=%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe"
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
if not exist ".venv\\Scripts\\python.exe" (
  echo Создаю изолированное окружение .venv ...
  "!PY!" -m venv .venv
)
set "VPY=.venv\\Scripts\\python.exe"
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
echo     .venv\\Scripts\\python.exe -m lektor.download_models --chatterbox
echo На NVIDIA он быстрый; на AMD и процессоре - работает, но собирает
echo аудио в 5-10 раз дольше реального времени. Основной движок - Silero.
echo.

echo ==========================================================
echo   Установка завершена.
echo   Запускайте программу двойным кликом: ЛЕКТОР.bat
echo ==========================================================
pause
''',
    "ДИАГНОСТИКА.bat": '''\
@echo off
title Лектор - самодиагностика
cd /d "%~dp0"

echo ==========================================================
echo   ЛЕКТОР: проверка установки (модули, словари, модель голоса)
echo ==========================================================
echo.

if not exist ".venv\\Scripts\\python.exe" (
  echo Не найден .venv - сначала запустите install.bat
  pause
  exit /b 1
)

".venv\\Scripts\\python.exe" -X utf8 -m lektor --doctor
echo.
pause
''',
    "ЛЕКТОР.bat": '''\
@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\\Scripts\\pythonw.exe" (
  echo Сначала запустите install.bat - он всё установит.
  pause
  exit /b 1
)
start "" ".venv\\Scripts\\pythonw.exe" "main.py"
''',
    "Озвучить файл.bat": '''\
@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Перетащите файл с текстом - .txt .docx .pdf .fb2 .epub - на этот ярлык,
  echo и рядом появится готовая аудиолекция.
  pause
  exit /b 1
)
if not exist ".venv\\Scripts\\python.exe" (
  echo Сначала запустите install.bat - он всё установит.
  pause
  exit /b 1
)
".venv\\Scripts\\python.exe" -m lektor "%~1" --open
pause
''',
}

for name, text in BATS.items():
    # страховка: только символы, существующие в CP866
    data = text.replace("\n", "\r\n").encode("cp866")
    with open(name, "wb") as f:
        f.write(data)
    # контроль: читаем обратно
    back = open(name, "rb").read().decode("cp866")
    assert back.replace("\r\n", "\n") == text, name
    print(f"{name}: {len(data)} байт, CP866 + CRLF — OK")

# проверим, что латиница/команды не задеты и нет запрещённых символов
for name in BATS:
    raw = open(name, "rb").read()
    assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r"), name
    raw.decode("cp866")  # строго
print("Все .bat пересозданы в CP866/CRLF")
