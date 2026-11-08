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
set "SETUPTEMP=%~dp0.setup-temp"

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

rem  Keep all setup files next to CrashLens instead of on drive C: (which may be full).
rem  These settings only apply inside this window.
if not exist "%SETUPTEMP%" mkdir "%SETUPTEMP%"
set "TEMP=%SETUPTEMP%"
set "TMP=%SETUPTEMP%"
set "PIP_NO_CACHE_DIR=1"
set "PIPFLAGS=--disable-pip-version-check --no-cache-dir"

rem  Remove an unfinished setup from an earlier attempt. This folder belongs to CrashLens.
if exist "%VENV%" rmdir /s /q "%VENV%"

rem ---------------------------------------------------------------- method 1
echo [method 1] >> "%LOG%"
%PY% -m venv "%VENV%" >> "%LOG%" 2>&1
if errorlevel 1 goto method2
"%VPY%" -m pip install %PIPFLAGS% -e ".[gui]" >> "%LOG%" 2>&1
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
%PY% -m pip install %PIPFLAGS% --target "%VENV%\Lib\site-packages" ".[gui]" >> "%LOG%" 2>&1
if errorlevel 1 goto fail

rem ---------------------------------------------------------------- check and start
:verify
"%VPY%" -c "import crashlens.gui.app" >> "%LOG%" 2>&1
if errorlevel 1 goto fail
echo ready> "%READY%"
if exist "%SETUPTEMP%" rmdir /s /q "%SETUPTEMP%"
echo  Done.

:launch
start "" "%VPYW%" -m crashlens %*
exit /b 0

rem ---------------------------------------------------------------- problems
:nospace
echo  A drive is full - there is not enough free space to finish the setup.
echo  This is usually drive C:. Free up at least 2 GB there, for example with
echo  Settings - System - Storage - Temporary files, or by emptying the Recycle Bin.
echo  Then double-click CrashLens.bat again.
echo.
echo  Full details are saved in setup-log.txt.
pause
exit /b 1

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
if exist "%SETUPTEMP%" rmdir /s /q "%SETUPTEMP%"
echo.
findstr /c:"No space left" "%LOG%" >nul 2>nul
if not errorlevel 1 goto nospace
echo  Setup did not finish. The details are below and saved in setup-log.txt.
echo  Please send a screenshot of this window or the setup-log.txt file.
echo  ------------------------------------------------------------------------
type "%LOG%"
echo  ------------------------------------------------------------------------
pause
exit /b 1
