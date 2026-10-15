"""Safety, detection, and idempotence tests for unprivileged startup backends."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest


DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


def load_module(name: str, filename: str):
    """Import the standalone installer scripts without changing PYTHONPATH."""
    spec = importlib.util.spec_from_file_location(name, DEPLOY / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


manager = load_module("hpc_test_service_manager", "service_manager.py")
watchdog = load_module("hpc_test_cron_watchdog", "cron_watchdog.py")


def completed(args, code=0, stdout="", stderr=""):
    """Create a deterministic fake subprocess result."""
    return subprocess.CompletedProcess(args, code, stdout, stderr)


def test_auto_prefers_persistent_systemd(monkeypatch):
    """Linger=yes and a live user manager select systemd."""
    monkeypatch.setattr(manager, "systemd_usable", lambda: True)
    monkeypatch.setattr(manager, "cron_usable", lambda: True)
    assert manager.choose_backend("auto") == "systemd"


def test_auto_falls_back_to_cron(monkeypatch):
    """Linger=no uses cron, not a user manager that dies after logout."""
    monkeypatch.setattr(manager, "systemd_usable", lambda: False)
    monkeypatch.setattr(manager, "cron_usable", lambda: True)
    assert manager.choose_backend("auto") == "cron"
    with pytest.raises(RuntimeError):
        manager.choose_backend("systemd")


def test_auto_fails_closed(monkeypatch):
    """No supported persistence backend is a visible error, not a false success."""
    monkeypatch.setattr(manager, "systemd_usable", lambda: False)
    monkeypatch.setattr(manager, "cron_usable", lambda: False)
    with pytest.raises(RuntimeError):
        manager.choose_backend("auto")
    assert manager.choose_backend("none") == "none"


def test_linger_explicit_yes_only(monkeypatch):
    """Read logind's status and avoid privilege-changing commands."""
    observed = []
    monkeypatch.setattr(manager.shutil, "which", lambda name: "/bin/" + name)
    monkeypatch.setattr(manager, "run", lambda args: (observed.append(args), completed(args, stdout="yes\n"))[1])
    assert manager.has_linger()
    assert observed[0][:2] == ["loginctl", "show-user"]


def test_marker_removal_preserves_user_jobs():
    """An unrelated scheduled job remains byte-identical after uninstall."""
    user_jobs = "MAILTO=research@example.org\n17 2 * * * /usr/bin/true\n"
    managed = manager.MARKER_START + "\n*/5 * * * * /safe/watchdog\n" + manager.MARKER_END + "\n"
    assert manager.remove_managed_block(user_jobs + managed) == user_jobs
    assert manager.remove_managed_block(user_jobs) == user_jobs


def test_broken_crontab_markers_are_rejected():
    """Never write a crontab when markers are malformed or duplicated."""
    with pytest.raises(ValueError):
        manager.remove_managed_block(manager.MARKER_START + "\n")
    duplicate = (manager.MARKER_START + "\n" + manager.MARKER_END + "\n") * 2
    with pytest.raises(ValueError):
        manager.remove_managed_block(duplicate)


def test_no_crontab_distinguished_from_real_errors(monkeypatch):
    """Do not erase an existing crontab after a permission error."""
    monkeypatch.setattr(manager, "run", lambda args: completed(args, code=1, stderr="no crontab for user"))
    assert manager.current_crontab() == ""
    monkeypatch.setattr(manager, "run", lambda args: completed(args, code=1, stderr="permission denied"))
    with pytest.raises(RuntimeError):
        manager.current_crontab()


def test_cron_install_idempotent_and_preserves_other_jobs(monkeypatch, tmp_path):
    """Two installs produce one marker and leave non-managed entries unchanged."""
    project = tmp_path / "work/hpc-mcp"
    home = tmp_path
    venv_python = project / ".venv/bin/python"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()
    (project / "deploy").mkdir()
    (project / "deploy/cron_watchdog.py").touch()
    store = {"text": "15 1 * * * /usr/bin/true\n"}
    monkeypatch.setattr(manager, "user_service_active", lambda: False)
    monkeypatch.setattr(manager, "current_crontab", lambda: store["text"])
    monkeypatch.setattr(manager, "update_crontab", lambda value: store.update(text=value))
    monkeypatch.setattr(manager, "run", lambda args: completed(args))
    manager.install_cron(project, home)
    manager.install_cron(project, home)
    assert store["text"].count(manager.MARKER_START) == 1
    assert store["text"].count("@reboot") == 1
    assert "15 1 * * * /usr/bin/true" in store["text"]


def test_cron_install_refuses_active_systemd(monkeypatch, tmp_path):
    """Protect an already running Tunnel against duplicate instances."""
    monkeypatch.setattr(manager, "user_service_active", lambda: True)
    with pytest.raises(RuntimeError):
        manager.install_cron(tmp_path, tmp_path)


def test_env_file_is_user_private(monkeypatch, tmp_path):
    """Load only the key field without evaluating shell instructions."""
    monkeypatch.setenv("HOME", str(tmp_path))
    home = tmp_path / ".config/hpc-mcp"
    home.mkdir(parents=True)
    path = home / "tunnel.env"
    path.write_text("# comment\nCONTROL_PLANE_API_KEY=sk-test-example\n")
    path.chmod(0o600)
    assert watchdog.read_key() == "sk-test-example"
    path.chmod(0o644)
    with pytest.raises(PermissionError):
        watchdog.read_key()


def test_watchdog_refuses_malformed_key(monkeypatch, tmp_path):
    """Reject shell-like substitutions without executing them."""
    monkeypatch.setenv("HOME", str(tmp_path))
    home = tmp_path / ".config/hpc-mcp"
    home.mkdir(parents=True)
    path = home / "tunnel.env"
    path.write_text("CONTROL_PLANE_API_KEY=$(something dangerous)\n")
    path.chmod(0o600)
    with pytest.raises(ValueError):
        watchdog.read_key()


def test_watchdog_status_does_not_start_or_stop(monkeypatch, tmp_path):
    """Query process state without requiring credentials."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(watchdog, "record_matches", lambda record: False)
    assert watchdog.execute("status") == {"running": False, "pid": None}


def test_systemd_install_skips_restart_when_active(monkeypatch, tmp_path):
    """Copy the unit only if changed and leave live Tunnel process untouched."""
    project = tmp_path / "project"
    home = tmp_path / "home"
    (project / "deploy").mkdir(parents=True)
    (project / "deploy/hpc-mcp-tunnel.service").write_text("[Service]\nExecStart=/bin/true\n")
    calls = []
    monkeypatch.setattr(manager, "cron_managed", lambda: False)
    monkeypatch.setattr(manager, "user_service_active", lambda: True)
    monkeypatch.setattr(manager, "run", lambda args: (calls.append(args), completed(args))[1])
    manager.install_systemd(project, home)
    assert (home / ".config/systemd/user/hpc-mcp-tunnel.service").is_file()
    assert not any("start" in args for args in calls)
    assert not any("restart" in args for args in calls)
