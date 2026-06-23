@echo off
setlocal
cd /d "%~dp0"
set "TMPFILE=%TEMP%\bellbird_tests_%RANDOM%.txt"

echo ============================================================
echo  Bellbird — suite de tests + smoke test
echo ============================================================
echo.
echo Corriendo... (puede tardar ~20 segundos)
echo.

(
    echo === PYTEST ^(tests/^) ===
    echo.
    uv run pytest tests/ -v --tb=short 2>&1
    echo.
    echo === SMOKE TEST ^(smoke_test.py --no-gui^) ===
    echo.
    uv run python smoke_test.py --no-gui 2>&1
) > "%TMPFILE%"

echo.
type "%TMPFILE%"
echo.

powershell -NoProfile -Command "Get-Content '%TMPFILE%' -Encoding UTF8 | Set-Clipboard"
echo ============================================================
echo  Resultado copiado al portapapeles. Pega con Ctrl+V.
echo ============================================================
echo.
del "%TMPFILE%"
pause
