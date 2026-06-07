"""Layer-0 lossless cleanup driver. Dry-run by default; ``apply`` mutates + logs.

Policy (preserve-all, dedup-redundant):

* DELETE byte-identical redundant copies in the live tree and within the held
  root (one canonical per hash survives; recoverable by sha256 in the manifest).
  Byte-identical ``(N)`` accidental copies are handled here too — the keeper is
  the base name, so the ``(N)`` copy is the redundant one.
* MOVE true revision lineages (``(N)`` files that DIFFER from their base) cold to
  the superseded root, preserving structure (supersede-not-erase).
* Hard guard: every decision is content-hash + path based, never filename; and
  the pass is ``.md``-scoped so code/binaries are never touched.

There is no built-in config — the caller supplies every path.
"""
from __future__ import annotations

import os
import shutil

from ..models import DEFAULT_EXCLUDE_GLOBS
from ..utils import manifests
from ..utils.hashing import scan
from .dedup import classify_version_pairs, held_dupes, live_tree_dupes

STAGE = "layer0"


def _supersede_dst(org_root: str, superseded_root: str, src: str) -> str:
    rel = os.path.relpath(os.path.abspath(src), os.path.abspath(org_root))
    return os.path.join(superseded_root, rel)


def run(*, org_root: str, live_roots: list[str], held_root: str,
        superseded_root: str, manifest_path: str, apply: bool = False,
        exclude_globs: list[str] | None = None,
        path_style: str = "native") -> dict:
    """Plan (or execute) the Layer-0 lossless cleanup. Returns the plan counts."""
    excludes = list(exclude_globs) if exclude_globs is not None else (
        list(DEFAULT_EXCLUDE_GLOBS) + ["Archives/**", "archives/**", "zips/**"])

    index = scan(org_root, excludes)
    # .md-scoped: drop non-.md from every hash-set.
    index = {sha: [p for p in paths if p.lower().endswith(".md")]
             for sha, paths in index.items()}
    index = {sha: paths for sha, paths in index.items() if len(paths) >= 1}

    live = live_tree_dupes(index, live_roots, held_root)
    held = held_dupes(index, held_root)
    pairs = classify_version_pairs(live_roots)
    lineage = [p for p in pairs if p["kind"] == "lineage"]
    # A lineage variant also byte-identical to a canonical elsewhere is handled
    # by the delete pass; drop it from the move list so the split is exact.
    live_redundant = {r for d in live for r in d["redundant"]}
    lineage = [p for p in lineage if p["variant"] not in live_redundant]

    plan = {
        "live_delete": sum(len(d["redundant"]) for d in live),
        "held_delete": sum(len(d["redundant"]) for d in held),
        "lineage_move": len(lineage),
    }
    if not apply:
        return plan

    # DELETE live-tree redundant copies (canonical preserved).
    for d in live:
        for red in d["redundant"]:
            size = os.path.getsize(red)
            manifests.append(
                manifest_path, op="delete", src_abs=red, dst_abs=None,
                sha256=d["sha256"], size_bytes=size, stage=STAGE, reversible=True,
                reason=f"dedup:live-tree byte-identical; canonical={d['canonical']}",
                path_style=path_style)
            os.remove(red)

    # MOVE lineage variants cold (preserve structure).
    for p in lineage:
        if not os.path.exists(p["variant"]):
            continue
        dst = _supersede_dst(org_root, superseded_root, p["variant"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        size = os.path.getsize(p["variant"])
        manifests.append(
            manifest_path, op="move", src_abs=p["variant"], dst_abs=dst,
            sha256=p["variant_sha"], size_bytes=size, stage=STAGE, reversible=True,
            reason=f"lineage:older revision superseded; base={p['base']}",
            path_style=path_style)
        shutil.move(p["variant"], dst)

    # DELETE held redundant copies (one-per-hash kept).
    for d in held:
        for red in d["redundant"]:
            if not os.path.exists(red):
                continue
            size = os.path.getsize(red)
            manifests.append(
                manifest_path, op="delete", src_abs=red, dst_abs=None,
                sha256=d["sha256"], size_bytes=size, stage=STAGE, reversible=True,
                reason=f"dedup:held byte-identical redundant; canonical={d['canonical']}",
                path_style=path_style)
            os.remove(red)

    return plan
