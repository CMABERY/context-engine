"""Append-only provenance manifest writer. Stdlib only.

Every mutation the engine performs (promote, move, delete, normalize, seed,
cadence-seen) appends exactly one JSON line to a manifest. Manifests are the
*truth*; the sqlite provenance index (see :mod:`context_engine.core.provenance`)
is a disposable, rebuildable projection of them.

Record schema (one JSON object per line)::

    {
      "op":          str,         # promote | move | delete | normalize | ...
      "src_abs":     str | null,  # source path (storage-normalized)
      "dst_abs":     str | null,  # destination path (storage-normalized)
      "sha256":      str,         # UPPERCASE content hash — the real link
      "size_bytes":  int,
      "mtime_utc":   str,         # source mtime, ...Z second precision
      "ts_utc":      str,         # append time, ...Z second precision
      "stage":       str,         # pipeline stage label
      "reversible":  bool,
      "reason":      str,
    }

Paths are stored in a configurable convention (``path_style``); ``sha256`` is the
authority, so a stored path that no longer resolves is only a stale hint, never a
broken link.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .paths import normalize_for_store


def now_utc() -> str:
    """ISO8601 UTC, second precision, trailing 'Z' (not '+00:00')."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mtime_z(src_abs: str | None, dst_abs: str | None) -> str:
    """Stat src if it exists, else dst; return mtime as ...Z (second precision)."""
    for cand in (src_abs, dst_abs):
        if cand and os.path.exists(cand):
            ts = datetime.fromtimestamp(os.stat(cand).st_mtime, tz=timezone.utc)
            return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return now_utc()


def _store(path: str | None, style: str) -> str | None:
    return None if path is None else normalize_for_store(path, style)


def append(
    manifest_path: str,
    *,
    op: str,
    src_abs: str | None,
    dst_abs: str | None,
    sha256: str,
    size_bytes: int,
    reason: str,
    stage: str,
    reversible: bool = True,
    path_style: str = "native",
) -> dict:
    """Append exactly ONE JSON line to ``manifest_path`` (created if absent).

    Returns the record that was written (useful for tests and callers that want
    to echo the logged action).
    """
    record = {
        "op": op,
        "src_abs": _store(src_abs, path_style),
        "dst_abs": _store(dst_abs, path_style),
        "sha256": sha256.upper(),
        "size_bytes": size_bytes,
        "mtime_utc": _mtime_z(src_abs, dst_abs),
        "ts_utc": now_utc(),
        "stage": stage,
        "reversible": reversible,
        "reason": reason,
    }
    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
    with open(manifest_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
