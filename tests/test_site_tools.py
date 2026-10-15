"""Validate and exercise fixed-argument custom site command tools."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from hpc_mcp.config import load_settings
from hpc_mcp.server import build_server
from hpc_mcp.site_tools import run_site_tool


def _config(tmp_path, root, command, *, enabled=True, extra=""):
    config = tmp_path / "config.toml"
    config.write_text(
        f'[filesystem]\nroots = ["{root}"]\n'
        f'[permissions]\nenable_site_tools = {str(enabled).lower()}\n'
        '[site_tools.point_balance]\n'
        'description = "Check remaining compute points"\n'
        f'argv = ["{command}", "--summary"]\n'
        'read_only = true\n'
        f'cwd = "{root}"\n'
        'timeout_seconds = 10\n'
        + extra
    )
    return config


def test_site_tool_registration_and_execution(tmp_path, root):
    """Expose one fixed-argument site tool and execute it without a shell."""
    cmd = tmp_path / "point"
    cmd.write_text("#!/bin/sh\nprintf 'points: 42\\n'\n")
    cmd.chmod(0o700)
    settings = load_settings(_config(tmp_path, root, cmd))
    assert settings.enable_site_tools
    names = {tool.name for tool in asyncio.run(build_server(settings).list_tools())}
    assert "site_point_balance" in names
    result = run_site_tool(settings, settings.site_tools[0])
    assert result["exit_code"] == 0
    assert "points: 42" in result["output"]
    # Exercise the actual FastMCP named-tool endpoint as well as the runner.
    payload = asyncio.run(build_server(settings).call_tool("site_point_balance", {}))
    assert "points: 42" in str(payload)


def test_site_tool_not_exposed_by_default(tmp_path, root):
    """The user must explicitly enable configured site commands."""
    cmd = tmp_path / "point"
    cmd.write_text("#!/bin/sh\nexit 0\n")
    cmd.chmod(0o700)
    settings = load_settings(_config(tmp_path, root, cmd, enabled=False))
    names = {tool.name for tool in asyncio.run(build_server(settings).list_tools())}
    assert "site_point_balance" not in names
    with pytest.raises(PermissionError):
        run_site_tool(settings, settings.site_tools[0])


@pytest.mark.parametrize("argv,readonly_flag", [
    ('["point"]', "true"),
    ('["/bin/sh", "-c", "echo x"]', "false"),
])
def test_invalid_site_tool_config(tmp_path, root, argv, readonly_flag):
    """Reject relative command paths and non-read-only declarations."""
    conf = tmp_path / "bad.toml"
    conf.write_text(
        f'[filesystem]\nroots = ["{root}"]\n'
        '[site_tools.example]\ndescription = "Test command"\n'
        f'argv = {argv}\nread_only = {readonly_flag}\n'
    )
    with pytest.raises(ValueError):
        load_settings(conf)


def test_site_tool_outside_root_cwd_rejected(tmp_path, root):
    """The site tool's working directory cannot be a path outside roots."""
    conf = tmp_path / "bad.toml"
    conf.write_text(
        f'[filesystem]\nroots = ["{root}"]\n'
        '[site_tools.example]\ndescription = "Test command"\n'
        'argv = ["/bin/echo", "hello"]\nread_only = true\n'
        f'cwd = "{tmp_path}"\n'
    )
    with pytest.raises(ValueError):
        load_settings(conf)

def test_two_site_tools_keep_separate_commands(tmp_path, root):
    """Dynamic registration must not accidentally capture the last command."""
    first = tmp_path / "point"
    second = tmp_path / "quota"
    for exe, value in ((first, "POINT_A"), (second, "QUOTA_B")):
        exe.write_text("#!/bin/sh\nprintf '" + value + "\\n'\n")
        exe.chmod(0o700)
    config = tmp_path / "both.toml"
    config.write_text(
        f'[filesystem]\nroots = ["{root}"]\n'
        '[permissions]\nenable_site_tools = true\n'
        f'[site_tools.point_balance]\ndescription = "Point balance"\nargv = ["{first}"]\nread_only = true\n'
        f'[site_tools.quota_summary]\ndescription = "Quota summary"\nargv = ["{second}"]\nread_only = true\n'
    )
    policy = load_settings(config)
    server = build_server(policy)
    listed = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {"site_point_balance", "site_quota_summary"} <= listed
    first_result = asyncio.run(server.call_tool("site_point_balance", {}))
    second_result = asyncio.run(server.call_tool("site_quota_summary", {}))
    assert "POINT_A" in str(first_result)
    assert "QUOTA_B" in str(second_result)
    assert "QUOTA_B" not in str(first_result)
