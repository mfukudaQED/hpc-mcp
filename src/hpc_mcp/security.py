"""Validate filesystem targets and untrusted process arguments."""

from __future__ import annotations

from pathlib import Path
import hashlib
import os

from .config import Settings

# The denylist is a second line of defense; the narrow roots are primary.
DENY_COMPONENTS = frozenset({
    ".ssh", ".gnupg", ".aws", ".kube", ".config", ".local", ".npmrc",
    ".netrc", ".env", ".credentials", "id_rsa", "id_ed25519", "id_ecdsa",
})
DENY_SUFFIXES = (".pem", ".p12", ".pfx", ".key")


def resolve_path(settings: Settings, value: str) -> Path:
    """Return the canonical path only when it remains below an approved root."""
    if not value or "\x00" in value:
        raise ValueError("Invalid path")
    raw = Path(os.path.expanduser(value))
    target = raw.resolve(strict=False)
    if any(part in DENY_COMPONENTS for part in raw.parts + target.parts):
        raise PermissionError("Credential or private configuration paths are prohibited")
    if target.name.lower().endswith(DENY_SUFFIXES):
        raise PermissionError("Secret-key file types are prohibited")
    if not any(target.is_relative_to(root) for root in settings.roots):
        raise PermissionError("Path outside configured roots")
    return target


def sha256_file(path: Path, max_bytes: int) -> str:
    """Hash a bounded regular file for optimistic update concurrency."""
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("Not a regular file within size limit")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def limited(value: str, limit: int) -> str:
    """Truncate tool output without creating unbounded model context."""
    return value if len(value) <= limit else value[:limit] + "\n[TRUNCATED]"
