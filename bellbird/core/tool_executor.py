"""ToolExecutor — headless PowerShell subprocess wrapper.

wx-free, tested on WSL via sys.platform mocking. On non-win32 returns
an error ToolResult immediately without invoking subprocess.
"""

import subprocess
import sys


class ToolResult:
    def __init__(self, tool_name: str, command: str,
                 stdout: str, stderr: str, returncode: int) -> None:
        self.tool_name = tool_name
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def to_display_text(self) -> str:
        """Texto para mostrar en el chat."""
        lines = [
            f"[Herramienta: {self.tool_name}]",
            f"> {self.command}",
            "-" * 40,
        ]
        if self.stdout.strip():
            lines.append(self.stdout.rstrip())
        if self.stderr.strip():
            lines.append(f"[stderr] {self.stderr.rstrip()}")
        if self.returncode != 0:
            lines.append(f"[codigo de salida: {self.returncode}]")
        return "\n".join(lines)

    def to_tool_message(self) -> dict:
        """Mensaje tipo 'tool' para enviar al modelo."""
        content = self.stdout
        if self.stderr:
            content += f"\n[stderr] {self.stderr}"
        if self.returncode != 0:
            content += f"\n[exit code: {self.returncode}]"
        return {
            "role": "tool",
            "content": content.strip(),
            "tool_call_id": "",  # se rellena en main_window
        }


class ToolExecutor:
    MAX_OUTPUT_CHARS = 4000

    def run(self, tool_name: str, command: str,
            timeout: float = 30.0) -> ToolResult:
        """Ejecuta el comando en PowerShell. wx-free, testeable headless."""
        if sys.platform != "win32":
            return ToolResult(
                tool_name, command, "",
                "Tool execution only available on Windows.", 1,
            )

        # Preferir pwsh.exe (PowerShell 7+), fallback a powershell.exe
        shell = "pwsh.exe"
        try:
            subprocess.run(
                [shell, "-Command", "exit 0"],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            shell = "powershell.exe"

        try:
            result = subprocess.run(
                [shell, "-NoProfile", "-NonInteractive",
                 "-Command", command],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            stdout = result.stdout[:self.MAX_OUTPUT_CHARS]
            stderr = result.stderr[:self.MAX_OUTPUT_CHARS]
            return ToolResult(tool_name, command, stdout, stderr,
                              result.returncode)
        except subprocess.TimeoutExpired:
            return ToolResult(tool_name, command, "",
                              f"Timeout despues de {timeout}s.", 1)
        except Exception as e:
            return ToolResult(tool_name, command, "", str(e), 1)
