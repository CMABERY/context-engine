"""Exact-duplicate + version-pair detection. Pure functions over a scan() index.

Live keeper ("canonical") = copy under the highest-priority live_root (by
caller's order), preferring a base filename over a ``(N)`` version variant,
tie-broken by lexicographically smallest path; held keeper = smallest path. Merge
decisions are ALWAYS by content-hash + path context, never by filename.
"""
from __future__ import annotations

import os
import re

from ..utils.hashing import sha256_file

_VERSION_RE = re.compile(r"^(?P<stem>.+?) \((?P<n>\d+)\)(?P<ext>\.[^.]+)$")


def _under(path: str, roots: list[str]) -> bool:
    ap = os.path.abspath(path)
    return any(ap == r or ap.startswith(r.rstrip(os.sep) + os.sep)
               for r in (os.path.abspath(x) for x in roots))


def _root_priority(path: str, roots_abs: list[str]) -> int:
    """Index of the first root (caller's order) that ``path`` sits under."""
    ap = os.path.abspath(path)
    for i, r in enumerate(roots_abs):
        if ap == r or ap.startswith(r.rstrip(os.sep) + os.sep):
            return i
    return len(roots_abs)


def live_tree_dupes(index: dict, live_roots: list[str], held_root: str) -> list[dict]:
    """Hash-sets with >1 copy entirely under live_roots, excluding held_root.

    The keeper is chosen by, in order: (1) highest-priority live_root (caller
    order, e.g. working copies before snapshots); (2) a base filename over a
    ``(N)`` version variant (so a byte-identical ``a (1).md`` is the redundant
    one, never the base ``a.md``); (3) lexicographically smallest path. Returns
    ``[{sha256, canonical, redundant, size_bytes}]`` sorted by sha256.
    """
    held = os.path.abspath(held_root)
    roots_abs = [os.path.abspath(x) for x in live_roots]
    out = []
    for digest, paths in index.items():
        live = [p for p in paths
                if _under(p, live_roots)
                and not os.path.abspath(p).startswith(held + os.sep)]
        if len(live) < 2:
            continue
        ordered = sorted(live, key=lambda p: (
            _root_priority(p, roots_abs),
            1 if _VERSION_RE.match(os.path.basename(p)) else 0,
            p))
        out.append({
            "sha256": digest,
            "canonical": ordered[0],
            "redundant": ordered[1:],
            "size_bytes": os.path.getsize(ordered[0]),
        })
    return sorted(out, key=lambda d: d["sha256"])


def held_dupes(index: dict, held_root: str) -> list[dict]:
    """Hash-sets with >1 physical copy inside held_root -> keep 1, list redundant.

    Returns ``[{sha256, canonical, redundant, size_bytes}]`` sorted by sha256.
    """
    held = os.path.abspath(held_root)
    out = []
    for digest, paths in index.items():
        inside = sorted(p for p in paths
                        if os.path.abspath(p).startswith(held + os.sep)
                        or os.path.abspath(p) == held)
        if len(inside) < 2:
            continue
        out.append({
            "sha256": digest,
            "canonical": inside[0],
            "redundant": inside[1:],
            "size_bytes": os.path.getsize(inside[0]),
        })
    return sorted(out, key=lambda d: d["sha256"])


def classify_version_pairs(live_roots: list[str]) -> list[dict]:
    """Find ``name (N).ext`` files whose base ``name.ext`` sits in the SAME dir.

    ``kind='accidental'`` iff byte-identical to base, else ``kind='lineage'``.
    Returns ``[{base, variant, n, kind, base_sha, variant_sha}]`` sorted by variant.
    """
    out = []
    for root in live_roots:
        root_abs = os.path.abspath(root)
        for dirpath, _d, filenames in os.walk(root_abs):
            names = set(filenames)
            for name in filenames:
                m = _VERSION_RE.match(name)
                if not m:
                    continue
                base_name = m.group("stem") + m.group("ext")
                if base_name not in names:
                    continue
                base_p = os.path.join(dirpath, base_name)
                var_p = os.path.join(dirpath, name)
                base_sha = sha256_file(base_p)
                var_sha = sha256_file(var_p)
                out.append({
                    "base": base_p,
                    "variant": var_p,
                    "n": int(m.group("n")),
                    "kind": "accidental" if base_sha == var_sha else "lineage",
                    "base_sha": base_sha,
                    "variant_sha": var_sha,
                })
    return sorted(out, key=lambda d: d["variant"])
