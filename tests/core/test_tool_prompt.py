"""Tests for the environment-aware tool system prompt (wx-free)."""

from bellbird.core.tool_prompt import build_tool_system_prompt, detect_environment


def test_detect_environment_has_keys():
    env = detect_environment()
    for key in ("os", "system", "is_wsl", "shell", "cwd", "date"):
        assert key in env


def test_windows_prompt_mentions_powershell():
    env = {
        "os": "Windows 11 (build 22631)", "system": "Windows", "is_wsl": False,
        "shell": "PowerShell", "cwd": "C:\\Users\\x", "date": "2026-06-26",
    }
    text = build_tool_system_prompt(env)
    assert "Windows 11" in text
    assert "PowerShell" in text
    assert "ls, pwd" in text  # explicit "don't use Linux syntax" hint
    # Core behavioural rules present
    assert "SOLO cuando" in text
    assert "SIEMPRE explicá" in text


def test_linux_prompt_mentions_shell():
    env = {
        "os": "Linux (WSL)", "system": "Linux", "is_wsl": True,
        "shell": "bash", "cwd": "/home/x", "date": "2026-06-26",
    }
    text = build_tool_system_prompt(env)
    assert "bash" in text
    assert "WSL" in text


def test_prompt_is_nonempty_for_real_environment():
    text = build_tool_system_prompt()
    assert "INFORMACIÓN DEL SISTEMA" in text
    assert len(text) > 200
