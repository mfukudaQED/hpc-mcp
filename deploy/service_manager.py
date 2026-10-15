#!/usr/bin/env python3
"""Manage per-user Tunnel startup through systemd or cron without root access."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


MARKER_START = "# BEGIN HPC-MCP MANAGED TUNNEL"
MARKER_END = "# END HPC-MCP MANAGED TUNNEL"


def run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run a short local management command as the current, non-root user."""
    return subprocess.run(
        args, input=input_text, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=15, check=False,
    )


def require_unprivileged() -> None:
    """Refuse running this installer with root or a changed effective UID."""
    if os.getuid() == 0 or os.geteuid() == 0 or os.getuid() != os.geteuid():
        raise PermissionError("Run hpc-mcp as the ordinary Linux user; root is forbidden")


def has_linger() -> bool:
    """Report whether logind keeps this user's manager after logout."""
    if not shutil.which("loginctl"):
        return False
    result = run(["loginctl", "show-user", str(os.getuid()), "-p", "Linger", "--value"])
    return result.returncode == 0 and result.stdout.strip().lower() == "yes"


def systemd_usable() -> bool:
    """Check a responsive user manager and logout persistence."""
    if not has_linger() or not shutil.which("systemctl"):
        return False
    return run(["systemctl", "--user", "show-environment"]).returncode == 0


def cron_usable() -> bool:
    """Require both a personal crontab interface and an active scheduler."""
    if not shutil.which("crontab") or not shutil.which("systemctl"):
        return False
    return run(["systemctl", "is-active", "crond"]).stdout.strip() == "active"


def choose_backend(requested: str) -> str:
    """Resolve auto, explicit, and disabled service modes."""
    if requested == "none":
        return "none"
    if requested == "systemd":
        if not systemd_usable():
            raise RuntimeError("systemd --user unavailable or Linger is not enabled")
        return "systemd"
    if requested == "cron":
        if not cron_usable():
            raise RuntimeError("cron is not available to this unprivileged user")
        return "cron"
    if systemd_usable():
        return "systemd"
    if cron_usable():
        return "cron"
    raise RuntimeError("Neither persistent systemd --user nor cron is available")


def check_tunnel_files(home: Path) -> None:
    """Ensure private credentials and a configured Tunnel exist before activation."""
    env_file = home / ".config/hpc-mcp/tunnel.env"
    profile = home / ".config/tunnel-client/hpc-mcp.yaml"
    binary = home / ".local/bin/tunnel-client"
    for file in (env_file, profile):
        if not file.is_file() or file.is_symlink():
            raise RuntimeError(f"Required regular file is missing or symlinked: {file}")
        if file.stat().st_uid != os.getuid() or file.stat().st_mode & 0o077:
            raise PermissionError(f"File must belong to user and be private (0600): {file}")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError(f"Tunnel client executable not found: {binary}")


def user_service_active() -> bool:
    """Check whether the managed per-user service is already running."""
    if not shutil.which("systemctl"):
        return False
    return run(["systemctl", "--user", "is-active", "hpc-mcp-tunnel.service"]).stdout.strip() == "active"


def install_systemd(project: Path, home: Path) -> None:
    """Install and start the existing user service without disrupting active units."""
    if cron_managed():
        raise RuntimeError("Managed cron schedule exists; uninstall cron first")
    source = project / "deploy/hpc-mcp-tunnel.service"
    destination = home / ".config/systemd/user/hpc-mcp-tunnel.service"
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not destination.exists() or destination.read_bytes() != source.read_bytes():
        shutil.copyfile(source, destination)
        destination.chmod(0o600)
    for args in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "hpc-mcp-tunnel.service"],
    ):
        result = run(args)
        if result.returncode:
            raise RuntimeError(f"{args[2]} failed: {result.stderr.strip()}")
    if not user_service_active():
        result = run(["systemctl", "--user", "start", "hpc-mcp-tunnel.service"])
        if result.returncode:
            raise RuntimeError(f"Service startup failed: {result.stderr.strip()}")


