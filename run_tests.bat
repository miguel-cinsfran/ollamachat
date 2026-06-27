@echo off
setlocal
cd /d "%~dp0"
REM Thin launcher. Real logic lives in scripts\run_tests.ps1, which runs each
REM test directory in its own pytest process (single-process runs hang ~70% on
REM accumulated wx state) and streams output live instead of buffering it.
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_tests.ps1"
if errorlevel 1 (
    echo.
    echo *** Hubo fallos. Revisa la salida de arriba. ***
)
echo.
pause
