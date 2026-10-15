"""Tests for reviewed development commands and execution environments."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import time

import pytest

from hpc_mcp import commands
from hpc_mcp.commands import (
    available_commands,
    checked_environment,
    process_output,
    run_checked,
    start_process,
)
from hpc_mcp.config import load_settings
from hpc_mcp.server import build_server


def test_command_environment_is_opt_in(readonly, root):
    """Require explicit permission for each overridden variable."""
    settings = replace(readonly, enable_commands=True, allowed_commands=("env",))
    with pytest.raises(PermissionError):
        run_checked(settings, ["env"], str(root), {"OMP_NUM_THREADS": "4"})

    settings = replace(settings, allowed_environment_variables=("OMP_NUM_THREADS",))
    result = run_checked(settings, ["env"], str(root), {"OMP_NUM_THREADS": "4"})
    assert result["exit_code"] == 0
    assert "OMP_NUM_THREADS=4" in result["output"]

    with pytest.raises(PermissionError):
        checked_environment(settings, {"LD_PRELOAD": "/tmp/test.so"})


@pytest.mark.parametrize("env", [
    {"OMP_NUM_THREADS": "4\nBAD=1"},
    {"OMP_NUM_THREADS": "x" * 2049},
    {"INVALID NAME": "4"},
])
def test_reject_unsafe_environment_values(readonly, env):
    """Reject multiline, huge, or malformed overrides."""
    settings = replace(readonly, allowed_environment_variables=("OMP_NUM_THREADS",))
    with pytest.raises((ValueError, PermissionError)):
        checked_environment(settings, env)


def test_environment_configuration(tmp_path, root):
    """Read approved environment names from TOML."""
    config = tmp_path / "config.toml"
    config.write_text(
        f'[filesystem]\nroots = ["{root}"]\n'
        '[commands]\nenv_allowlist = ["OMP_NUM_THREADS", "I_MPI_FABRICS"]\n',
        encoding="utf-8",
    )
    settings = load_settings(config)
    assert settings.allowed_environment_variables == ("OMP_NUM_THREADS", "I_MPI_FABRICS")


def test_environment_config_rejects_duplicates(tmp_path, root):
    """Disallow ambiguous environment policy declarations."""
    config = tmp_path / "config.toml"
    config.write_text(
        f'[filesystem]\nroots = ["{root}"]\n'
        '[commands]\nenv_allowlist = ["OMP_NUM_THREADS", "OMP_NUM_THREADS"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_settings(config)


def test_discovery_tool_requires_opt_in(readonly):
    """Expose command discovery only after command execution is enabled."""
    off = {item.name for item in asyncio.run(build_server(readonly).list_tools())}
    assert "list_allowed_commands" not in off
    enabled = replace(readonly, enable_commands=True, allowed_commands=("env",))
    on = {item.name for item in asyncio.run(build_server(enabled).list_tools())}
    assert "list_allowed_commands" in on
    info = available_commands(enabled)
    assert info["commands"][0]["name"] == "env"
    assert info["commands"][0]["available"]


def test_managed_process_reports_exit_code(readonly, root, tmp_path, monkeypatch):
    """Provide a success/failure status after a build process exits."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(commands, "session_dir", lambda: sessions)
    settings = replace(readonly, enable_commands=True, allowed_commands=("env",),
                       allowed_environment_variables=("OMP_NUM_THREADS",))
    started = start_process(settings, ["env"], str(root), {"OMP_NUM_THREADS": "2"})
    identifier = started["session_id"]
    result = None
    for _ in range(100):
        result = process_output(settings, identifier)
        if result["exit_code"] is not None:
            break
        time.sleep(0.02)
    assert result is not None and result["exit_code"] == 0
    assert "OMP_NUM_THREADS=2" in result["output"]