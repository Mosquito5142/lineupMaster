@echo off
REM ---------------------------------------------------------------
REM  Start LineupMaster (closing this console window quits the app).
REM
REM  Keep this file ASCII-only - cmd.exe parses .bat with the system
REM  codepage, not UTF-8, so Thai text on executed lines breaks it.
REM ---------------------------------------------------------------
chcp 65001 >nul
cd /d "%~dp0"

REM .venv cannot be copied between PCs - it stores the full path of the
REM Python it was built from. Check it actually runs before using it.
if not exist ".venv\Scripts\python.exe" goto :needsetup
".venv\Scripts\python.exe" -c "pass" >nul 2>&1
if errorlevel 1 goto :needsetup

set PYTHONPATH=%~dp0src
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m lineupmaster %*
pause
exit /b

:needsetup
echo.
echo  [x] Not installed on this PC yet
echo      (or .venv was copied from another PC - that never works).
echo.
echo      Fix: double-click  setup.bat  once, then run this again.
echo.
pause
