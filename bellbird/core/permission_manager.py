"""PermissionManager — risk classifier and ephemeral session grant store.

Headless (no wx, no I/O). Risk classification is pure regex-based,
never mutates state, never raises. Session grants are in-memory only,
reset on process exit — never written to disk.
"""

import enum
import re


class RiskLevel(enum.Enum):
    GREEN = "green"    # operaciones de solo lectura o creación
    YELLOW = "yellow"  # modificaciones
    RED = "red"        # borrado o irreversible


class PermissionManager:
    """Gestiona permisos de ejecución de herramientas por sesión.

    Los permisos se resetean al cerrar la app (en memoria, nunca a disco).
    La clasificación de riesgo solo informa al usuario — no bloquea nada
    automáticamente excepto los paths de sistema.
    """

    def __init__(self) -> None:
        self._session_grants: set[str] = set()

    def classify_risk(self, command: str) -> RiskLevel:
        """Clasifica el riesgo del comando. No bloquea, solo informa."""
        cmd = command.lower()
        red_patterns = [
            r'remove-item', r'\brm\b', r'\bdel\b', r'rmdir', r'rd\s',
            r'clear-content', r'format-volume',
        ]
        yellow_patterns = [
            r'move-item', r'rename-item', r'set-content', r'copy-item',
            r'mv\b', r'cp\b', r'sed\b', r'awk\b',
        ]
        for p in red_patterns:
            if re.search(p, cmd):
                return RiskLevel.RED
        for p in yellow_patterns:
            if re.search(p, cmd):
                return RiskLevel.YELLOW
        return RiskLevel.GREEN

    def is_system_destructive(self, command: str) -> bool:
        """Retorna True solo para comandos que tocan directorios del sistema.

        CRÍTICO: NUNCA bloquear automáticamente operaciones en directorios
        del usuario. El usuario puede necesitar mover, borrar o copiar
        sus propios archivos. Auto-bloqueo solo para paths de sistema.
        """
        system_paths = [
            r'c:\\windows', r'c:\\system32',
            r'c:\\program files', r'c:\\program files \(x86\)',
            r'format-volume', r'clear-disk',
        ]
        cmd = command.lower()
        for p in system_paths:
            if re.search(p, cmd):
                return True
        return False

    def has_session_grant(self, tool_name: str) -> bool:
        return tool_name in self._session_grants

    def grant_session(self, tool_name: str) -> None:
        self._session_grants.add(tool_name)

    def revoke_session(self, tool_name: str) -> None:
        self._session_grants.discard(tool_name)

    def revoke_all(self) -> None:
        self._session_grants.clear()
