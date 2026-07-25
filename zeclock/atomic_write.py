"""Atomic file write utilities for power-loss safety.

All config and state writes should use these functions to avoid
file corruption on unexpected power loss. The pattern is:

    1. Write to a temporary file in the same directory
    2. fsync() the file to ensure data reaches storage
    3. rename() atomically replaces the target (POSIX guarantees)
    4. fsync() the directory to persist the rename

This guarantees that at any point during a power cut, the target
file is either the old version or the new version — never a
partially written/truncated file.
"""

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Atomically write text content to a file.

    Uses write-to-temp + fsync + rename pattern for crash safety.

    Args:
        path: Target file path.
        content: Text content to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create temp file in the same directory (same filesystem for rename)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = -1  # Mark as closed
        # Atomic rename
        os.replace(tmp_path, str(path))
        # fsync the directory to persist the rename
        _fsync_directory(path.parent)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Atomically write binary content to a file.

    Uses write-to-temp + fsync + rename pattern for crash safety.

    Args:
        path: Target file path.
        content: Binary content to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        os.write(fd, content)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp_path, str(path))
        _fsync_directory(path.parent)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _fsync_directory(directory: Path) -> None:
    """fsync a directory to persist rename operations."""
    try:
        fd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(fd)
        os.close(fd)
    except OSError:
        # Some filesystems/platforms don't support directory fsync
        pass
