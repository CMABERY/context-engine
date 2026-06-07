"""Cross-platform path normalization. Stdlib only.

Provenance records store absolute paths as *hints* (sha256 is the real
authority). A manifest written on one host may be read on another whose path
convention differs — most commonly Windows (``C:\\corpus``) vs. a POSIX/WSL
mount (``/mnt/c/corpus``). These helpers translate between the stored form and
the form the *current* OS can ``os.path.exists()``.

This generalizes the host-specific conversions that the reference implementation
scattered across modules (``_win_to_posix``, ``_to_local``, ``_to_windows``):
there are no hard-coded drive letters or mount roots here.
"""
from __future__ import annotations

import os
import re

# A Windows drive-letter absolute path, e.g. ``C:\x`` or ``c:/x``.
_WIN_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/]")
# A POSIX mount of a Windows drive, e.g. ``/mnt/c/x`` (WSL) or ``/c/x`` (Git Bash).
_MOUNT_RE = re.compile(r"^/(?:mnt/)?([A-Za-z])/")


def to_posix_mount(path: str) -> str:
    """Map a Windows drive path to a ``/mnt/<drive>/`` POSIX mount path.

    ``C:\\corpus\\a.md`` -> ``/mnt/c/corpus/a.md``. Already-POSIX paths are
    returned with back-slashes normalized to forward slashes.
    """
    p = path.replace("\\", "/")
    m = _WIN_DRIVE_RE.match(path)
    if m:
        drive = m.group(1).lower()
        rest = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return p


def to_windows(path: str) -> str:
    """Map a POSIX mount path to a ``<DRIVE>:\\`` Windows path.

    ``/mnt/c/corpus/a.md`` -> ``C:\\corpus\\a.md``. Already-Windows paths are
    returned with forward slashes normalized to back-slashes.
    """
    m = _MOUNT_RE.match(path)
    if m:
        drive = m.group(1).upper()
        rest = path[m.end():]
        return f"{drive}:\\" + rest.replace("/", "\\")
    if _WIN_DRIVE_RE.match(path):
        return path[0].upper() + ":" + path[2:].replace("/", "\\")
    return path.replace("/", "\\")


def to_local(path: str) -> str:
    """Translate a stored path to the form the current OS can resolve.

    On Windows hosts, POSIX mounts (``/mnt/c/...``) become drive paths. On POSIX
    hosts, drive paths (``C:\\...``) become ``/mnt/<drive>/...`` mounts. Paths
    already in the native convention are returned unchanged.
    """
    if os.sep == "\\":  # Windows host
        if _MOUNT_RE.match(path):
            return to_windows(path)
        return path
    # POSIX host
    if _WIN_DRIVE_RE.match(path):
        return to_posix_mount(path)
    return path


def normalize_for_store(path: str, style: str = "native") -> str:
    """Render an absolute path in the requested *storage* convention.

    ``style`` is one of:

    * ``"native"`` (default) — the absolute path as the current OS expresses it.
      Best for single-host deployments; keeps manifests round-trippable.
    * ``"posix"``  — ``/mnt/<drive>/`` style (portable to WSL/Linux readers).
    * ``"windows"`` — ``<DRIVE>:\\`` style.
    """
    if style == "posix":
        return to_posix_mount(path)
    if style == "windows":
        return to_windows(path)
    if style == "native":
        return os.path.abspath(path) if not os.path.isabs(path) else path
    raise ValueError(f"unknown path style: {style!r}")
