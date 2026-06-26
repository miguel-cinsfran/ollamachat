"""Tool definitions (JSON-schema) and risk metadata for all Bellbird tools."""

from __future__ import annotations

from bellbird.core.permission_manager import RiskLevel

SHELL_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "shell_execute",
        "description": (
            "Ejecuta un comando en PowerShell en el sistema Windows del "
            "usuario. Usa esto para operaciones de archivos, sistema, o "
            "cuando el usuario lo pide explicitamente."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "El comando de PowerShell a ejecutar.",
                }
            },
            "required": ["command"],
        },
    },
}

READ_FILE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Lee el contenido de un archivo de texto (UTF-8).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta absoluta o relativa del archivo a leer.",
                }
            },
            "required": ["path"],
        },
    },
}

LIST_DIR_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "list_dir",
        "description": "Lista el contenido de un directorio.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del directorio a listar.",
                }
            },
            "required": ["path"],
        },
    },
}

WRITE_FILE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Crea o sobreescribe un archivo con el contenido dado (UTF-8).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a escribir.",
                },
                "content": {
                    "type": "string",
                    "description": "Contenido a escribir en el archivo.",
                },
            },
            "required": ["path", "content"],
        },
    },
}

EDIT_FILE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": (
            "Reemplaza la primera ocurrencia de old_text por new_text en un archivo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a editar.",
                },
                "old_text": {
                    "type": "string",
                    "description": "Texto exacto a reemplazar.",
                },
                "new_text": {
                    "type": "string",
                    "description": "Texto de reemplazo.",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
}

# All tool definitions in one place — passed to the API as tool array.
ALL_FILE_TOOLS: list[dict] = [
    READ_FILE_TOOL,
    LIST_DIR_TOOL,
    WRITE_FILE_TOOL,
    EDIT_FILE_TOOL,
]

# Fixed risk per file tool name (shell_execute risk is classified per command).
FILE_TOOL_RISK: dict[str, RiskLevel] = {
    "read_file": RiskLevel.GREEN,
    "list_dir": RiskLevel.GREEN,
    "write_file": RiskLevel.YELLOW,
    "edit_file": RiskLevel.YELLOW,
}

FILE_TOOL_NAMES: frozenset[str] = frozenset(FILE_TOOL_RISK.keys())


def get_enabled_tools(config) -> list[dict] | None:
    """Return the active tool list for the API based on config.tools_enabled."""
    if not config.tools_enabled:
        return None
    tools = [SHELL_TOOL]
    if getattr(config, "file_tools_enabled", False):
        tools.extend(ALL_FILE_TOOLS)
    return tools


def display_command(tool_name: str, args: dict) -> str:
    """Human-readable summary of a tool invocation (shown in permission dialog)."""
    if tool_name == "shell_execute":
        return args.get("command", str(args))
    path = args.get("path", "?")
    if tool_name == "read_file":
        return f'read_file("{path}")'
    if tool_name == "list_dir":
        return f'list_dir("{path}")'
    if tool_name == "write_file":
        chars = len(args.get("content", ""))
        return f'write_file("{path}", {chars} chars)'
    if tool_name == "edit_file":
        return f'edit_file("{path}", ...)'
    return f"{tool_name}({args})"
