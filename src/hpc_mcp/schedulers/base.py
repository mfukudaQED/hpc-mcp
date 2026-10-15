"""Shared types and validation for user-scoped HPC schedulers."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Protocol

from ..config import Settings
from ..security import limited, resolve_path


JOB_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\[\]-]{0,127}")


def checked_job_id(job_id: str) -> str:
    """Reject options, whitespace, and shell operators in scheduler job IDs."""
    if not isinstance(job_id, str) or not JOB_ID_PATTERN.fullmatch(job_id):
        raise ValueError("Invalid scheduler job ID")
    return job_id


def checked_script(settings: Settings, script_path: str) -> Path:
    """Require an existing batch script in an approved filesystem root."""
    script = resolve_path(settings, script_path)
    if not script.is_file() or script.stat().st_size > settings.max_file_bytes:
        raise ValueError("Invalid batch script")
    return script


def binary(settings: Settings, name: str) -> str:
    """Find scheduler binaries in a site-specific directory or service PATH."""
    directory = settings.scheduler_bin_dir or (settings.slurm_bin_dir if settings.scheduler_type == "slurm" else None)
    if directory is None:
        return name
    return str(directory / name)


def execute(settings: Settings, argv: list[str], *, cwd: Path | None = None, timeout: int = 15) -> dict:
    """Execute a scheduler command directly, returning bounded output."""
    try:
        result = subprocess.run(
            argv, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "stdout": "", "stderr": "Scheduler command timed out"}
    except FileNotFoundError:
        return {"exit_code": 127, "stdout": "", "stderr": "Scheduler executable not found"}
    return {
        "exit_code": result.returncode,
        "stdout": limited(result.stdout.strip(), settings.max_output_chars),
        "stderr": limited(result.stderr.strip(), settings.max_output_chars),
    }


class Scheduler(Protocol):
    """Interface implemented by one scheduler adapter."""

    name: str

    def list_jobs(self, settings: Settings) -> dict: ...
    def submit(self, settings: Settings, script_path: str) -> dict: ...
    def job_detail(self, settings: Settings, job_id: str) -> dict: ...
    def cancel(self, settings: Settings, job_id: str) -> dict: ...
