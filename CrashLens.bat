@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CrashLens

rem  Double-click this file to start CrashLens.
rem  The first start sets everything up (1-3 minutes). After that it opens right away.

set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "VPYW=%VENV%\Scripts\pythonw.exe"

if exist "%VPYW%" goto check

set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

echo.
echo  Setting up CrashLens for the first time.
echo  This takes 1-3 minutes and only happens once. Please wait...
echo.
%PY% -m venv "%VENV%"
if errorlevel 1 goto fail
"%VPY%" -m pip install --disable-pip-version-check -q -e ".[gui]"
if errorlevel 1 goto fail

:check
"%VPY%" -c "import crashlens.gui.app" >nul 2>nul
if errorlevel 1 (
  echo  Finishing the CrashLens setup, please wait...
  "%VPY%" -m pip install --disable-pip-version-check -q -e ".[gui]"
  if errorlevel 1 goto fail
)
start "" "%VPYW%" -m crashlens %*
exit /b 0

:nopython
echo.
echo  CrashLens needs Python, which is not installed on this PC yet.
echo.
choice /c YN /m " Install Python 3.12 now"
if errorlevel 2 goto manual
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto manual
echo.
echo  Python is installed. Close this window and double-click CrashLens.bat again.
echo.
pause
exit /b 0

:manual
echo.
echo  Opening the Python download page. Install Python, tick "Add python.exe to PATH",
echo  then double-click CrashLens.bat again.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:fail
echo.
echo  Setup did not finish. Check your internet connection and try again.
echo  If it keeps failing, send a screenshot of this window.
echo.
pause
exit /b 1
