"""Tests for policy setup and optional execution."""

from dataclasses import replace
import asyncio
import pytest
from hpc_mcp.commands import checked_argv, run_checked
from hpc_mcp.config import load_settings
from hpc_mcp.server import build_server


def test_policy_from_toml(tmp_path, root):
    """Load explicit per-user configuration."""
    path = tmp_path / "config.toml"
    path.write_text(f'[filesystem]\nroots = ["{root}"]\n[permissions]\nenable_writes = true\n')
    policy = load_settings(path)
    assert policy.enable_writes
    assert not policy.enable_commands


def test_invalid_slurm_combination(tmp_path, root):
    """Reject submit privilege without command-execution opt-in."""
    path = tmp_path / "config.toml"
    path.write_text(f'[filesystem]\nroots = ["{root}"]\n[permissions]\nenable_slurm_submit = true\n')
    with pytest.raises(ValueError):
        load_settings(path)


def test_commands_default_denied(readonly):
    """Deny even innocuous commands unless explicitly enabled."""
    with pytest.raises(PermissionError):
        checked_argv(readonly, ["whoami"])


def test_allowlisted_command(readonly, root):
    """Execute only commands explicitly allowed by a user."""
    allowed = replace(readonly, enable_commands=True, allowed_commands=("whoami",))
    result = run_checked(allowed, ["whoami"], str(root))
    assert result["exit_code"] == 0
    with pytest.raises(PermissionError):
        run_checked(allowed, ["bash", "-c", "echo hello"], str(root))


def test_registered_tools_default(readonly):
    """Ensure the MCP server does not advertise dangerous tools by default."""
    server = build_server(readonly)
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {"ping", "get_system_info", "slurm_list_jobs"}.issubset(names)
    assert "write_file_tool" not in names
    assert "execute_command" not in names
