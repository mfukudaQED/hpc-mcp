"""Regression tests for filesystem boundaries."""

import pytest
from hpc_mcp.filesystem import read_file, list_directory, write_file
from hpc_mcp.security import resolve_path


def test_allowed_and_forbidden_roots(readonly, root, tmp_path):
    """Disallow traversal outside configured roots."""
    assert resolve_path(readonly, str(root / "new.txt")) == root / "new.txt"
    with pytest.raises(PermissionError):
        resolve_path(readonly, str(root / ".." / "secret.txt"))
    with pytest.raises(PermissionError):
        resolve_path(readonly, str(tmp_path / "other.txt"))


def test_symlink_escape_blocked(readonly, root, tmp_path):
    """Reject symlinks that resolve to files outside allowed roots."""
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    (root / "escape.txt").symlink_to(secret)
    with pytest.raises(PermissionError):
        read_file(readonly, str(root / "escape.txt"))
    assert list_directory(readonly, str(root))["entries"] == []


def test_sensitive_names_blocked(readonly, root):
    """Block direct access to credential-style names."""
    for name in (".ssh/id_rsa", ".env", "private.pem", ".config/app"):
        with pytest.raises(PermissionError):
            resolve_path(readonly, str(root / name))


def test_default_writes_disabled(readonly, root):
    """Default policy is read-only regardless of file permissions."""
    with pytest.raises(PermissionError):
        write_file(readonly, str(root / "new.txt"), "hello")
