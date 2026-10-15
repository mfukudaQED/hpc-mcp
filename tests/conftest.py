"""Shared isolated-root fixtures."""

from pathlib import Path
import pytest
from hpc_mcp.config import Settings


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Return a dedicated permitted file tree."""
    workspace = tmp_path / "work"
    workspace.mkdir()
    return workspace


@pytest.fixture
def readonly(root: Path) -> Settings:
    """Provide a read-only MCP policy."""
    return Settings(roots=(root,))


@pytest.fixture
def writable(root: Path) -> Settings:
    """Provide a policy with write operations enabled."""
    return Settings(roots=(root,), enable_writes=True)
