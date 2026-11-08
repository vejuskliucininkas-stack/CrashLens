@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CrashLens

rem  Double-click this file to start CrashLens.
rem  The first start sets everything up (1-3 minutes). After that it opens right away.

set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "VPYW=%VENV%\Scripts\pythonw.exe"
set "READY=%VENV%\crashlens-ready.txt"
set "LOG=%~dp0setup-log.txt"

if exist "%READY%" goto launch

rem ---------------------------------------------------------------- find Python
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

echo.
echo  Setting up CrashLens for the first time.
echo  This takes 1-3 minutes and only happens once. Please wait...
echo.
echo CrashLens setup log > "%LOG%"
%PY% --version >> "%LOG%" 2>&1

rem  Remove an unfinished setup from an earlier attempt. This folder belongs to CrashLens.
if exist "%VENV%" rmdir /s /q "%VENV%"

rem ---------------------------------------------------------------- method 1
echo [method 1] >> "%LOG%"
%PY% -m venv "%VENV%" >> "%LOG%" 2>&1
if errorlevel 1 goto method2
"%VPY%" -m pip install --disable-pip-version-check -e ".[gui]" >> "%LOG%" 2>&1
if errorlevel 1 goto method2
goto verify

rem ---------------------------------------------------------------- method 2
:method2
echo  The usual setup did not work on this PC. Trying another way...
echo [method 2] >> "%LOG%"
if exist "%VENV%" rmdir /s /q "%VENV%"
%PY% -m venv --without-pip "%VENV%" >> "%LOG%" 2>&1
if errorlevel 1 goto fail
%PY% -m pip --version >> "%LOG%" 2>&1
if errorlevel 1 goto nopip
%PY% -m pip install --disable-pip-version-check --target "%VENV%\Lib\site-packages" ".[gui]" >> "%LOG%" 2>&1
if errorlevel 1 goto fail

rem ---------------------------------------------------------------- check and start
:verify
"%VPY%" -c "import crashlens.gui.app" >> "%LOG%" 2>&1
if errorlevel 1 goto fail
echo ready> "%READY%"
echo  Done.

:launch
start "" "%VPYW%" -m crashlens %*
exit /b 0

rem ---------------------------------------------------------------- problems
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

:nopip
echo.
echo  Your Python installation is missing parts CrashLens needs to set itself up.
echo  Please reinstall Python from python.org - the download page opens now.
echo  During setup tick "Add python.exe to PATH", then double-click CrashLens.bat again.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:manual
echo.
echo  Opening the Python download page. Install Python, tick "Add python.exe to PATH",
echo  then double-click CrashLens.bat again.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:fail
echo.
echo  Setup did not finish. The details are below and saved in setup-log.txt.
echo  Please send a screenshot of this window or the setup-log.txt file.
echo  ------------------------------------------------------------------------
type "%LOG%"
echo  ------------------------------------------------------------------------
pause
exit /b 1
