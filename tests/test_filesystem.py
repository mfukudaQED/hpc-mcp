"""Tests for bounded reading and guarded atomic updates."""

import pytest
from hpc_mcp.filesystem import read_file, replace_text, search_files, write_file


def test_read_and_hash_and_replace(writable, root):
    """Require an expected SHA-256 for replacements and edits."""
    file = root / "code.f90"
    first = write_file(writable, str(file), "alpha\nbeta\n")
    read = read_file(writable, str(file))
    assert read["sha256"] == first["sha256"]
    with pytest.raises(ValueError):
        write_file(writable, str(file), "replacement")
    with pytest.raises(ValueError):
        replace_text(writable, str(file), "alpha", "gamma", "00")
    result = replace_text(writable, str(file), "alpha", "gamma", read["sha256"])
    assert read_file(writable, str(file))["content"].startswith("gamma")
    with pytest.raises(ValueError):
        write_file(writable, str(file), "old", read["sha256"])
    assert result["sha256"] != read["sha256"]


def test_search_only_within_roots(readonly, root):
    """Find matching source lines without returning binary data."""
    (root / "source.py").write_text("hello\nphysics = 42\n")
    result = search_files(readonly, str(root), "physics")
    assert len(result["matches"]) == 1
    assert result["matches"][0]["line"] == 2


def test_oversized_and_binary_files_rejected(readonly, root):
    """Refuse large and binary inputs."""
    binary = root / "blob.bin"
    binary.write_bytes(b"a\x00b")
    with pytest.raises(ValueError):
        read_file(readonly, str(binary))
    (root / "huge.txt").write_bytes(b"x" * (readonly.max_file_bytes + 1))
    with pytest.raises(ValueError):
        read_file(readonly, str(root / "huge.txt"))
