"""Derived provenance INDEX: a rebuildable sqlite projection of the manifests.

Table ``files(sha256 TEXT, path TEXT, current INTEGER, tier TEXT)``. ``sha256``
is stored UPPERCASE so old- and new-style records join. The manifests directory
is walked RECURSIVELY so nested staging manifests are replayed alongside
top-level ones. The INDEX is **disposable** — manifests are the truth; rebuild
freely.

``tier`` is assigned by config-driven ``tier_rules`` (ordered ``(substring,
tier)`` pairs), not by any hard-coded corpus layout, so the same code serves any
hot/cold topology.
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3

from ..utils.paths import to_local, to_posix_mount


def tier_for(path: str, tier_rules: list[tuple[str, str]] | None) -> str:
    """Classify ``path`` into a tier via ordered substring rules (first match).

    Matching is case-insensitive against the POSIX-normalized path so a rule
    written as ``"/corpus/_hot/"`` matches both ``C:\\corpus\\_hot\\x`` and
    ``/mnt/c/corpus/_hot/x``. Returns ``"live"`` when no rule matches.
    """
    if not tier_rules:
        return "live"
    hay = to_posix_mount(path).lower()
    for needle, tier in tier_rules:
        n = to_posix_mount(needle).lower()
        if n and n in hay:
            return tier
    return "live"


def build(manifests_dir: str, out_db: str,
          tier_rules: list[tuple[str, str]] | None = None) -> None:
    """Replay all ``*.jsonl`` under ``manifests_dir`` (RECURSIVE) into ``out_db``.

    Always produces a valid (possibly empty) ``files`` table so downstream
    ``resolve()`` never hits a 'no such table' error on a first run.
    """
    if os.path.exists(out_db):
        os.remove(out_db)
    os.makedirs(os.path.dirname(os.path.abspath(out_db)), exist_ok=True)
    conn = sqlite3.connect(out_db)
    conn.execute(
        "CREATE TABLE files (sha256 TEXT, path TEXT, current INTEGER, tier TEXT)"
    )
    conn.execute("CREATE INDEX idx_sha ON files(sha256)")
    rows = []
    pattern = os.path.join(manifests_dir, "**", "*.jsonl")
    for mf in sorted(glob.glob(pattern, recursive=True)):
        with open(mf, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sha = (rec.get("sha256") or "").upper()
                if not sha or sha.startswith("WITHHELD"):
                    continue
                for key in ("dst_abs", "src_abs"):
                    p = rec.get(key)
                    if not p:
                        continue
                    rows.append((sha, p, 1 if os.path.exists(to_local(p)) else 0,
                                 tier_for(p, tier_rules)))
    conn.executemany("INSERT INTO files VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()


def resolve(db: str, sha256: str) -> dict:
    """Return ``{sha256, paths, path, current, tier}`` (case-insensitive lookup)."""
    sha = sha256.upper()
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "SELECT path, current, tier FROM files WHERE sha256=? "
        "ORDER BY current DESC, path",
        (sha,),
    )
    recs = cur.fetchall()
    conn.close()
    if not recs:
        return {"sha256": sha, "paths": [], "path": None,
                "current": False, "tier": None}
    paths = [r[0] for r in recs]
    return {
        "sha256": sha,
        "paths": paths,
        "path": paths[0],
        "current": bool(recs[0][1]),
        "tier": recs[0][2],
    }


def dangling_report(db: str, artifact_paths: list[str]) -> list[dict]:
    """Flag dangling=True for each artifact source-path with no live file.

    Non-dangling if it currently exists OR a current-tier INDEX record shares its
    basename (recoverable by sha256 cross-join).
    """
    conn = sqlite3.connect(db)
    report = []
    for ap in artifact_paths:
        local = to_local(ap)
        exists = os.path.exists(local)
        recoverable = False
        if not exists:
            base = os.path.basename(local.replace("\\", "/"))
            cur = conn.execute(
                "SELECT 1 FROM files WHERE current=1 AND path LIKE ? LIMIT 1",
                ("%" + base + "%",),
            )
            recoverable = cur.fetchone() is not None
        report.append({
            "path": ap,
            "exists": exists,
            "recoverable_by_name": recoverable,
            "dangling": (not exists) and (not recoverable),
        })
    conn.close()
    return report
