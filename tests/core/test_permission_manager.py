"""Tests for PermissionManager — 10 tests covering risk classification,
system-destructive detection, and session grant management."""

import pytest

from bellbird.core.permission_manager import PermissionManager, RiskLevel


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

    def test_classify_risk_case_insensitive(self):
        """Given uppercase commands, classify_risk still classifies correctly."""
        pm = PermissionManager()
        assert pm.classify_risk("REMOVE-ITEM C:\\Temp\\junk.txt") == RiskLevel.RED
        assert pm.classify_risk("MOVE-ITEM a.txt b.txt") == RiskLevel.YELLOW
        assert pm.classify_risk("GET-PROCESS") == RiskLevel.GREEN

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

    # ── risk-category-keyed grants (v0.7.5) ──────────────────────────────────

    def test_grant_session_with_risk(self):
        """grant_session with GREEN makes has_session_grant GREEN True."""
        pm = PermissionManager()
        pm.grant_session("shell", RiskLevel.GREEN)
        assert pm.has_session_grant("shell", RiskLevel.GREEN) is True

    def test_grant_green_does_not_cover_red(self):
        """A GREEN grant does NOT enable RED commands."""
        pm = PermissionManager()
        pm.grant_session("shell", RiskLevel.GREEN)
        assert pm.has_session_grant("shell", RiskLevel.RED) is False

    def test_grant_red_does_not_cover_green(self):
        """A RED grant does NOT enable GREEN commands."""
        pm = PermissionManager()
        pm.grant_session("shell", RiskLevel.RED)
        assert pm.has_session_grant("shell", RiskLevel.GREEN) is False

    def test_revoke_session_removes_one_pair(self):
        """revoke_session(name, level) removes only that pair."""
        pm = PermissionManager()
        pm.grant_session("shell", RiskLevel.GREEN)
        pm.grant_session("shell", RiskLevel.RED)
        pm.revoke_session("shell", RiskLevel.GREEN)
        assert pm.has_session_grant("shell", RiskLevel.GREEN) is False
        assert pm.has_session_grant("shell", RiskLevel.RED) is True

    def test_revoke_all_clears_all(self):
        """revoke_all clears every stored pair."""
        pm = PermissionManager()
        pm.grant_session("a", RiskLevel.GREEN)
        pm.grant_session("b", RiskLevel.RED)
        pm.revoke_all()
        assert pm.has_session_grant("a", RiskLevel.GREEN) is False
        assert pm.has_session_grant("b", RiskLevel.RED) is False

    def test_has_session_grant_no_raise(self):
        """has_session_grant for an unknown (name, level) returns False, no raise."""
        pm = PermissionManager()
        assert pm.has_session_grant("never", RiskLevel.GREEN) is False

    def test_grant_session_idempotent(self):
        """Double grant of same (name, level) is idempotent — no error."""
        pm = PermissionManager()
        pm.grant_session("shell", RiskLevel.GREEN)
        pm.grant_session("shell", RiskLevel.GREEN)
        assert pm.has_session_grant("shell", RiskLevel.GREEN) is True
