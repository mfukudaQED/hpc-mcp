"""Test opt-in capabilities without changing the real user's configuration."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from hpc_mcp.commands import run_checked
from hpc_mcp.filesystem import make_directory, write_file, replace_text, read_file
from hpc_mcp.server import build_server


def test_writable_tools_registered_only_with_opt_in(readonly):
    """Advertising mutating tools requires explicit write capability."""
    off = {tool.name for tool in asyncio.run(build_server(readonly).list_tools())}
    assert "make_directory_tool" not in off
    assert "write_file_tool" not in off
    assert "replace_text_tool" not in off
    writable = replace(readonly, enable_writes=True)
    on = {tool.name for tool in asyncio.run(build_server(writable).list_tools())}
    assert {"make_directory_tool", "write_file_tool", "replace_text_tool"} <= on


def test_process_tools_registered_only_with_opt_in(readonly):
    """Only trusted per-user policy exposes command/process management."""
    disabled = {tool.name for tool in asyncio.run(build_server(readonly).list_tools())}
    assert "execute_command" not in disabled
    allowed = replace(readonly, enable_commands=True)
    enabled = {tool.name for tool in asyncio.run(build_server(allowed).list_tools())}
    assert {
        "execute_command", "start_background_process",
        "read_background_output", "terminate_background_process",
    } <= enabled


def test_make_directory_and_edit_guard(readonly, root, tmp_path):
    """Create directories under approved roots and reject traversal."""
    with pytest.raises(PermissionError):
        make_directory(readonly, str(root / "new"))
    writable = replace(readonly, enable_writes=True)
    created = make_directory(writable, str(root / "a/b"))
    assert created["created_or_exists"]
    target = root / "a/b/source.py"
    first = write_file(writable, str(target), "alpha=1\n")
    with pytest.raises(ValueError):
        replace_text(writable, str(target), "alpha", "beta", "bad-hash")
    changed = replace_text(writable, str(target), "alpha", "beta", first["sha256"])
    assert changed["sha256"] != first["sha256"]
    assert read_file(writable, str(target))["content"] == "beta=1"
    with pytest.raises(PermissionError):
        make_directory(writable, str(tmp_path / "escape"))


def test_command_output_is_bounded(readonly, root):
    """A noisy allowed command cannot generate unbounded model output."""
    from shutil import which
    interpreter = "python3" if which("python3") else "python"
    configured = replace(
        readonly, enable_commands=True, allowed_commands=(interpreter,),
        max_output_chars=128,
    )
    result = run_checked(configured, [interpreter, "-c", "print('x' * 10000)"], str(root))
    assert result["exit_code"] == 0
    assert result["output_truncated"]
    assert len(result["output"]) < 200


def test_command_timeout_kills_process_group(readonly, root):
    """Timed-out commands report termination rather than hanging."""
    from shutil import which
    interpreter = "python3" if which("python3") else "python"
    configured = replace(
        readonly, enable_commands=True, allowed_commands=(interpreter,),
        command_timeout_seconds=1,
    )
    result = run_checked(configured, [interpreter, "-c", "import time;time.sleep(10)"], str(root))
    assert result["timeout"] is True
