"""Tests for PermissionManager — 10 tests covering risk classification,
system-destructive detection, and session grant management."""

import pytest

from ollamachat.core.permission_manager import PermissionManager, RiskLevel


class TestPermissionManager:
    """Tests for PermissionManager."""

    # ── classify_risk ────────────────────────────────────────────────────

    def test_classify_risk_green(self):
        """Given safe commands, classify_risk returns GREEN."""
        pm = PermissionManager()
        assert pm.classify_risk("mkdir foo") == RiskLevel.GREEN
        assert pm.classify_risk("Get-Process") == RiskLevel.GREEN
        assert pm.classify_risk("ls -la") == RiskLevel.GREEN

    def test_classify_risk_yellow(self):
        """Given Move-Item, classify_risk returns YELLOW."""
        pm = PermissionManager()
        result = pm.classify_risk("Move-Item a.txt b.txt")
        assert result == RiskLevel.YELLOW

    def test_classify_risk_red(self):
        """Given Remove-Item, classify_risk returns RED."""
        pm = PermissionManager()
        result = pm.classify_risk("Remove-Item C:\\Temp\\junk.txt")
        assert result == RiskLevel.RED

    # ── is_system_destructive ────────────────────────────────────────────

    def test_is_system_destructive_windows_dir(self):
        """Given C:\\Windows path, is_system_destructive returns True."""
        pm = PermissionManager()
        result = pm.is_system_destructive("Remove-Item C:\\Windows\\System32\\foo.dll")
        assert result is True

    def test_is_system_destructive_system32(self):
        """Given C:\\System32 directly, is_system_destructive returns True."""
        pm = PermissionManager()
        result = pm.is_system_destructive("del C:\\System32\\driver.sys")
        assert result is True

    def test_is_system_destructive_user_dir_returns_false(self):
        """Given a user-directory path with Remove-Item, returns False (CRITICAL)."""
        pm = PermissionManager()
        result = pm.is_system_destructive(
            "C:\\Users\\Miguel\\Documents\\Remove-Item test.txt"
        )
        assert result is False

    def test_is_system_destructive_format_volume(self):
        """Given Format-Volume, is_system_destructive returns True."""
        pm = PermissionManager()
        result = pm.is_system_destructive("Format-Volume -DriveLetter C")
        assert result is True

    # ── session grants ───────────────────────────────────────────────────

    def test_session_grant_and_has(self):
        """After grant_session, has_session_grant returns True."""
        pm = PermissionManager()
        assert pm.has_session_grant("shell_execute") is False
        pm.grant_session("shell_execute")
        assert pm.has_session_grant("shell_execute") is True
        assert pm.has_session_grant("other_tool") is False

    def test_session_revoke(self):
        """After grant then revoke, has_session_grant returns False."""
        pm = PermissionManager()
        pm.grant_session("shell_execute")
        pm.grant_session("read_file")
        pm.revoke_session("shell_execute")
        assert pm.has_session_grant("shell_execute") is False
        assert pm.has_session_grant("read_file") is True

    def test_revoke_all(self):
        """After revoke_all, no tool has a session grant."""
        pm = PermissionManager()
        pm.grant_session("a")
        pm.grant_session("b")
        pm.revoke_all()
        assert pm.has_session_grant("a") is False
        assert pm.has_session_grant("b") is False
