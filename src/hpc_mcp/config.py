"""Load per-user policy with a secure, read-only default."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import tomllib


@dataclass(frozen=True)
class SiteTool:
    """One locally configured fixed-argument command exposed as an MCP tool."""

    name: str
    description: str
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int


@dataclass(frozen=True)
class Settings:
    """Immutable effective configuration for one Linux user."""

    roots: tuple[Path, ...]
    enable_writes: bool = False
    enable_commands: bool = False
    enable_slurm_submit: bool = False
    enable_scheduler_submit: bool = False
    enable_scheduler_cancel: bool = False
    enable_site_tools: bool = False
    scheduler_type: str = "slurm"
    scheduler_bin_dir: Path | None = None
    site_tools: tuple[SiteTool, ...] = ()
    allowed_commands: tuple[str, ...] = ("hostname", "whoami", "pwd", "date", "uptime")
    max_file_bytes: int = 2 * 1024 * 1024
    max_output_chars: int = 16_000
    command_timeout_seconds: int = 30
    max_background_sessions: int = 4
    slurm_bin_dir: Path | None = None


def load_settings(path: Path | None = None) -> Settings:
    """Parse TOML from the caller's home directory without escalating privilege."""
    config_path = path or Path(os.environ.get("HPC_MCP_CONFIG", "~/.config/hpc-mcp/config.toml")).expanduser()
    config = {}
    if config_path.is_file():
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    fs = config.get("filesystem", {})
    permissions = config.get("permissions", {})
    limits = config.get("limits", {})
    commands = config.get("commands", {})
    slurm = config.get("slurm", {})
    scheduler = config.get("scheduler", {})
    if not isinstance(scheduler, dict):
        raise ValueError("scheduler must be a TOML table")
    scheduler_type = scheduler.get("type", "slurm")
    if scheduler_type not in ("slurm", "pbs", "none"):
        raise ValueError("scheduler.type must be slurm, pbs or none")
    raw_slurm_bin = slurm.get("bin_dir", "")
    if not isinstance(raw_slurm_bin, str):
        raise ValueError("slurm.bin_dir must be a directory path string")
    slurm_bin_dir = Path(raw_slurm_bin).expanduser().resolve() if raw_slurm_bin else None
    raw_scheduler_bin = scheduler.get("bin_dir", raw_slurm_bin if scheduler_type == "slurm" else "")
    if not isinstance(raw_scheduler_bin, str):
        raise ValueError("scheduler.bin_dir must be a string")
    scheduler_bin_dir = Path(raw_scheduler_bin).expanduser().resolve() if raw_scheduler_bin else None
    if scheduler_bin_dir is not None and not scheduler_bin_dir.is_dir():
        raise ValueError("scheduler.bin_dir must name an existing directory")
    if slurm_bin_dir is not None and not slurm_bin_dir.is_dir():
        raise ValueError("slurm.bin_dir must name an existing directory")
    raw_roots = fs.get("roots", ["~/work"])
    if not isinstance(raw_roots, list) or not raw_roots or not all(isinstance(root, str) for root in raw_roots):
        raise ValueError("filesystem.roots must be a non-empty list of paths")
    roots = tuple(Path(root).expanduser().resolve() for root in raw_roots)
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Configured filesystem root is not a directory: {root}")
    allowed = commands.get("allowlist", ["hostname", "whoami", "pwd", "date", "uptime"])
    if not isinstance(allowed, list) or any(not isinstance(item, str) or not item for item in allowed):
        raise ValueError("commands.allowlist must be a list of command names")
    raw_site_tools = config.get("site_tools", {})
    if not isinstance(raw_site_tools, dict):
        raise ValueError("site_tools must be a TOML table")
    parsed_tools = []
    for name, definition in raw_site_tools.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,48}", name):
            raise ValueError("Invalid site tool name")
        if not isinstance(definition, dict):
            raise ValueError(f"site_tools.{name} must be a TOML table")
        description = definition.get("description", "")
        argv = definition.get("argv")
        if not isinstance(description, str) or not 1 <= len(description) <= 256:
            raise ValueError(f"site_tools.{name}.description must be 1..256 characters")
        if not isinstance(argv, list) or not 1 <= len(argv) <= 32 or not all(
            isinstance(item, str) and 0 < len(item) <= 1024 and "\x00" not in item
            for item in argv
        ):
            raise ValueError(f"site_tools.{name}.argv must be a list of 1..32 fixed strings")
        executable = Path(argv[0])
        if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f"site_tools.{name} requires an executable absolute path")
        if not isinstance(definition.get("read_only", False), bool) or definition.get("read_only") is not True:
            raise ValueError(f"site_tools.{name} must explicitly declare read_only = true")
        raw_cwd = definition.get("cwd", str(roots[0]))
        if not isinstance(raw_cwd, str):
            raise ValueError(f"site_tools.{name}.cwd must be a directory path")
        cwd = Path(raw_cwd).expanduser().resolve()
        if not cwd.is_dir() or not any(cwd.is_relative_to(root) for root in roots):
            raise ValueError(f"site_tools.{name}.cwd must be inside an approved root")
        timeout = definition.get("timeout_seconds", 10)
        if type(timeout) is not int or not 1 <= timeout <= 60:
            raise ValueError(f"site_tools.{name}.timeout_seconds must be 1..60")
        parsed_tools.append(SiteTool(name, description, tuple(argv), cwd, timeout))
    site_tools_enabled = permissions.get("enable_site_tools", False) is True
    # Legacy enable_slurm_submit must not grant PBS submission on a reused config.
    legacy_submit = permissions.get("enable_slurm_submit", False) if scheduler_type == "slurm" else False
    submitted = permissions.get("enable_scheduler_submit", legacy_submit) is True
    settings = Settings(
        roots=roots,
        enable_writes=permissions.get("enable_writes", False) is True,
        enable_commands=permissions.get("enable_commands", False) is True,
        enable_slurm_submit=permissions.get("enable_slurm_submit", False) is True,
        enable_scheduler_submit=submitted,
        enable_scheduler_cancel=permissions.get("enable_scheduler_cancel", False) is True,
        enable_site_tools=site_tools_enabled,
        scheduler_type=scheduler_type,
        scheduler_bin_dir=scheduler_bin_dir,
        site_tools=tuple(parsed_tools),
        allowed_commands=tuple(allowed),
        max_file_bytes=int(limits.get("max_file_bytes", 2 * 1024 * 1024)),
        max_output_chars=int(limits.get("max_output_chars", 16_000)),
        command_timeout_seconds=int(limits.get("command_timeout_seconds", 30)),
        max_background_sessions=int(limits.get("max_background_sessions", 4)),
        slurm_bin_dir=slurm_bin_dir,
    )
    if (settings.enable_scheduler_submit or settings.enable_scheduler_cancel) and not settings.enable_commands:
        raise ValueError("Scheduler submission/cancellation requires command execution opt-in")
    if settings.scheduler_type == "none" and (settings.enable_scheduler_submit or settings.enable_scheduler_cancel):
        raise ValueError("Cannot enable scheduler mutation when scheduler.type = none")
    if settings.max_file_bytes < 1 or not 128 <= settings.max_output_chars <= 100_000:
        raise ValueError("Unsafe limits in configuration")
    if not 1 <= settings.command_timeout_seconds <= 300:
        raise ValueError("command_timeout_seconds must be 1..300")
    if not 1 <= settings.max_background_sessions <= 16:
        raise ValueError("max_background_sessions must be 1..16")
    return settings
