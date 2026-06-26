@echo off
setlocal
cd /d "%~dp0"
set "TMPFILE=%TEMP%\bellbird_tests_%RANDOM%.txt"

echo ============================================================
echo  Bellbird — suite de tests + smoke test
echo ============================================================
echo.
echo NOTA: Los tests *_runtime.py se saltan automaticamente en WSL/CI
echo       via pytest.importorskip("wx").
echo.
echo Corriendo... (puede tardar ~20 segundos)
echo.

REM === WX-RUNTIME FILES (documentation only — pytest tests/ covers all) ===
REM These files use pytest.importorskip("wx") and are skipped on WSL:
REM
REM   test_chat_panel_runtime.py
REM   test_find_dialog.py
REM   test_main_window_runtime.py
REM   test_url_dialog.py
REM   test_message_detail_dialog_runtime.py
REM   test_permission_dialog_runtime.py
REM   test_server_watchdog.py
REM   test_mainwindow_construction.py
REM   test_keymap_accelerator.py
REM   test_keymap_capture.py
REM   test_chat_quick_actions.py
REM   test_wx_notifier_runtime.py
REM   test_preferences_dialog_runtime.py
REM   test_voice_dialog_runtime.py
REM   test_lectura_tab_runtime.py
REM   test_system_voice_runtime.py

(
    echo === PYTEST ^(tests/^) ===
    echo.
    uv run pytest tests/ -v --tb=short 2>&1
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
