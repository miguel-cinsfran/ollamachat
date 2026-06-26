#!/usr/bin/env bash
# scripts/build_windows.sh
#
# Build a Windows distribution kit for Bellbird.
#
# This script runs in WSL/Linux. It does NOT build the .exe itself:
# cross-compiling Python + wxPython from Linux to Windows is fragile
# (wxPython ships Windows-only wheels that link Win32, and Wine
# emulation of wxWidgets is unreliable).
#
# Instead, this script:
#   1. Runs the automated test suite to verify the source is healthy.
#   2. Reads the version from pyproject.toml.
#   3. Copies the project source into a clean build directory, excluding
#      dev artifacts (.venv, .pytest_cache, openspec/, data/, etc.).
#   4. Writes a build.bat that the user runs on Windows to drive
#      PyInstaller.
#   5. Writes the bellbird.spec file PyInstaller consumes.
#   6. Zips the kit as dist/bellbird_v<version>_<timestamp>.zip.
#   7. Removes the build directory.
#
# Usage:
#   scripts/build_windows.sh
#   scripts/build_windows.sh --skip-tests    (skip pytest, just package)
#   scripts/build_windows.sh --help

set -euo pipefail

# --- Resolve paths --------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$ROOT/dist"

# --- Options --------------------------------------------------------------

SKIP_TESTS=0
for arg in "$@"; do
    case "$arg" in
        --skip-tests) SKIP_TESTS=1 ;;
        --help|-h)
            sed -n '2,22p' "$0"
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $arg" >&2
            echo "Run with --help for usage." >&2
            exit 1
            ;;
    esac
done

# --- Logging helpers ------------------------------------------------------

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- Pre-flight checks ----------------------------------------------------

command -v uv >/dev/null 2>&1 || die "uv not found. Install from https://github.com/astral-sh/uv"
[ -f "$ROOT/pyproject.toml" ] || die "pyproject.toml not found at $ROOT"

# --- Cleanup on exit ------------------------------------------------------

BUILD_DIR=""
cleanup() {
    if [ -n "$BUILD_DIR" ] && [ -d "$BUILD_DIR" ]; then
        rm -rf "$BUILD_DIR"
        log "Cleaned up build directory"
    fi
}
trap cleanup EXIT

# --- Step 1: Run tests ----------------------------------------------------

if [ "$SKIP_TESTS" -eq 0 ]; then
    log "Running tests (uv run --no-sync pytest -xvs)"
    (
        cd "$ROOT"
        uv run --no-sync pytest -xvs --tb=short
    ) || die "Tests failed. Use --skip-tests to bypass."
else
    warn "Skipping tests (--skip-tests)"
fi

# --- Step 2: Read version -------------------------------------------------

VERSION=$(grep -E '^version[[:space:]]*=' "$ROOT/pyproject.toml" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
[ -n "$VERSION" ] || die "Could not read version from pyproject.toml"
log "Project version: $VERSION"

# --- Step 3: Prepare build directory --------------------------------------

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$DIST_DIR"
BUILD_DIR="$DIST_DIR/bellbird_v${VERSION}_${TIMESTAMP}"

log "Copying project source to build directory"
# rsync with excludes to drop dev-only artifacts
rsync -a \
    --exclude='.venv' \
    --exclude='.pytest_cache' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.git' \
    --exclude='.atl' \
    --exclude='opencode.json' \
    --exclude='opencode.json:Zone.Identifier' \
    --exclude='openspec' \
    --exclude='build' \
    --exclude='dist' \
    --exclude='data' \
    --exclude='.coverage' \
    --exclude='htmlcov' \
    --exclude='*.egg-info' \
    --exclude='NOTAS_PARA_PROBAR.txt' \
    "$ROOT/" "$BUILD_DIR/"

# --- Step 4: Write build.bat (Windows entry point) -----------------------

log "Writing build.bat"
cat > "$BUILD_DIR/build.bat" <<'BAT_EOF'
@echo off
REM Build script for Bellbird on Windows.
REM Requires: Python 3.12+, uv, and Windows 10/11.
REM
REM Usage: double-click this file or run from cmd.exe: build.bat

setlocal EnableDelayedExpansion

echo === Bellbird Windows build ===

REM Clean previous build artifacts and cache
if exist __pycache__ rmdir /s /q __pycache__
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Prefer uv; fall back to a venv + pip if uv is not installed.
where uv >nul 2>nul
if not errorlevel 1 (
    echo Using uv to install dependencies...
    uv sync || goto :error
    echo Building executable with PyInstaller...
    uv run pyinstaller bellbird.spec --clean --noconfirm || goto :error
) else (
    echo uv not found; falling back to Python venv + pip.
    echo Install uv from https://github.com/astral-sh/uv for a faster build.
    echo.
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python not found. Install Python 3.12+ from https://www.python.org/downloads/
        goto :error
    )
    if not exist .venv\Scripts\activate.bat (
        python -m venv .venv || goto :error
    )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip || goto :error
    python -m pip install -r requirements.txt || goto :error
    python -m pip install pyinstaller || goto :error
    echo Building executable with PyInstaller...
    pyinstaller bellbird.spec --clean --noconfirm || goto :error
)

echo.
echo === Build complete ===
echo Output:  dist\Bellbird\Bellbird.exe
echo.
echo To run:  dist\Bellbird\Bellbird.exe

goto :eof

:error
echo.
echo === Build failed ===
echo See messages above. For debugging, check that Python 3.12+ is
echo installed and that you have internet access (PyInstaller needs
echo to download some files on first run).

endlocal
exit /b 1
BAT_EOF

