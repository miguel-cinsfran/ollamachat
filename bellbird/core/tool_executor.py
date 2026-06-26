"""ToolExecutor — headless subprocess + file-tool executor.

wx-free, tested on WSL via sys.platform mocking.
shell_execute: PowerShell only, Windows-only.
read_file / list_dir / write_file / edit_file: platform-agnostic.
"""

import os
import subprocess
import sys
import threading
from pathlib import Path


class ToolResult:
    def __init__(self, tool_name: str, command: str,
                 stdout: str, stderr: str, returncode: int,
                 cancelled: bool = False) -> None:
        self.tool_name = tool_name
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.cancelled = cancelled

    def to_display_text(self) -> str:
        """Texto para mostrar en el chat."""
        lines = [
            f"[Herramienta: {self.tool_name}]",
            f"> {self.command}",
            "-" * 40,
        ]
        if self.cancelled:
            lines.append("[Cancelado]")
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
        if self.cancelled:
            content += "\n[Cancelado]"
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

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._cancelled = False

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
                creationflags=0x08000000,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            shell = "powershell.exe"

        self._cancelled = False
        proc: subprocess.Popen | None = None
        try:
            proc = subprocess.Popen(
                [shell, "-NoProfile", "-NonInteractive",
                 "-Command", command],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, text=True,
                encoding="utf-8", errors="replace",
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            # Store under lock so cancel() can see the live process.
            with self._lock:
                self._proc = proc
            # Release the lock before wait() to avoid 30s lock hold.
            proc.wait(timeout=timeout)
            stdout = (proc.stdout.read(self.MAX_OUTPUT_CHARS)
                      if proc.stdout else "")[:self.MAX_OUTPUT_CHARS]
            stderr = (proc.stderr.read(self.MAX_OUTPUT_CHARS)
                      if proc.stderr else "")[:self.MAX_OUTPUT_CHARS]
            returncode = proc.returncode
            cancelled = self._cancelled
            return ToolResult(tool_name, command, stdout, stderr,
                              returncode, cancelled=cancelled)
        except subprocess.TimeoutExpired:
            if proc is not None:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
            return ToolResult(tool_name, command, "",
                              f"Timeout despues de {timeout}s.", 1)
        except Exception as e:
            if proc is not None:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
            return ToolResult(tool_name, command, "", str(e), 1)
        finally:
            with self._lock:
                self._proc = None

    # ── File tools (platform-agnostic) ────────────────────────────────────────

    def read_file(self, path: str) -> ToolResult:
        """Read a text file (UTF-8). Returns content or error in stdout."""
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            content = content[:self.MAX_OUTPUT_CHARS]
            return ToolResult("read_file", f'read_file("{path}")', content, "", 0)
        except Exception as e:
            return ToolResult("read_file", f'read_file("{path}")', "", str(e), 1)

    def list_dir(self, path: str) -> ToolResult:
        """List directory contents. Returns newline-separated entries."""
        try:
            entries = sorted(os.listdir(path))
            content = "\n".join(entries)[:self.MAX_OUTPUT_CHARS]
            return ToolResult("list_dir", f'list_dir("{path}")', content, "", 0)
        except Exception as e:
            return ToolResult("list_dir", f'list_dir("{path}")', "", str(e), 1)

    def write_file(self, path: str, content: str) -> ToolResult:
        """Write (create or overwrite) a text file (UTF-8)."""
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult(
                "write_file", f'write_file("{path}")',
                f"Escrito: {len(content)} caracteres.", "", 0,
            )
        except Exception as e:
            return ToolResult("write_file", f'write_file("{path}")', "", str(e), 1)

    def edit_file(self, path: str, old_text: str, new_text: str) -> ToolResult:
        """Replace first occurrence of old_text with new_text in a file."""
        try:
            p = Path(path)
            original = p.read_text(encoding="utf-8", errors="replace")
            if old_text not in original:
                return ToolResult(
                    "edit_file", f'edit_file("{path}")',
                    "", f"old_text no encontrado en {path}.", 1,
                )
            modified = original.replace(old_text, new_text, 1)
            p.write_text(modified, encoding="utf-8")
            return ToolResult(
                "edit_file", f'edit_file("{path}")', "Archivo editado.", "", 0,
            )
        except Exception as e:
            return ToolResult("edit_file", f'edit_file("{path}")', "", str(e), 1)

    def run_file_tool(self, tool_name: str, args: dict) -> ToolResult:
        """Dispatch a file-tool call by name."""
        if tool_name == "read_file":
            return self.read_file(args.get("path", ""))
        if tool_name == "list_dir":
            return self.list_dir(args.get("path", ""))
        if tool_name == "write_file":
            return self.write_file(args.get("path", ""), args.get("content", ""))
        if tool_name == "edit_file":
            return self.edit_file(
                args.get("path", ""),
                args.get("old_text", ""),
                args.get("new_text", ""),
            )
        return ToolResult(tool_name, str(args), "", f"Tool desconocida: {tool_name}", 1)

    def cancel(self) -> None:
        """Cancel the currently running tool subprocess.

        Thread-safe, idempotent. Sends SIGTERM, waits 2s grace,
        then SIGKILL. Never raises.
        """
        with self._lock:
            proc = self._proc
            if proc is None:
                return
            # Check if already dead
            if proc.poll() is not None:
                self._proc = None
                return
            self._proc = None
            self._cancelled = True
        # Outside the lock to avoid 2s+1s lock hold.
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
        except Exception:
            pass  # Best-effort cleanup, never raise
