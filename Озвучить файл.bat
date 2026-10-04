@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Перетащите файл с текстом - .txt .docx .pdf .fb2 .epub - на этот ярлык,
  echo и рядом появится готовая аудиолекция.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите install.bat - он всё установит.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m lektor "%~1" --open
pause
