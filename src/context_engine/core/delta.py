"""Delta detection for the ongoing-cadence pipeline.

A file is *new* iff its sha256 is in NEITHER the provenance INDEX NOR the set of
``sources[].sha256`` link-backs cited by existing hot artifacts. The second set
is load-bearing: ``promote()`` logs the inbox artifact as ``src_abs``, never the
source it was distilled from, so distilled-from sources are absent from the INDEX
and would otherwise be re-flagged as new on the first run.
"""
from __future__ import annotations

import os
import sqlite3

import yaml

from ..utils.hashing import sha256_file

DEFAULT_SKIP_DIRS = {".git", ".venv", "node_modules", "_provenance", "__pycache__"}


def index_shas(db: str) -> set[str]:
    """Return the UPPERCASE sha256 set recorded in the provenance INDEX."""
    if not os.path.exists(db):
        return set()
    conn = sqlite3.connect(db)
    try:
        # Exclude pure-removal ops from the seen-set: a `delete` only removed a
        # redundant COPY, so its sha (identical to the surviving canonical's)
        # must not suppress curation of that canonical. Only curation/preservation
        # ops mark content as seen. (Older indexes without an `op` column fall
        # back to all rows.)
        try:
            rows = conn.execute(
                "SELECT sha256 FROM files WHERE op IS NULL OR op != 'delete'"
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute("SELECT sha256 FROM files").fetchall()
    finally:
        conn.close()
    return {str(r[0]).upper() for r in rows if r[0]}


def _frontmatter(text: str) -> dict:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            try:
                data = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                return {}
            if isinstance(data, dict):
                return data
    return {}


def hot_source_shas(hot_root: str) -> set[str]:
    """UPPERCASE set of every ``sources[].sha256`` cited under hot_root (skips _inbox)."""
    shas: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(hot_root):
        dirnames[:] = [d for d in dirnames if d != "_inbox"]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            with open(os.path.join(dirpath, name), "r",
                      encoding="utf-8", errors="replace") as fh:
                fm = _frontmatter(fh.read())
            for s in (fm.get("sources") or []):
                if isinstance(s, dict) and s.get("sha256"):
                    shas.add(str(s["sha256"]).upper())
    return shas


def new_files(live_roots: list[str], db: str, hot_root: str,
              *, skip_dirs: set[str] | None = None) -> list[dict]:
    """Return ``[{path, sha256, size}]`` for ``*.md`` whose sha256 is unseen.

    seen-set = ``index_shas(db) | hot_source_shas(hot_root)``. Cadence-seen ledger
    entries are folded in via ``index_shas`` once the manifests are replayed into
    the INDEX.
    """
    skip = skip_dirs or DEFAULT_SKIP_DIRS
    seen = index_shas(db) | hot_source_shas(hot_root)
    out: list[dict] = []
    batch: set[str] = set()
    for root in live_roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for name in sorted(filenames):
                if not name.lower().endswith(".md"):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    sha = sha256_file(path)
                except OSError:
                    continue
                if sha in seen or sha in batch:
                    continue
                batch.add(sha)
                out.append({"path": path, "sha256": sha,
                            "size": os.path.getsize(path)})
    return out
