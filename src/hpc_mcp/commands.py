"""Opt-in command execution with argv-only invocation and bounded outputs."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import threading
import subprocess
import time
import uuid

from .config import Settings
from .security import limited, resolve_path


def checked_argv(settings: Settings, argv: list[str]) -> list[str]:
    """Enforce the explicitly configured executable basename allowlist."""
    if not settings.enable_commands:
        raise PermissionError("Command execution is disabled")
    if not argv or not all(isinstance(item, str) and item and "\x00" not in item for item in argv):
        raise ValueError("argv must be a non-empty list of non-empty strings")
    if argv[0] != Path(argv[0]).name:
        raise PermissionError("Commands must use allowlisted names, not executable paths")
    binary = argv[0]
    if binary not in settings.allowed_commands:
        raise PermissionError(f"Command not allowed: {binary}")
    # User opt-in is deliberately required; some allowed binaries execute arbitrary code.
    return argv


def checked_environment(settings: Settings, env_overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Apply only environment variables approved by the per-user policy."""
    if env_overrides is None:
        env_overrides = {}
    if not isinstance(env_overrides, dict) or len(env_overrides) > 24:
        raise ValueError("env_overrides must be a dictionary of at most 24 entries")
    for name, value in env_overrides.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("Invalid environment variable name")
        if name not in settings.allowed_environment_variables:
            raise PermissionError(f"Environment variable not allowed: {name}")
        if not isinstance(value, str) or len(value) > 2048 or "\x00" in value or "\n" in value:
            raise ValueError("Environment values must be short, single-line strings")
    return {**os.environ, **env_overrides, "GIT_TERMINAL_PROMPT": "0"}


def available_commands(settings: Settings) -> dict:
    """Report approved commands that are visible on the service PATH."""
    return {
        "commands": [
            {"name": name, "path": shutil.which(name), "available": shutil.which(name) is not None}
            for name in settings.allowed_commands
        ],
        "env_allowlist": list(settings.allowed_environment_variables),
        "command_timeout_seconds": settings.command_timeout_seconds,
        "max_background_sessions": settings.max_background_sessions,
    }


def run_checked(
    settings: Settings, argv: list[str], cwd: str,
    env_overrides: dict[str, str] | None = None,
) -> dict:
    """Execute a configured binary without shell interpretation or interactive input."""
    checked_argv(settings, argv)
    working_dir = resolve_path(settings, cwd)
    if not working_dir.is_dir():
        raise NotADirectoryError(str(working_dir))
    # Disk-backed output avoids unbounded memory use by verbose applications.
    import tempfile
    with tempfile.TemporaryFile(mode="w+b") as output:
        process = subprocess.Popen(
            argv, cwd=working_dir, stdin=subprocess.DEVNULL, stdout=output,
            stderr=subprocess.STDOUT, start_new_session=True, close_fds=True,
            env=checked_environment(settings, env_overrides),
        )
        try:
            code = process.wait(timeout=settings.command_timeout_seconds)
        except subprocess.TimeoutExpired:
            # Terminate the entire detached group, not only its immediate parent.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            return {"timeout": True, "message": "Process group exceeded timeout and was stopped"}
        output.seek(0)
        captured = output.read(settings.max_output_chars * 4 + 1)
        output.seek(0, os.SEEK_END)
        total_bytes = output.tell()
        text = captured.decode("utf-8", errors="replace")
        return {
            "exit_code": code,
            "output": limited(text, settings.max_output_chars),
            "output_truncated": total_bytes > len(captured) or len(text) > settings.max_output_chars,
        }


def session_dir() -> Path:
    """Create a private metadata directory for background process sessions."""
    path = Path.home() / ".local" / "state" / "hpc-mcp" / "sessions"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _linux_start_time(pid: int) -> str | None:
    """Read the Linux process creation tick to avoid PID-reuse confusion."""
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
        fields = data.rsplit(") ", 1)[1].split()
        if fields[0] in ("Z", "X"):
            return None
        return fields[19]
    except (OSError, IndexError):
        return None


def _get_session(identifier: str) -> dict:
    """Load an opaque, locally owned session record."""
    if not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Invalid session id")
    path = session_dir() / f"{identifier}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _alive(record: dict) -> bool:
    """Require both the PID and its creation tick to match the recorded process."""
    return _linux_start_time(record["pid"]) == record["start_ticks"]


def _record_exit_status(process: subprocess.Popen, identifier: str) -> None:
    """Reap a finished subprocess and store its exit status for later inspection."""
    code = process.wait()
    path = session_dir() / f"{identifier}.exit.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"exit_code": code}), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def start_process(
    settings: Settings, argv: list[str], cwd: str,
    env_overrides: dict[str, str] | None = None,
) -> dict:
    """Start a detached user-owned process with a private bounded-observation log."""
    checked_argv(settings, argv)
    working_dir = resolve_path(settings, cwd)
    if not working_dir.is_dir():
        raise NotADirectoryError(str(working_dir))
    directory = session_dir()
    active = 0
    for metadata in directory.glob("*.json"):
        try:
            if _alive(json.loads(metadata.read_text(encoding="utf-8"))):
                active += 1
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if active >= settings.max_background_sessions:
        raise RuntimeError("Too many background sessions")
    identifier = uuid.uuid4().hex
    log_path = directory / f"{identifier}.log"
    with log_path.open("xb") as stream:
        process = subprocess.Popen(
            argv, cwd=working_dir, stdin=subprocess.DEVNULL, stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True, close_fds=True,
            env=checked_environment(settings, env_overrides),
        )
    # /proc is populated just after fork/exec.
    start_ticks = None
    for _ in range(20):
        start_ticks = _linux_start_time(process.pid)
        if start_ticks:
            break
        time.sleep(0.01)
    record = {
        "id": identifier, "pid": process.pid, "start_ticks": start_ticks,
        "argv": argv, "cwd": str(working_dir), "created_epoch": time.time(),
    }
    (directory / f"{identifier}.json").write_text(json.dumps(record), encoding="utf-8")
    os.chmod(directory / f"{identifier}.json", 0o600)
    threading.Thread(
        target=_record_exit_status, args=(process, identifier), daemon=True,
    ).start()
    return {"session_id": identifier, "pid": process.pid, "state": "started"}


