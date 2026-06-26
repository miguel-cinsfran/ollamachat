"""Tests for file-tool executor methods and tool_catalog."""

import pytest
from pathlib import Path

from bellbird.core.tool_executor import ToolExecutor
from bellbird.core.tool_catalog import (
    ALL_FILE_TOOLS,
    FILE_TOOL_NAMES,
    FILE_TOOL_RISK,
    SHELL_TOOL,
    display_command,
    get_enabled_tools,
)
from bellbird.core.config import BellbirdConfig
from bellbird.core.permission_manager import RiskLevel


class TestReadFile:
    def test_reads_existing_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("Hola mundo", encoding="utf-8")
        result = ToolExecutor().read_file(str(f))
        assert result.returncode == 0
        assert "Hola mundo" in result.stdout

    def test_missing_file_returns_error(self, tmp_path):
        result = ToolExecutor().read_file(str(tmp_path / "nope.txt"))
        assert result.returncode == 1
        assert result.stderr

    def test_truncates_large_file(self, tmp_path):
        big = tmp_path / "big.txt"
        big.write_text("x" * 10000, encoding="utf-8")
        result = ToolExecutor().read_file(str(big))
        assert len(result.stdout) <= ToolExecutor.MAX_OUTPUT_CHARS


class TestListDir:
    def test_lists_files(self, tmp_path):
        (tmp_path / "a.txt").touch()
        (tmp_path / "b.txt").touch()
        result = ToolExecutor().list_dir(str(tmp_path))
        assert result.returncode == 0
        assert "a.txt" in result.stdout
        assert "b.txt" in result.stdout

    def test_missing_dir_returns_error(self):
        result = ToolExecutor().list_dir("/nonexistent/path/xyz")
        assert result.returncode == 1
        assert result.stderr


class TestWriteFile:
    def test_creates_new_file(self, tmp_path):
        f = tmp_path / "out.txt"
        result = ToolExecutor().write_file(str(f), "contenido")
        assert result.returncode == 0
        assert f.read_text(encoding="utf-8") == "contenido"

    def test_overwrites_existing(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("viejo", encoding="utf-8")
        ToolExecutor().write_file(str(f), "nuevo")
        assert f.read_text(encoding="utf-8") == "nuevo"

    def test_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "sub" / "deep" / "file.txt"
        result = ToolExecutor().write_file(str(f), "ok")
        assert result.returncode == 0
        assert f.exists()


class TestEditFile:
    def test_replaces_first_occurrence(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("foo bar foo", encoding="utf-8")
        result = ToolExecutor().edit_file(str(f), "foo", "baz")
        assert result.returncode == 0
        assert f.read_text(encoding="utf-8") == "baz bar foo"

    def test_old_text_not_found_returns_error(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("hello", encoding="utf-8")
        result = ToolExecutor().edit_file(str(f), "NONEXISTENT", "y")
        assert result.returncode == 1

    def test_missing_file_returns_error(self, tmp_path):
        result = ToolExecutor().edit_file(str(tmp_path / "nope.txt"), "a", "b")
        assert result.returncode == 1


class TestDispatch:
    def test_run_file_tool_read(self, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text("data", encoding="utf-8")
        r = ToolExecutor().run_file_tool("read_file", {"path": str(f)})
        assert "data" in r.stdout

    def test_run_file_tool_unknown(self):
        r = ToolExecutor().run_file_tool("unknown_tool", {})
        assert r.returncode == 1


class TestToolCatalog:
    def test_file_tool_names_correct(self):
        assert FILE_TOOL_NAMES == {"read_file", "list_dir", "write_file", "edit_file"}

    def test_read_and_list_are_green(self):
        assert FILE_TOOL_RISK["read_file"] == RiskLevel.GREEN
        assert FILE_TOOL_RISK["list_dir"] == RiskLevel.GREEN

    def test_write_and_edit_are_yellow(self):
        assert FILE_TOOL_RISK["write_file"] == RiskLevel.YELLOW
        assert FILE_TOOL_RISK["edit_file"] == RiskLevel.YELLOW

    def test_system_path_blocked_display(self):
        from bellbird.core.permission_manager import PermissionManager
        pm = PermissionManager()
        assert pm.is_system_destructive('write_file("C:\\Windows\\system32\\x.dll")')

    def test_display_command_shell(self):
        cmd = display_command("shell_execute", {"command": "dir"})
        assert cmd == "dir"

    def test_display_command_read_file(self):
        cmd = display_command("read_file", {"path": "/home/user/file.txt"})
        assert "read_file" in cmd
        assert "/home/user/file.txt" in cmd

    def test_get_enabled_tools_none_when_disabled(self):
        cfg = BellbirdConfig(tools_enabled=False)
        assert get_enabled_tools(cfg) is None

    def test_get_enabled_tools_shell_only(self):
        cfg = BellbirdConfig(tools_enabled=True, file_tools_enabled=False)
        tools = get_enabled_tools(cfg)
        assert tools is not None
        names = [t["function"]["name"] for t in tools]
        assert names == ["shell_execute"]

    def test_get_enabled_tools_all_when_file_tools_on(self):
        cfg = BellbirdConfig(tools_enabled=True, file_tools_enabled=True)
        tools = get_enabled_tools(cfg)
        assert tools is not None
        names = {t["function"]["name"] for t in tools}
        assert "shell_execute" in names
        assert "read_file" in names
        assert "write_file" in names
