#!/usr/bin/env python
"""Smoke test y verificación de accesibilidad de Bellbird.

Tres fases, cada una se ejecuta solo si el entorno la permite:

  Fase 1  (cualquier SO):   importa los módulos de lógica pura (core/).
  Fase 2  (necesita wx):    importa los módulos de GUI. Caza NameError,
                            imports circulares y atributos inexistentes que
                            py_compile no detecta.
  Fase 3  (Windows + pywinauto): lanza la app, recorre el árbol de
                            accesibilidad (UI Automation, el mismo que usa
                            NVDA) y reporta controles interactivos sin nombre
                            accesible. Después cierra la app.

Uso:
    python smoke_test.py            # todas las fases disponibles
    python smoke_test.py --no-gui   # solo fases 1 y 2 (no abre la ventana)

Para la fase 3 hace falta:  pip install pywinauto
"""

from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))

# Controles que SIEMPRE deben tener nombre accesible (lo que NVDA anuncia
# al llegar a ellos con Tab). Si alguno aparece sin nombre es un fallo.
_INTERACTIVOS = {"Button", "Edit", "ComboBox", "List", "CheckBox", "RadioButton"}

_MODULOS_CORE = [
    "bellbird.core.config",
    "bellbird.core.conversation",
    "bellbird.core.llama_client",
    "bellbird.core.llama_runner",
    "bellbird.core.speech",
    "bellbird.core.text_utils",
    "bellbird.core.logger",
    "bellbird.core.permission_manager",
    "bellbird.core.tool_executor",
]

_MODULOS_UI = [
    "bellbird.ui.chat_panel",
    "bellbird.ui.message_detail_dialog",
    "bellbird.ui.permission_dialog",
    "bellbird.ui.preferences_dialog",
    "bellbird.ui.main_window",
]


def _titulo(texto):
    print("\n" + "=" * 60)
    print("  " + texto)
    print("=" * 60)


def fase1_logica() -> bool:
    _titulo("FASE 1 — Importar lógica pura (core/, cualquier SO)")
    ok = True
    for nombre in _MODULOS_CORE:
        try:
            __import__(nombre)
            print(f"  [ok]    import {nombre}")
        except Exception as exc:
            ok = False
            print(f"  [FALLO] import {nombre}: {exc.__class__.__name__}: {exc}")
    return ok


def fase2_gui() -> bool:
    _titulo("FASE 2 — Importar módulos de GUI (necesita wxPython)")
    try:
        import wx  # noqa: F401
    except ImportError:
        print("  [saltada] wxPython no está instalado.")
        print("            En Windows: uv sync")
        return True
    ok = True
    print(f"  wxPython {wx.version()}")
    for nombre in _MODULOS_UI:
        try:
            __import__(nombre)
            print(f"  [ok]    import {nombre}")
        except Exception as exc:
            ok = False
            print(f"  [FALLO] import {nombre}: {exc.__class__.__name__}: {exc}")
    return ok


def _recorrer(win):
    """Devuelve lista de (tipo, nombre) de win y sus descendientes."""
    salida = []
    try:
        elementos = [win] + win.descendants()
    except Exception as exc:
        print(f"  No se pudo recorrer la ventana: {exc}")
        return salida
    for el in elementos:
        try:
            info = el.element_info
            salida.append((info.control_type or "?", (info.name or "").strip()))
        except Exception:
            pass
    return salida


def fase3_accesibilidad() -> bool:
    _titulo("FASE 3 — Árbol de accesibilidad (Windows + pywinauto)")
    if sys.platform != "win32":
        print("  [saltada] No es Windows; no hay árbol UI Automation que leer.")
        return True
    try:
        import time
        from pywinauto import Application, Desktop
    except ImportError:
        print("  [saltada] pywinauto no está instalado.")
        print("            pip install pywinauto")
        return True

    main_py = os.path.join(AQUI, "bellbird", "main.py")
    cmd = f'"{sys.executable}" "{main_py}"'
    print(f"  Lanzando: {cmd}")
    # wait_for_idle=False: python.exe es un proceso de consola que luego abre
    # la ventana wx. Si esperamos idle, pywinauto falla con error 1471.
    # Buscamos la ventana por título en todo el escritorio para tolerar el
    # caso de que uv relance el intérprete en un proceso hijo distinto.
    app = Application(backend="uia").start(cmd, work_dir=AQUI,
                                           wait_for_idle=False)
    win_pid = None
    try:
        def _buscar_ventana():
            try:
                for w in Desktop(backend="uia").windows():
                    try:
                        if (w.window_text() or "").startswith("Bellbird"):
                            return w
                    except Exception:
                        continue
            except Exception:
                pass
            return None

        win = None
        limite = time.monotonic() + 25
        while time.monotonic() < limite:
            win = _buscar_ventana()
            if win is not None:
                break
            time.sleep(0.5)
        if win is None:
            raise TimeoutError("la ventana 'Bellbird' no apareció en 25 s")
        win_pid = win.element_info.process_id
        print("  Ventana visible. Recorriendo controles...\n")

        controles = _recorrer(win)
        sin_nombre = []
        for tipo, nombre in controles:
            etiqueta = nombre if nombre else "(SIN NOMBRE)"
            print(f"    {tipo:14s}  {etiqueta}")
            if tipo in _INTERACTIVOS and not nombre:
                sin_nombre.append(tipo)

        print(f"\n  Total de controles: {len(controles)}")
        if sin_nombre:
            print(f"  [AVISO ACCESIBILIDAD] {len(sin_nombre)} control(es) "
                  f"interactivo(s) SIN nombre: {', '.join(sin_nombre)}")
            return False
        print("  [ok] Todos los controles interactivos tienen nombre accesible.")
        return True
    except Exception as exc:
        print(f"  [FALLO] {exc.__class__.__name__}: {exc}")
        return False
    finally:
        cerrado = False
        if win_pid is not None:
            try:
                Application(backend="uia").connect(process=win_pid).kill()
                cerrado = True
            except Exception:
                pass
        try:
            app.kill()
            cerrado = True
        except Exception:
            pass
        if cerrado:
            print("\n  Aplicación cerrada.")


def main():
    no_gui = "--no-gui" in sys.argv
    os.chdir(AQUI)
    if AQUI not in sys.path:
        sys.path.insert(0, AQUI)

    r1 = fase1_logica()
    r2 = fase2_gui()
    r3 = True if no_gui else fase3_accesibilidad()

    _titulo("RESUMEN")
    print(f"  Fase 1 (core imports):  {'OK' if r1 else 'FALLO'}")
    print(f"  Fase 2 (GUI imports):   {'OK' if r2 else 'FALLO'}")
    if no_gui:
        print("  Fase 3 (accesibilidad): omitida (--no-gui)")
    else:
        print(f"  Fase 3 (accesibilidad): {'OK' if r3 else 'FALLO / avisos'}")
    print()
    sys.exit(0 if (r1 and r2 and r3) else 1)


if __name__ == "__main__":
    main()
