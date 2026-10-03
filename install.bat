@echo off
setlocal EnableDelayedExpansion
title ����� - ��⠭����
cd /d "%~dp0"

echo ==========================================================
echo   ������: ��⠭���� - ���� ࠧ, �㦥� ���୥�, ~10 �����
echo   ����� �ணࠬ�� �㤥� ࠡ���� ��������� �䫠��
echo ==========================================================
echo.

REM ---------- Python ----------
set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "!PY!" (
  where python >nul 2>nul
  if not errorlevel 1 (
    rem �ய�᪠�� ������� Microsoft Store �� WindowsApps
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
  echo Python �� ������. ��⠭������� Python 3.11 �१ winget...
  winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
  set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)
if not exist "!PY!" (
  echo.
  echo �� 㤠���� ���� ��� ��⠭����� Python.
  echo ��⠭���� Python 3.11 � ᠩ� python.org/downloads/ � ������� install.bat ᭮��.
  echo �����: �� ��⠭���� �⬥��� ������ Add python.exe to PATH.
  pause
  exit /b 1
)
echo �ᯮ���� Python: !PY!
echo.

REM ---------- ����㠫쭮� ���㦥��� ----------
if not exist ".venv\Scripts\python.exe" (
  echo ������ �����஢����� ���㦥��� .venv ...
  "!PY!" -m venv .venv
)
set "VPY=.venv\Scripts\python.exe"
if not exist "!VPY!" (
  echo �� 㤠���� ᮧ���� ���㦥���. �஢����, �� Python ��⠭����� ���४⭮.
  pause
  exit /b 1
)

"!VPY!" -m pip install --upgrade pip

REM ---------- PyTorch: �᪮७�� ⮫쪮 ��� NVIDIA; ��� AMD � Intel - CPU ----------
for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name" 2^>nul') do echo ������� ���������: %%i
nvidia-smi >nul 2>nul
if not errorlevel 1 (
  echo ��������� NVIDIA: �⠢�� PyTorch � �᪮७���, ~2.5 ��
  "!VPY!" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
) else (
  echo ��������� �� NVIDIA - �� AMD ��� Intel, ���� �� ���.
  echo ��� ��� �᪮७�� PyTorch ������㯭�: �⠢�� �������� CPU-��ਠ��.
  echo �� ���譮: ������ Silero �⫨筮 � ����� ࠡ�⠥� �� ������.
  "!VPY!" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
)
if errorlevel 1 (
  echo.
  echo �� 㤠���� ��⠭����� PyTorch. �஢���� ���୥� � ������� install.bat ᭮��.
  pause
  exit /b 1
)

echo.
echo ��⠭������� ������⥪� ��ࠡ�⪨ ⥪�� � �㤨�...
"!VPY!" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo �訡�� ��⠭���� ������⥪. �஢���� ���୥� � ������� install.bat ᭮��.
  pause
  exit /b 1
)

echo.
echo ���稢�� ����ᮢ�� ������ Silero, ~130 ��, ��業��� MIT, 29 ����ᮢ ...
"!VPY!" -m lektor.download_models
echo.
echo �������⥫�� HD-����� Chatterbox - �� �������, ��������:
echo     .venv\Scripts\python.exe -m lektor.download_models --chatterbox
echo �� NVIDIA �� ������; �� AMD � ������ - ࠡ�⠥�, �� ᮡ�ࠥ�
echo �㤨� � 5-10 ࠧ ����� ॠ�쭮�� �६���. �᭮���� ������ - Silero.
echo.

echo ==========================================================
echo   ��⠭���� �����襭�.
echo   ����᪠�� �ணࠬ�� ������ ������: ������.bat
echo ==========================================================
pause
