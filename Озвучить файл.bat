@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo ������ 䠩� � ⥪�⮬ - .txt .docx .pdf .fb2 .epub - �� ��� ���,
  echo � �冷� ����� ��⮢�� �㤨������.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo ���砫� ������� install.bat - �� ��� ��⠭����.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m lektor "%~1" --open
pause
