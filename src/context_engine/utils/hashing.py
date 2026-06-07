"""Content hashing + duplicate scan. Stdlib only.

``sha256`` is the engine's primary source-link authority: provenance manifests,
delta seen-sets, gate link-backs, and dedup decisions all key on it, never on
filenames. Digests are returned UPPERCASE hex so old- and new-style records
join case-insensitively.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os

_READ_CHUNK = 1 << 20  # 1 MiB


def sha256_file(path: str) -> str:
    """Return the UPPERCASE hex sha256 of the file at ``path`` (streamed)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_READ_CHUNK), b""):
            h.update(block)
    return h.hexdigest().upper()


def sha256_bytes(data: bytes) -> str:
    """Return the UPPERCASE hex sha256 of an in-memory byte string."""
    return hashlib.sha256(data).hexdigest().upper()


def sha256_text(text: str) -> str:
    """Return the UPPERCASE hex sha256 of ``text`` encoded as UTF-8."""
    return sha256_bytes(text.encode("utf-8"))


def _excluded(rel_posix: str, exclude_globs: list[str]) -> bool:
    for pat in exclude_globs:
        if fnmatch.fnmatch(rel_posix, pat):
            return True
        # ``**/X/**``-style patterns must also exclude X at the tree root, where
        # the leading "**/" has zero path segments to bind to (fnmatch would
        # otherwise miss a top-level ".venv/lib.py" for pattern "**/.venv/**").
        if pat.startswith("**/") and fnmatch.fnmatch(rel_posix, pat[3:]):
            return True
    return False


def scan(root: str, exclude_globs: list[str] | None = None) -> dict[str, list[str]]:
    """Walk ``root``, hash every non-excluded file, return sha256 -> sorted abs paths.

    ``exclude_globs`` are fnmatch'd against the path relative to ``root`` with
    forward slashes, e.g. ``"**/.venv/**"``, ``"_provenance/*"``.
    """
    exclude_globs = exclude_globs or []
    buckets: dict[str, list[str]] = {}
    root_abs = os.path.abspath(root)
    for dirpath, _dirnames, filenames in os.walk(root_abs):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root_abs).replace(os.sep, "/")
            if _excluded(rel, exclude_globs):
                continue
            try:
                digest = sha256_file(full)
            except (OSError, PermissionError):
                continue
            buckets.setdefault(digest, []).append(full)
    for digest in buckets:
        buckets[digest].sort()
    return buckets
