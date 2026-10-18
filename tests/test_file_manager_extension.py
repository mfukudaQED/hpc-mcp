"""Tests for optional MCP File Manager integration and opt-in policies."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from hpc_mcp.config import Settings, load_settings
from hpc_mcp.server import build_server


def _config(tmp_path: Path, *, body: str = "") -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        "[filesystem]\n"
        f"roots = [{json.dumps(str(tmp_path))}]\n"
        + body,
        encoding="utf-8",
    )
    return path


def test_file_manager_disabled_by_default(tmp_path: Path) -> None:
    cfg = load_settings(_config(tmp_path))
    assert not cfg.enable_file_viewer
    assert not cfg.enable_file_manager_edit


def test_legacy_file_viewer_enable_still_works(tmp_path: Path) -> None:
    cfg = load_settings(_config(tmp_path, body=(
        "\n[extensions.file_viewer]\nenabled = true\n"
    )))
    assert cfg.enable_file_viewer
    assert not cfg.enable_file_manager_edit


def test_new_setting_overrides_legacy(tmp_path: Path) -> None:
    cfg = load_settings(_config(tmp_path, body=(
        "\n[extensions.file_viewer]\nenabled = true\n"
        "\n[extensions.file_manager]\nenabled = false\n"
    )))
    assert not cfg.enable_file_viewer


def test_editing_requires_global_writes(tmp_path: Path) -> None:
    for enabled in (False, True):
        cfg = load_settings(_config(tmp_path, body=(
            f"\n[permissions]\nenable_writes = {str(enabled).lower()}\n"
            "\n[extensions.file_manager]\nenabled = true\n"
            "enable_edit = true\n"
        )))
        assert cfg.enable_file_viewer
        assert cfg.enable_file_manager_edit is enabled


def test_register_optional_package_only_when_enabled(tmp_path: Path, monkeypatch) -> None:
    calls = []

    # A minimal stub prevents this test from requiring the optional package.
    package = types.ModuleType("mcp_file_manager")
    extension = types.ModuleType("mcp_file_manager.extension")

    def register(*args, **kwargs):
        calls.append((args, kwargs))

    extension.register_file_manager = register
    monkeypatch.setitem(sys.modules, "mcp_file_manager", package)
    monkeypatch.setitem(sys.modules, "mcp_file_manager.extension", extension)

    disabled = Settings(roots=(tmp_path,), scheduler_type="none")
    build_server(disabled)
    assert not calls

    enabled = Settings(
        roots=(tmp_path,),
        scheduler_type="none",
        enable_file_viewer=True,
        enable_file_manager_edit=True,
        max_file_bytes=12345,
        max_output_chars=19000,
    )
    build_server(enabled)
    assert len(calls) == 1
    (_server,), opts = calls[0]
    assert opts == {
        "roots": (tmp_path,),
        "max_file_bytes": 12345,
        "max_response_chars": 12000,
        "enable_edit": True,
    }