def current_crontab() -> str:
    """Read user's crontab; distinguish no entries from a real failure."""
    result = run(["crontab", "-l"])
    if result.returncode == 0:
        return result.stdout
    if result.returncode == 1 and "no crontab" in result.stderr.lower():
        return ""
    raise RuntimeError(f"Cannot read crontab: {result.stderr.strip()}")


def remove_managed_block(contents: str) -> str:
    """Remove only this application's paired marker block."""
    if contents.count(MARKER_START) != contents.count(MARKER_END):
        raise ValueError("Malformed managed crontab markers")
    if contents.count(MARKER_START) > 1:
        raise ValueError("Duplicated managed crontab markers")
    if MARKER_START not in contents:
        return contents
    before, rest = contents.split(MARKER_START, 1)
    _, after = rest.split(MARKER_END, 1)
    return before + after.lstrip("\n")


def cron_managed() -> bool:
    """Check for a managed cron entry without modifying the crontab."""
    if not shutil.which("crontab"):
        return False
    return MARKER_START in current_crontab()


def update_crontab(contents: str) -> None:
    """Install a full crontab, preserving all unrelated entries."""
    result = run(["crontab", "-"], input_text=contents)
    if result.returncode:
        raise RuntimeError(f"crontab update failed: {result.stderr.strip()}")


def install_cron(project: Path, home: Path) -> None:
    """Add two narrowly scoped cron entries without clobbering other jobs."""
    if user_service_active():
        raise RuntimeError("systemd tunnel is active; refusing duplicate cron tunnel")
    paths = [str(project / ".venv/bin/python"), str(project / "deploy/cron_watchdog.py")]
    if not Path(paths[0]).is_file():
        raise RuntimeError(f"Project venv Python missing: {paths[0]}")
    if any(any(c in value for c in ("\n", "\r", "%")) for value in paths):
        raise ValueError("Unsafe characters in cron command paths")
    import shlex
    action = " ".join(shlex.quote(value) for value in paths) + " start"
    managed = (
        MARKER_START + "\n"
        + "@reboot " + action + "\n"
        + "*/5 * * * * " + action + "\n"
        + MARKER_END + "\n"
    )
    existing = remove_managed_block(current_crontab()).rstrip("\n")
    update_crontab((existing + "\n" if existing else "") + managed)
    result = run([paths[0], paths[1], "start"])
    if result.returncode:
        raise RuntimeError(f"Initial cron watchdog launch failed: {result.stderr.strip()}")


def remove_cron(project: Path) -> None:
    """Remove managed entries and stop only the watchdog-owned process."""
    if shutil.which("crontab") and cron_managed():
        previous = current_crontab()
        updated = remove_managed_block(previous)
        update_crontab(updated)
    executable = project / ".venv/bin/python"
    watchdog = project / "deploy/cron_watchdog.py"
    if executable.is_file() and watchdog.is_file():
        result = run([str(executable), str(watchdog), "stop"])
        if result.returncode:
            raise RuntimeError(result.stderr.strip())


def status() -> None:
    """Print relevant non-sensitive user service state."""
    print(f"Linger={'yes' if has_linger() else 'no'}")
    print(f"systemd_usable={systemd_usable()}")
    print(f"cron_usable={cron_usable()}")
    print(f"systemd_active={user_service_active()}")
    print(f"cron_managed={cron_managed()}")


def main() -> int:
    """Install, inspect, or remove a per-user service backend."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("auto", "systemd", "cron", "none"), default="auto")
    parser.add_argument("--action", choices=("activate", "status", "remove-cron"), default="status")
    args = parser.parse_args()
    require_unprivileged()
    project = Path(__file__).resolve().parent.parent
    home = Path.home()
    try:
        if args.action == "status":
            status()
        elif args.action == "remove-cron":
            remove_cron(project)
            print("Removed only HPC-MCP cron entries and associated tunnel process")
        else:
            backend = choose_backend(args.backend)
            if backend == "none":
                print("No automatic startup backend selected")
                return 0
            check_tunnel_files(home)
            if backend == "systemd":
                install_systemd(project, home)
            else:
                install_cron(project, home)
            print(f"Backend activated: {backend}")
        return 0
    except (OSError, RuntimeError, PermissionError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"hpc-mcp service manager: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
