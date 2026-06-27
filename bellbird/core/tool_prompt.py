"""Environment-aware system prompt for tool use — wx-free, testable on WSL.

Local GGUF models are trained mostly on Linux/bash and, when given tools, tend
to (a) call a tool for *everything* and (b) end their turn with a bare tool
call and no written answer — exactly the erratic behaviour observed (e.g.
answering "¿quién eres?" by running ``whoami`` and then saying nothing).

The fix is the same "SYSTEM INFORMATION" technique used by agent tools (Cline,
OpenAI Codex, Claude Code, open-interpreter): inject a short system message that
states the REAL operating system / shell / working directory and gives explicit
rules for *when* and *how* to use tools. Detection is conservative and never
raises.

Refs (June 2026):
- Cline "SYSTEM INFORMATION" + "before using execute_command, think about the
  SYSTEM INFORMATION context" rule.
- prompthub.us "Prompt Engineering for AI Agents" (environment block).
- mattwestcott.org "Give your LLM a terminal".
"""

import os
import platform
import sys
from datetime import date


def detect_environment() -> dict:
    """Describe the runtime environment for the tool prompt. Never raises."""
    system = platform.system()
    is_wsl = False
    os_label = system or "desconocido"
    shell = "el shell del sistema"

    if system == "Windows":
        build = 0
        try:
            build = int(getattr(sys.getwindowsversion(), "build", 0))
        except Exception:
            build = 0
        # Windows 11 keeps the "10.0" major version but bumps the build to
        # >= 22000, so the build number is the only reliable 10-vs-11 signal.
        os_label = "Windows 11" if build >= 22000 else "Windows 10"
        if build:
            os_label += f" (build {build})"
        shell = "PowerShell"
    elif system == "Linux":
        try:
            with open("/proc/version", "r", encoding="utf-8", errors="replace") as f:
                if "microsoft" in f.read().lower():
                    is_wsl = True
        except Exception:
            pass
        os_label = "Linux (WSL)" if is_wsl else "Linux"
        shell = (os.environ.get("SHELL", "bash").rsplit("/", 1)[-1]) or "bash"
    elif system == "Darwin":
        os_label = "macOS"
        shell = (os.environ.get("SHELL", "zsh").rsplit("/", 1)[-1]) or "zsh"

    cwd = ""
    try:
        cwd = os.getcwd()
    except Exception:
        cwd = ""

    return {
        "os": os_label,
        "system": system,
        "is_wsl": is_wsl,
        "shell": shell,
        "cwd": cwd,
        "date": date.today().isoformat(),
    }


def build_tool_system_prompt(env: dict | None = None) -> str:
    """Build the Spanish environment-aware tool-use system message."""
    env = env or detect_environment()

    if env["system"] == "Windows":
        syntax = (
            "Los comandos DEBEN ser válidos en PowerShell de Windows "
            "(por ejemplo Get-ChildItem, Get-Location, $env:USERNAME). NO uses "
            "sintaxis de Linux/bash (ls, pwd, cat, rm, ~/ ) salvo que exista "
            "como alias real en PowerShell."
        )
    else:
        donde = "WSL" if env["is_wsl"] else env["system"]
        syntax = (
            f"Los comandos DEBEN ser válidos en {env['shell']} ({donde}), no en "
            "otro sistema operativo."
        )

    return (
        "INFORMACIÓN DEL SISTEMA (entorno REAL donde se ejecutan las herramientas):\n"
        f"- Sistema operativo: {env['os']}\n"
        f"- Shell / terminal: {env['shell']}\n"
        f"- Directorio de trabajo: {env['cwd']}\n"
        f"- Fecha: {env['date']}\n\n"
        "USO DE HERRAMIENTAS:\n"
        "- Tenés herramientas (terminal y archivos), pero NO son para todo. "
        "Usalas SOLO cuando el usuario pide explícitamente ejecutar algo, o "
        "cuando necesitás un dato del sistema que no podés conocer de memoria. "
        "Para preguntas generales o de conocimiento, respondé directamente con "
        "texto, SIN ejecutar comandos.\n"
        f"- {syntax}\n"
        "- Después de usar una herramienta, SIEMPRE explicá el resultado al "
        "usuario con texto claro. NUNCA termines tu turno con solo una llamada "
        "a herramienta y sin una respuesta escrita.\n"
        "- Hacé el mínimo de comandos necesarios; no encadenes acciones que el "
        "usuario no pidió."
    )
