"""Verify Slurm and PBS adapters without running a real scheduler."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import subprocess

import pytest

from hpc_mcp.commands import scheduler_cancel, scheduler_detail, scheduler_jobs, scheduler_submit
from hpc_mcp.config import load_settings
from hpc_mcp.server import build_server


def _mock_subprocess(monkeypatch, output, *, exit_code=0):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, exit_code, output, "")
    monkeypatch.setattr("hpc_mcp.schedulers.base.subprocess.run", fake_run)
    return calls


def test_pbs_list_normalized(monkeypatch, readonly):
    """PBS qstat -u reports only our username and normalized fields."""
    import getpass
    user = getpass.getuser()
    output = (
        "header text\n"
        "Job ID Username Queue Jobname SessID NDS TSK Memory Time S Time\n"
        "-------------------------------------------------------------\n"
        f"123.server {user} workq benzene -- 2 32 -- 01:00:00 R 00:02\n"
        "124.server someone_else workq test -- 1 1 -- 00:05:00 Q --\n"
        f"125.server {user} fastq chain -- 1 8 -- 00:10:00 Q --\n"
    )
    calls = _mock_subprocess(monkeypatch, output)
    policy = replace(readonly, scheduler_type="pbs")
    result = scheduler_jobs(policy)
    assert result["scheduler"] == "pbs"
    assert [job["job_id"] for job in result["jobs"]] == ["123.server", "125.server"]
    assert [job["state"] for job in result["jobs"]] == ["R", "Q"]
    assert calls[0][0] == ["qstat", "-u", user]


def test_slurm_list_normalized(monkeypatch, readonly):
    """Slurm output is converted into the same job structure."""
    import getpass
    user = getpass.getuser()
    calls = _mock_subprocess(monkeypatch, "120|sham|benzene|RUNNING|1:23|2|node01\n")
    result = scheduler_jobs(replace(readonly, scheduler_type="slurm"))
    assert result["jobs"][0]["job_id"] == "120"
    assert result["jobs"][0]["nodes"] == "2"
    assert result["jobs"][0]["scheduler"] == "slurm"
    assert calls[0][0][:4] == ["squeue", "-h", "-u", user]


@pytest.mark.parametrize("backend,expected_command", [
    ("pbs", "qsub"), ("slurm", "sbatch")
])
def test_scheduler_submit_with_mock(monkeypatch, readonly, root, backend, expected_command):
    """Submitting is opt-in and leaves resource requests to Slurm/PBS."""
    policy = replace(
        readonly, scheduler_type=backend,
        enable_commands=True, enable_scheduler_submit=True,
    )
    script = root / "job.sh"
    script.write_text("#!/bin/bash\n#PBS -l select=8:ncpus=8\n#SBATCH --nodes=8\nhostname\n")
    job_id = "442.server" if backend == "pbs" else "442"
    calls = _mock_subprocess(monkeypatch, job_id + "\n")
    result = scheduler_submit(policy, str(script))
    assert result["job_id"] == job_id
    assert result["scheduler"] == backend
    assert calls[0][0][0] == expected_command
    assert calls[0][0][-1] == str(script)
    assert "--nodes=" not in " ".join(calls[0][0])


def test_scheduler_detail_and_cancel(monkeypatch, readonly):
    """Detail is read-only while cancellation is a separate opt-in."""
    policy = replace(readonly, scheduler_type="pbs")
    calls = _mock_subprocess(monkeypatch, "Job Id: 123.server\n")
    assert scheduler_detail(policy, "123.server")["exit_code"] == 0
    assert calls[0][0] == ["qstat", "-f", "123.server"]
    with pytest.raises(PermissionError):
        scheduler_cancel(policy, "123.server")
    with pytest.raises(ValueError):
        scheduler_detail(policy, "--everything")
    enabled = replace(policy, enable_commands=True, enable_scheduler_cancel=True)
    assert scheduler_cancel(enabled, "123.server")["exit_code"] == 0
    assert calls[-1][0] == ["qdel", "123.server"]


def test_config_scheduler_choice(tmp_path, root):
    """Scheduler type validates and can point to an absolute binary directory."""
    config = tmp_path / "config.toml"
    bindir = tmp_path / "pbs_bin"
    bindir.mkdir()
    config.write_text(
        f'[filesystem]\nroots = ["{root}"]\n'
        f'[scheduler]\ntype = "pbs"\nbin_dir = "{bindir}"\n'
        '[permissions]\nenable_commands = true\nenable_scheduler_submit = true\n'
    )
    policy = load_settings(config)
    assert policy.scheduler_type == "pbs"
    assert policy.scheduler_bin_dir == bindir
    names = {tool.name for tool in asyncio.run(build_server(policy).list_tools())}
    assert "scheduler_list_jobs" in names
    assert "scheduler_submit_script" in names
    assert "slurm_list_jobs" not in names
    assert "submit_slurm_script" not in names
    config.write_text(f'[filesystem]\nroots = ["{root}"]\n[scheduler]\ntype = "unknown"\n')
    with pytest.raises(ValueError):
        load_settings(config)


def test_legacy_slurm_still_registered(readonly):
    """Older users keep legacy Slurm tools alongside generic tools."""
    policy = replace(readonly, enable_commands=True, enable_slurm_submit=True)
    names = {tool.name for tool in asyncio.run(build_server(policy).list_tools())}
    assert {"slurm_list_jobs", "submit_slurm_script", "scheduler_list_jobs",
            "scheduler_submit_script", "scheduler_job_detail"} <= names


def test_scheduler_none_disables_tool_discovery(readonly):
    """A machine without a scheduler does not advertise scheduler tools."""
    policy = replace(readonly, scheduler_type="none")
    names = {tool.name for tool in asyncio.run(build_server(policy).list_tools())}
    assert "scheduler_list_jobs" not in names
    assert "slurm_list_jobs" not in names

def test_pbs_never_inherits_legacy_slurm_submit(readonly, root, tmp_path):
    """Old Slurm permission must not silently allow PBS mutations."""
    config = tmp_path / "pbs.toml"
    config.write_text(
        f'[filesystem]\nroots = ["{root}"]\n'
        '[scheduler]\ntype = "pbs"\n'
        '[permissions]\nenable_commands = true\nenable_slurm_submit = true\n'
    )
    parsed = load_settings(config)
    assert not parsed.enable_scheduler_submit
    names = {tool.name for tool in asyncio.run(build_server(parsed).list_tools())}
    assert "scheduler_submit_script" not in names
    with pytest.raises(PermissionError):
        scheduler_submit(parsed, str(root / "none.sbatch"))


def test_cancel_tool_needs_separate_permission(readonly):
    """Cancellation is not exposed by a submit-only opt-in."""
    submit_only = replace(readonly, enable_commands=True, enable_scheduler_submit=True)
    names = {tool.name for tool in asyncio.run(build_server(submit_only).list_tools())}
    assert "scheduler_cancel_job" not in names
    enabled = replace(submit_only, enable_scheduler_cancel=True)
    names = {tool.name for tool in asyncio.run(build_server(enabled).list_tools())}
    assert "scheduler_cancel_job" in names