# --- Step 4b: Write LEEME.txt (brief end-user instructions) --------------

log "Writing LEEME.txt"
cat > "$BUILD_DIR/LEEME.txt" <<LEEME_EOF
BELLBIRD v${VERSION} - Instrucciones para Windows 11
=====================================================

QUE HACER
---------

1. Descomprimi este zip en una carpeta (por ejemplo, el Escritorio).
   Se va a crear una carpeta bellbird_v${VERSION}_${TIMESTAMP}\ con todo adentro.

2. Asegurate de tener Python 3.12 o superior instalado.
   Si no lo tenes, bajalo de https://www.python.org/downloads/
   Durante la instalacion, marca la opcion "Add Python to PATH".

3. Asegurate de tener Ollama instalado y corriendo, con al menos un
   modelo descargado. Si no, bajalo de https://ollama.com/download
   y en una terminal ejecutá: ollama pull llama3.2

4. Doble click en build.bat y esperá. La primera vez tarda entre
   5 y 10 minutos porque tiene que descargar wxPython (que es pesado)
   y compilar todo. Las veces siguientes tarda segundos.

5. Cuando build.bat termina, andá a la carpeta recien creada
   dist\Bellbird\ y hace doble click en Bellbird.exe.

6. La primera vez, si Ollama no esta corriendo, te aparece un dialogo
   y la aplicacion lo anuncia por voz. Apreta el boton "Iniciar Ollama"
   que esta arriba de todo para arrancarlo. Despues F5 recarga la lista
   de modelos.

7. Para conversar: escribi en el campo de abajo y aprieta Enter.
   Shift+Enter inserta salto de linea sin enviar.

ATAJOS DE TECLADO
-----------------

- Ctrl+N: nueva conversacion
- Ctrl+O: abrir una conversacion guardada
- Ctrl+S: guardar la conversacion actual
- F5: actualizar lista de modelos
- Escape: detener la generacion de una respuesta
- Enter: enviar el mensaje
- Shift+Enter: nueva linea en el campo de entrada
- Alt+F4: cerrar la aplicacion

PROBLEMAS COMUNES
-----------------

- build.bat dice "Python no encontrado": instalá Python y reiniciá
  la terminal (o reintenta con doble click).
- La aplicacion dice "No se puede conectar a Ollama": inicia Ollama
  desde el menu inicio, o hace click en "Iniciar Ollama" arriba.
- La aplicacion se abre sin voz: instalá NVDA (gratis) o JAWS.
  accessible-output2 los detecta automaticamente.
- Cualquier otro error: revisá el archivo %LOCALAPPDATA%\\Bellbird\\data\\bellbird.log.

CONTACTO
--------

- Repo de GitHub: https://github.com/miguel-cinsfran/bellbird
- Para reportar bugs: abrir un issue en el repo.
LEEME_EOF

# --- Step 5: Write PyInstaller spec --------------------------------------

log "Writing bellbird.spec"
cat > "$BUILD_DIR/bellbird.spec" <<'SPEC_EOF'
# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Bellbird.
# Produces a one-folder (onedir) distribution under dist/Bellbird/.
# The exe is windowed (no console). Hidden imports cover libraries
# PyInstaller's static analysis sometimes misses.

block_cipher = None

a = Analysis(
    ['bellbird/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('bellbird/data/sounds/default/*.wav', 'data/sounds/default'),
    ],
    hiddenimports=[
        'wx',
        'wx.adv',
        'accessible_output2',
        'accessible_output2.outputs.auto',
        'requests',
        'markdown',
        'platformdirs',
        'gguf',
        'html.parser',
        'unicodedata',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'pydoc',
        'doctest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Bellbird',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Bellbird',
)
SPEC_EOF

# --- Step 6: Create the zip -----------------------------------------------

# The zip lives at $DIST_DIR/$ZIP_NAME. We move the build folder next to
# it under $DIST_DIR first, so the zip can reference it relatively.
# (BUILD_DIR is already under $DIST_DIR from step 3.)

ZIP_NAME="bellbird_v${VERSION}_${TIMESTAMP}.zip"
ZIP_PATH="$DIST_DIR/$ZIP_NAME"

log "Creating zip: $ZIP_PATH"
(
    cd "$DIST_DIR"
    if command -v zip >/dev/null 2>&1; then
        zip -r -q "$ZIP_NAME" "$(basename "$BUILD_DIR")"
    else
        # Fallback to Python's zipfile module if `zip` isn't installed
        python3 - "$ZIP_NAME" "$(basename "$BUILD_DIR")" <<'PYEOF'
import os
import sys
import zipfile

zip_name = sys.argv[1]
folder = sys.argv[2]
parent = os.path.dirname(folder) or "."
with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, _, files in os.walk(folder):
        for f in files:
            full = os.path.join(root, f)
            arc = os.path.relpath(full, parent)
            zf.write(full, arc)
PYEOF
    fi
)

# --- Step 7: Report -------------------------------------------------------

ZIP_SIZE=$(du -h "$ZIP_PATH" | cut -f1)
FILE_COUNT=$(unzip -l "$ZIP_PATH" 2>/dev/null | tail -1 | awk '{print $2}')

log "Build kit ready"
log "  Path:   $ZIP_PATH"
log "  Size:   $ZIP_SIZE"
log "  Files:  $FILE_COUNT"
log ""
log "Next steps:"
log "  1. Move the zip to your Windows 11 machine"
log "  2. Unzip it"
log "  3. Open the unzipped folder and double-click build.bat"
log "  4. When build.bat finishes, run dist\\Bellbird\\Bellbird.exe"
