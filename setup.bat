@echo off
REM ---------------------------------------------------------------
REM  LineupMaster setup - run this once on each new PC.
REM
REM  Keep this file ASCII-only. cmd.exe parses .bat with the system
REM  codepage (not UTF-8), so Thai text on executed lines corrupts the
REM  parser and can run the wrong command. All Thai messages live in
REM  tools\setup.py instead.
REM ---------------------------------------------------------------
chcp 65001 >nul
cd /d "%~dp0"

set "PYCMD="
py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD (
    python --version >nul 2>&1 && set "PYCMD=python"
)
if not defined PYCMD goto :nopython

set PYTHONUTF8=1
%PYCMD% "%~dp0tools\setup.py"
pause
exit /b

:nopython
echo.
echo [x] Python not found on this PC.
echo.
echo     Download it from https://www.python.org/downloads/
echo     During install, TICK "Add python.exe to PATH".
echo     Then run setup.bat again.
echo.
pause
