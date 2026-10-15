"""Bounded, user-owned filesystem operations."""

from __future__ import annotations

from pathlib import Path
import hashlib
import os
import tempfile

from .config import Settings
from .security import resolve_path, sha256_file


def list_directory(settings: Settings, path: str, max_entries: int = 100) -> dict:
    """List direct children, excluding prohibited paths and leaking no file contents."""
    directory = resolve_path(settings, path)
    if not directory.is_dir():
        raise NotADirectoryError(str(directory))
    max_entries = max(1, min(max_entries, 200))
    results = []
    for child in sorted(directory.iterdir(), key=lambda entry: entry.name):
        try:
            resolved = resolve_path(settings, str(child))
        except (PermissionError, ValueError, OSError):
            continue
        results.append({"name": child.name, "type": "directory" if resolved.is_dir() else "file"})
        if len(results) >= max_entries:
            break
    return {"path": str(directory), "entries": results, "limited_to": max_entries}


def read_file(settings: Settings, path: str, start_line: int = 1, max_lines: int = 200) -> dict:
    """Read at most the configured file size and a bounded number of lines."""
    target = resolve_path(settings, path)
    if not target.is_file() or target.stat().st_size > settings.max_file_bytes:
        raise ValueError("Not a regular file or file exceeds configured limit")
    start_line = max(start_line, 1)
    max_lines = max(1, min(max_lines, 1000))
    data = target.read_bytes()
    if b"\x00" in data:
        raise ValueError("Binary file refused")
    lines = data.decode("utf-8").splitlines()
    return {
        "path": str(target), "sha256": hashlib.sha256(data).hexdigest(),
        "total_lines": len(lines), "start_line": start_line,
        "content": "\n".join(lines[start_line - 1:start_line - 1 + max_lines]),
    }


def make_directory(settings: Settings, path: str) -> dict:
    """Create an allowed directory tree when write permissions are enabled."""
    if not settings.enable_writes:
        raise PermissionError("Writing is disabled")
    directory = resolve_path(settings, path)
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    if not directory.is_dir():
        raise NotADirectoryError(str(directory))
    return {"path": str(directory), "created_or_exists": True}


def write_file(settings: Settings, path: str, content: str, expected_sha256: str = "") -> dict:
    """Atomically create a UTF-8 file or replace an existing hash-matched file."""
    if not settings.enable_writes:
        raise PermissionError("Writing is disabled")
    target = resolve_path(settings, path)
    if not target.parent.is_dir():
        raise FileNotFoundError("Parent directory does not exist")
    payload = content.encode("utf-8")
    if len(payload) > settings.max_file_bytes:
        raise ValueError("File exceeds configured size limit")
    old_mode = None
    if target.exists():
        if not target.is_file():
            raise ValueError("Target is not a regular file")
        if not expected_sha256:
            raise ValueError("expected_sha256 required to replace existing file")
        actual = sha256_file(target, settings.max_file_bytes)
        if actual != expected_sha256:
            raise ValueError("File changed since last read; refusing overwrite")
        old_mode = target.stat().st_mode & 0o777
    elif expected_sha256:
        raise ValueError("Cannot check expected_sha256 of a missing file")
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".hpc-mcp-", delete=False) as handle:
            tmp_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if old_mode is not None:
            os.chmod(tmp_name, old_mode)
        os.replace(tmp_name, target)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return {"path": str(target), "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def replace_text(settings: Settings, path: str, old: str, new: str, expected_sha256: str) -> dict:
    """Replace one exact text occurrence when its hash matches the last read."""
    if not old:
        raise ValueError("old text must be non-empty")
    info = read_file(settings, path, 1, 1_000_000)
    target = resolve_path(settings, path)
    if info["sha256"] != expected_sha256:
        raise ValueError("File changed since last read")
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise ValueError("old text must occur exactly once")
    return write_file(settings, path, text.replace(old, new, 1), expected_sha256)


def search_files(settings: Settings, path: str, term: str, max_results: int = 50) -> dict:
    """Search bounded UTF-8 files without following directory symlinks."""
    root = resolve_path(settings, path)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    if not term or len(term) > 256:
        raise ValueError("Search term must contain 1..256 characters")
    results = []
    visited = 0
    max_results = max(1, min(max_results, 100))
    for parent, dirs, files in os.walk(root, followlinks=False):
        safe_dirs = []
        for d in dirs:
            try:
                p = resolve_path(settings, str(Path(parent) / d))
                if not p.is_symlink() and p.is_dir() and not d.startswith("."):
                    safe_dirs.append(d)
            except (PermissionError, OSError):
                continue
        dirs[:] = safe_dirs
        for filename in files:
            if filename.startswith("."):
                continue
            try:
                file = resolve_path(settings, str(Path(parent) / filename))
                if not file.is_file() or file.stat().st_size > settings.max_file_bytes:
                    continue
                visited += 1
                if visited > 2000:
                    return {"matches": results, "scan_limit_reached": True}
                with file.open("r", encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, 1):
                        if term in line:
                            results.append({"file": str(file), "line": line_number, "text": line[:300].rstrip()})
                            if len(results) >= max_results:
                                return {"matches": results, "result_limit_reached": True}
            except (UnicodeDecodeError, PermissionError, OSError, ValueError):
                continue
    return {"matches": results, "scanned_files": visited}