def process_output(settings: Settings, session_id: str, offset_bytes: int = 0) -> dict:
    """Read a capped byte range of a session log for incremental polling."""
    record = _get_session(session_id)
    path = session_dir() / f"{session_id}.log"
    length = min(settings.max_output_chars * 2, 100_000)
    with path.open("rb") as handle:
        handle.seek(max(0, offset_bytes))
        data = handle.read(length)
        next_offset = handle.tell()
    exit_path = session_dir() / f"{session_id}.exit.json"
    exit_code = json.loads(exit_path.read_text(encoding="utf-8"))["exit_code"] if exit_path.exists() else None
    return {
        "session_id": session_id, "pid": record["pid"],
        "running": _alive(record), "exit_code": exit_code,
        "next_offset_bytes": next_offset,
        "output": limited(data.decode("utf-8", errors="replace"), settings.max_output_chars),
    }


def terminate_process(settings: Settings, session_id: str) -> dict:
    """Send SIGTERM only to a matching process group created by this MCP server."""
    if not settings.enable_commands:
        raise PermissionError("Command execution is disabled")
    record = _get_session(session_id)
    if not _alive(record):
        return {"session_id": session_id, "signal_sent": False, "reason": "not running"}
    os.killpg(record["pid"], signal.SIGTERM)
    return {"session_id": session_id, "signal_sent": True}


def scheduler_jobs(settings: Settings) -> dict:
    """List the current user's jobs in a scheduler-neutral response."""
    from .schedulers import get_scheduler
    return get_scheduler(settings).list_jobs(settings)


def scheduler_submit(settings: Settings, script_path: str) -> dict:
    """Submit an existing batch script using the configured scheduler."""
    permitted = settings.enable_scheduler_submit or (
        settings.scheduler_type == "slurm" and settings.enable_slurm_submit
    )
    if not settings.enable_commands or not permitted:
        raise PermissionError("Scheduler submission is disabled")
    from .schedulers import get_scheduler
    return get_scheduler(settings).submit(settings, script_path)


def scheduler_detail(settings: Settings, job_id: str) -> dict:
    """Read one job's scheduler metadata."""
    from .schedulers import get_scheduler
    return get_scheduler(settings).job_detail(settings, job_id)


def scheduler_cancel(settings: Settings, job_id: str) -> dict:
    """Cancel a job only if the user enabled this separate mutating capability."""
    if not settings.enable_commands or not settings.enable_scheduler_cancel:
        raise PermissionError("Scheduler cancellation is disabled")
    from .schedulers import get_scheduler
    return get_scheduler(settings).cancel(settings, job_id)


def slurm_jobs(settings: Settings) -> dict:
    """Legacy Slurm-only view for existing MCP clients."""
    from .schedulers.slurm import SlurmScheduler
    result = SlurmScheduler().list_jobs(settings)
    if "error" in result:
        return {"error": result["error"], "exit_code": result.get("exit_code", 1)}
    return {
        "user": result["user"],
        "jobs": [[job[key] for key in (
            "job_id", "queue", "name", "state", "elapsed", "nodes", "reason"
        )] for job in result["jobs"]],
    }


def slurm_submit(settings: Settings, script_path: str) -> dict:
    """Legacy Slurm-only submission for existing MCP clients."""
    if not settings.enable_commands or not (settings.enable_slurm_submit or settings.enable_scheduler_submit):
        raise PermissionError("Slurm submission is disabled")
    from .schedulers.slurm import SlurmScheduler
    result = SlurmScheduler().submit(settings, script_path)
    return {key: result[key] for key in ("exit_code", "stdout", "stderr")}


def git_status(settings: Settings, repo_path: str) -> dict:
    """Inspect Git status without prompting or modifying tracked files."""
    directory = resolve_path(settings, repo_path)
    result = subprocess.run(
        ["git", "-C", str(directory), "--no-pager", "status", "--short"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
    )
    return {"exit_code": result.returncode, "output": limited(result.stdout or result.stderr, settings.max_output_chars)}


def git_diff(settings: Settings, repo_path: str) -> dict:
    """Read a bounded repository diff without shell interpolation."""
    directory = resolve_path(settings, repo_path)
    result = subprocess.run(
        ["git", "-C", str(directory), "--no-pager", "diff", "--no-ext-diff"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
    )
    return {"exit_code": result.returncode, "output": limited(result.stdout or result.stderr, settings.max_output_chars)}