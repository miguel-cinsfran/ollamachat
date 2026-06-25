@echo off
setlocal
cd /d "%~dp0"
set "TMPFILE=%TEMP%\bellbird_tests_%RANDOM%.txt"

echo ============================================================
echo  Bellbird — suite de tests + smoke test
echo ============================================================
echo.
echo NOTA: tests/ui/test_mainwindow_construction.py requiere wxPython
echo       (se salta automaticamente en WSL/CI via importorskip)
echo.
echo Corriendo... (puede tardar ~20 segundos)
echo.

(
    echo === PYTEST ^(tests/^) ===
    echo.
    uv run pytest tests/ -v --tb=short 2>&1
    echo.
    echo === WX-RUNTIME TESTS (chat_panel + find_dialog + main_window + message_detail_dialog) ===
    echo.
    uv run pytest tests/ui/test_chat_panel_runtime.py tests/ui/test_find_dialog.py tests/ui/test_main_window_runtime.py tests/ui/test_message_detail_dialog_runtime.py tests/ui/test_permission_dialog_runtime.py -v --tb=short 2>&1
    echo.
    echo === SMOKE TEST ^(smoke_test.py^) ===
    echo.
    uv run python smoke_test.py 2>&1
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
echo.
echo Para smoke test con UI completo (necesita pywinauto):
echo   uv run python smoke_test.py
echo.
pause
