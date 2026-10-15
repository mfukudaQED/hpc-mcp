"""Test optional Slurm batch submission without submitting real jobs."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import subprocess

import pytest

from hpc_mcp.commands import slurm_jobs, slurm_submit
from hpc_mcp.config import load_settings
from hpc_mcp.server import build_server


def test_submit_preserves_script_node_directives(monkeypatch, readonly, root):
    """The submission tool does not inject an MCP-specific node cap."""
    script = root / "job.sbatch"
    script.write_text("#!/bin/bash\n#SBATCH --nodes=8\nhostname\n")
    policy = replace(readonly, enable_commands=True, enable_slurm_submit=True)
    calls = []

    def fake_run(argv, **kwargs):
        """Observe submission arguments without scheduling a job."""
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "12345", "")

    monkeypatch.setattr("hpc_mcp.commands.subprocess.run", fake_run)
    result = slurm_submit(policy, str(script))
    assert result == {"exit_code": 0, "stdout": "12345", "stderr": ""}
    assert calls[0][0] == ["sbatch", "--parsable", str(script)]
    assert calls[0][1]["cwd"] == script.parent


def test_submit_requires_opt_in(readonly, root):
    """Submitting is denied unless the local user enables Slurm tools."""
    script = root / "job.sbatch"
    script.write_text("#!/bin/bash\nhostname\n")
    with pytest.raises(PermissionError):
        slurm_submit(readonly, str(script))


def test_submit_tool_opt_in(readonly):
    """The Slurm submit tool appears only with explicitly enabled permissions."""
    off = {tool.name for tool in asyncio.run(build_server(readonly).list_tools())}
    assert "submit_slurm_script" not in off
    policy = replace(readonly, enable_commands=True, enable_slurm_submit=True)
    on = {tool.name for tool in asyncio.run(build_server(policy).list_tools())}
    assert "submit_slurm_script" in on


def test_slurm_binary_directory_override(monkeypatch, readonly, root, tmp_path):
    """Slurm executables can be located with a restricted service PATH."""
    binary_dir = tmp_path / "slurm-bin"
    binary_dir.mkdir()
    config = tmp_path / "config.toml"
    config.write_text(
        f'[filesystem]\nroots = ["{root}"]\n[slurm]\n'
        f'bin_dir = "{binary_dir}"\n'
    )
    assert load_settings(config).slurm_bin_dir == binary_dir
    script = root / "job.sbatch"
    script.write_text("#!/bin/bash\n#SBATCH --nodes=2\nhostname\n")
    policy = replace(
        readonly, enable_commands=True, enable_slurm_submit=True,
        slurm_bin_dir=binary_dir,
    )
    calls = []

    def fake_run(argv, **kwargs):
        """Record Slurm commands without invoking the scheduler."""
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "12345", "")

    monkeypatch.setattr("hpc_mcp.commands.subprocess.run", fake_run)
    slurm_submit(policy, str(script))
    slurm_jobs(policy)
    assert calls[0] == [str(binary_dir / "sbatch"), "--parsable", str(script)]
    assert calls[1][0] == str(binary_dir / "squeue")
