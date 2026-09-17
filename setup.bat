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

REM Prefer Python 3.12 specifically: the "winsdk" package (Windows OCR for the
REM zone-name locate feature) only ships prebuilt wheels up to 3.12. Falls back
REM to whatever "python" resolves to if 3.12 isn't installed (setup.py warns).
set "PYCMD="
py -3.12 --version >nul 2>&1 && set "PYCMD=py -3.12"
if not defined PYCMD (
    py -3 --version >nul 2>&1 && set "PYCMD=py -3"
)
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
