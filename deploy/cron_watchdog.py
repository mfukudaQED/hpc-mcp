#!/usr/bin/env python3
"""Cron watchdog for a user-owned Secure MCP Tunnel (no privileges or shell)."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


def assert_unprivileged() -> None:
    """Refuse execution as root or through a setuid context."""
    if os.getuid() == 0 or os.geteuid() == 0 or os.getuid() != os.geteuid():
        raise PermissionError("The Tunnel watchdog must run as a normal Linux user")


def private_state_dir() -> Path:
    """Create a user-only directory for PID records, lock, and logs."""
    directory = Path.home() / ".local/state/hpc-mcp/cron"
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        raise PermissionError("Invalid watchdog state directory")
    return directory


def start_ticks(pid: int) -> str | None:
    """Return process start ticks only while the process is not a zombie."""
    try:
        parts = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(") ", 1)[1].split()
        if parts[0] in ("Z", "X"):
            return None
        return parts[19]
    except (OSError, IndexError):
        return None


def record_matches(record: dict) -> bool:
    """Prevent PID reuse and prevent signaling unrelated processes."""
    try:
        pid = int(record["pid"])
        if pid <= 1 or start_ticks(pid) != str(record["start_ticks"]):
            return False
        if os.getpgid(pid) != pid:
            return False
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        return argv[0].decode("utf-8") == record["executable"]
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        return False


def load_record(directory: Path) -> dict:
    """Load previously created process metadata, if valid."""
    try:
        return json.loads((directory / "tunnel.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def store_record(directory: Path, record: dict) -> None:
    """Replace PID metadata atomically, keeping it private to the user."""
    path = directory / "tunnel.json"
    tmp = directory / "tunnel.json.tmp"
    with tmp.open("w", encoding="utf-8") as handle:
        os.chmod(tmp, 0o600)
        json.dump(record, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read_key() -> str:
    """Read the private EnvironmentFile without invoking a shell."""
    env_file = Path.home() / ".config/hpc-mcp/tunnel.env"
    if not env_file.is_file() or env_file.is_symlink():
        raise RuntimeError("Private Tunnel EnvironmentFile is missing")
    info = env_file.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("Tunnel EnvironmentFile must be owned by user with mode 0600")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        match = re.fullmatch(r"(?:export\s+)?CONTROL_PLANE_API_KEY\s*=\s*(.*)", line)
        if match:
            value = match.group(1).strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            if not value.startswith("sk-") or any(ch.isspace() for ch in value):
                raise ValueError("Tunnel API key format is invalid")
            return value
    raise RuntimeError("CONTROL_PLANE_API_KEY is not set")


def launch(directory: Path) -> dict:
    """Start one Tunnel client detached from cron's standard streams."""
    binary = Path.home() / ".local/bin/tunnel-client"
    profile = Path.home() / ".config/tunnel-client/hpc-mcp.yaml"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("tunnel-client is missing or not executable")
    if not profile.is_file() or profile.is_symlink():
        raise RuntimeError("Tunnel profile missing or unsafe")
    if profile.stat().st_uid != os.getuid() or profile.stat().st_mode & 0o077:
        raise PermissionError("Tunnel profile must be owned by user and private")
    key = read_key()
    log = directory / "tunnel.log"
    if log.exists() and log.stat().st_size > 2 * 1024 * 1024:
        log.unlink()
    with log.open("ab") as stream:
        os.chmod(log, 0o600)
        process = subprocess.Popen(
            [str(binary), "run", "--profile", "hpc-mcp", "--health.listen-addr=127.0.0.1:0"],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
            env={**os.environ, "CONTROL_PLANE_API_KEY": key},
            start_new_session=True, close_fds=True, cwd=Path.home(),
        )
    ticks = None
    for _ in range(20):
        ticks = start_ticks(process.pid)
        if ticks:
            break
        time.sleep(0.01)
    if not ticks:
        raise RuntimeError("Tunnel did not create an observable process")
    record = {"pid": process.pid, "start_ticks": ticks, "executable": str(binary)}
    store_record(directory, record)
    return record


def execute(action: str) -> dict:
    """Lock one startup/shutdown operation to prevent duplicate Tunnel processes."""
    assert_unprivileged()
    directory = private_state_dir()
    with (directory / "tunnel.lock").open("a+") as stream:
        os.chmod(directory / "tunnel.lock", 0o600)
        fcntl.flock(stream, fcntl.LOCK_EX)
        record = load_record(directory)
        running = record_matches(record)
        if action == "status":
            return {"running": running, "pid": record.get("pid") if running else None}
        if action == "stop":
            if running:
                os.killpg(int(record["pid"]), signal.SIGTERM)
            (directory / "tunnel.json").unlink(missing_ok=True)
            return {"stopped": running}
        if action == "start":
            if running:
                return {"running": True, "pid": record["pid"], "already_running": True}
            record = launch(directory)
            return {"running": True, "pid": record["pid"], "already_running": False}
        raise ValueError("Unknown action")


def main() -> int:
    """Run an idempotent cron watchdog action."""
    if len(sys.argv) != 2 or sys.argv[1] not in ("start", "stop", "status"):
        print("Usage: cron_watchdog.py {start|stop|status}", file=sys.stderr)
        return 2
    try:
        print(json.dumps(execute(sys.argv[1])))
        return 0
    except (OSError, ValueError, RuntimeError, PermissionError) as error:
        print(f"hpc-mcp watchdog: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
