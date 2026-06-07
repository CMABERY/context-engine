"""Near-duplicate detection + merge. Two-stage for tractability.

1. Bucket files by normalized title (O(n) grouping).
2. Within each bucket of >=2, compute pairwise Jaccard similarity on word
   shingles to find near-duplicate clusters (O(bucket^2)).

Files with unique titles are never compared; only files sharing a normalized
title are candidates. The Jaccard threshold is the real gate — false-positive
title collisions are filtered by content similarity. Losers are MOVED (never
deleted) to a cold directory and logged via the manifest.
"""
from __future__ import annotations

import os
import re
import shutil

from ..models import DEFAULT_EXPORT_PREFIXES, DEFAULT_GENERIC_STEMS
from ..utils import manifests as _manifests
from ..utils.hashing import sha256_file

# Trailing version marker: " (N)" just before extension or at end of stem.
_VERSION_RE = re.compile(r"\s*\(\d+\)$")
_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n.*?\n---\s*\n", re.DOTALL)
_FENCED_CODE_RE = re.compile(r"```[^\n]*\n.*?```", re.DOTALL)


def _is_generic(filename: str, generic_stems: set[str]) -> bool:
    """Return True if filename's basename stem is a generic name to skip."""
    base = os.path.basename(filename)
    stem, _, _ext = base.rpartition(".")
    if not stem:
        stem = base
    return stem.lower() in generic_stems


def normalize_title(filename: str, export_prefixes: list[str] | None = None) -> str:
    """Normalize a filename to a canonical form for title-bucket comparison.

    Strips extension, a trailing ``(N)`` marker, a single leading ``x``, and a
    leading export prefix; lowercases; collapses non-alphanumerics to spaces.
    """
    prefixes = export_prefixes if export_prefixes is not None else DEFAULT_EXPORT_PREFIXES
    stem, _, _ext = filename.rpartition(".")
    if not stem:
        stem = filename
    stem = _VERSION_RE.sub("", stem)
    stem = stem.lower()
    if stem.startswith("x") and len(stem) > 1:
        stem = stem[1:]
    for prefix in prefixes:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    stem = re.sub(r"[^a-z0-9]+", " ", stem)
    return stem.strip()


def shingles(text: str, k: int = 5) -> set[str]:
    """Return set of k-word shingles over whitespace-normalized lowercased tokens.

    Strips YAML frontmatter and fenced code blocks before shingling. Empty or
    short text returns an empty set safely.
    """
    text = _FRONTMATTER_RE.sub("", text)
    text = _FENCED_CODE_RE.sub("", text)
    tokens = text.lower().split()
    if len(tokens) < k:
        return set()
    return {" ".join(tokens[i: i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: set, b: set) -> float:
    """Jaccard similarity |a∩b| / |a∪b|. Returns 0.0 if both sets are empty."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


class _UnionFind:
    def __init__(self, n: int):
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[ry] = rx


def find_clusters(paths: list[str], threshold: float = 0.80, *,
                  export_prefixes: list[str] | None = None,
                  generic_stems: list[str] | None = None) -> list[list[str]]:
    """Find near-duplicate clusters among ``paths``.

    Returns only clusters with >=2 members, each a sorted list of paths. Files
    with unique normalized titles (or generic basenames) are never compared.
    """
    stems = set(generic_stems if generic_stems is not None else DEFAULT_GENERIC_STEMS)
    buckets: dict[str, list[str]] = {}
    for path in paths:
        if _is_generic(os.path.basename(path), stems):
            continue
        key = normalize_title(os.path.basename(path), export_prefixes)
        buckets.setdefault(key, []).append(path)

    all_clusters: list[list[str]] = []
    for _key, bucket in buckets.items():
        if len(bucket) < 2:
            continue
        n = len(bucket)
        uf = _UnionFind(n)
        bucket_shingles: list[set[str]] = []
        for path in bucket:
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                text = ""
            bucket_shingles.append(shingles(text))
        for i in range(n):
            for j in range(i + 1, n):
                if jaccard(bucket_shingles[i], bucket_shingles[j]) >= threshold:
                    uf.union(i, j)
        groups: dict[int, list[str]] = {}
        for i, path in enumerate(bucket):
            groups.setdefault(uf.find(i), []).append(path)
        for group in groups.values():
            if len(group) >= 2:
                all_clusters.append(sorted(group))
    return all_clusters


def pick_canonical(cluster: list[str]) -> tuple[str, list[str]]:
    """Choose the keeper from a cluster of near-duplicate paths.

    Preference (ascending sort key, first = best): non-``x`` basename, then larger
    file, then lexicographically smallest path. Returns ``(canonical, losers)``.
    """
    def _sort_key(path: str):
        basename = os.path.basename(path)
        is_x = 1 if basename.startswith("x") else 0
        size = os.path.getsize(path) if os.path.exists(path) else 0
        return (is_x, -size, path)

    ordered = sorted(cluster, key=_sort_key)
    return ordered[0], sorted(ordered[1:])


def _scan_md(roots: list[str]) -> list[str]:
    found: list[str] = []
    for root in roots:
        root_abs = os.path.abspath(root)
        for dirpath, _dirs, filenames in os.walk(root_abs):
            for name in filenames:
                if name.lower().endswith(".md"):
                    found.append(os.path.join(dirpath, name))
    return found


def _common_base(paths: list[str]) -> str:
    if not paths:
        return ""
    dirs = [os.path.dirname(os.path.abspath(p)) for p in paths]
    return os.path.commonpath(dirs)


def run(roots: list[str], cold_dir: str, manifest_path: str,
        threshold: float = 0.80, apply: bool = False, *,
        export_prefixes: list[str] | None = None,
        generic_stems: list[str] | None = None,
        path_style: str = "native") -> list[dict]:
    """Scan roots for ``*.md``, find near-dup clusters, plan (or execute) merges.

    Dry-run (default) returns the plan and writes nothing. Apply moves losers to
    ``cold_dir`` (preserving relative structure) and logs each via the manifest.
    NEVER deletes; only moves. Plan entry: ``{canonical, losers, dst_map}``.
    """
    cold_abs = os.path.abspath(cold_dir)
    all_paths = _scan_md(roots)
    if not all_paths:
        return []
    base = _common_base(all_paths)
    clusters = find_clusters(all_paths, threshold=threshold,
                             export_prefixes=export_prefixes,
                             generic_stems=generic_stems)
    plan: list[dict] = []
    for cluster in clusters:
        canonical, losers = pick_canonical(cluster)
        dst_map: dict[str, str] = {}
        for loser in losers:
            loser_abs = os.path.abspath(loser)
            try:
                rel = os.path.relpath(loser_abs, base)
            except ValueError:
                rel = os.path.basename(loser_abs)
            dst_map[loser] = os.path.join(cold_abs, rel)
        plan.append({"canonical": canonical, "losers": losers, "dst_map": dst_map})

    if not apply:
        return plan

    for entry in plan:
        canonical = entry["canonical"]
        for loser in entry["losers"]:
            dst = entry["dst_map"][loser]
            loser_abs = os.path.abspath(loser)
            try:
                size_bytes = os.path.getsize(loser_abs)
                sha = sha256_file(loser_abs)
            except OSError:
                size_bytes = 0
                sha = ""
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(loser_abs, dst)
            _manifests.append(
                manifest_path, op="move", src_abs=loser_abs, dst_abs=dst,
                sha256=sha, size_bytes=size_bytes,
                reason=f"near-dup-merge; keeper={canonical}",
                stage="neardup", reversible=True, path_style=path_style,
            )
    return plan
