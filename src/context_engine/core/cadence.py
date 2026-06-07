"""Ongoing-cadence curation driver. Dry-run by default; ``apply`` mutates + logs.

Full pipeline::

  0 layer0 lossless dedup      1 detect new (provenance + delta)
  2 classify                   3 route: queue aggressive / seed near-lossless
  4 gatecalc                   5 promote
  6 near-dup new-vs-hot (hot wins)  7 normalize hot
  8 reindex                    (recall validation is left to the caller)

Every mutation is append-only-logged via a single run manifest and is reversible.
All paths and policy come from :class:`~context_engine.models.EngineConfig`; this
module embeds nothing corpus-specific.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import tempfile

from ..config import resolve_manifest_path
from ..models import EngineConfig
from ..utils import manifests
from ..utils.hashing import sha256_file
from . import classify as _classify
from . import (
    delta,
    distill_queue,
    gatecalc,
    layer0,
    neardup,
    normalize,
    promote as _promote,
    provenance,
    seed,
)

_LEDGER = "\n\n## Stripping Ledger\nDropped: none — near-verbatim seed.\n"


# ---------------------------------------------------------------------------
# Effective path resolution (sensible derivations when optional paths are unset)
# ---------------------------------------------------------------------------

def _inbox_dir(cfg: EngineConfig) -> str:
    return cfg.inbox_dir or os.path.join(cfg.hot_root or "", "_inbox")


def _queue_dir(cfg: EngineConfig) -> str:
    return cfg.queue_dir or os.path.join(_inbox_dir(cfg), "_queue")


def _near_dup_cold(cfg: EngineConfig) -> str:
    return cfg.near_dup_cold or os.path.join(cfg.held_root or "", "near-dup")


def _seen(cfg: EngineConfig, manifest_path: str, src_path: str, sha: str,
          size: int, note: str) -> None:
    manifests.append(manifest_path, op="cadence-seen", src_abs=src_path,
                     dst_abs=None, sha256=sha, size_bytes=size,
                     reason=f"cadence evaluated: {note}", stage="cadence",
                     reversible=True, path_style=cfg.path_style)


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def detect(cfg: EngineConfig, db: str | None = None) -> list[dict]:
    """Stage 1: (re)build the INDEX from manifests, return unseen ``*.md``.

    ``db`` defaults to ``cfg.index_db``. Pass an alternate path (e.g. a throwaway
    one) to detect without touching the configured index — see ``detect_readonly``.
    """
    db = db or cfg.index_db
    os.makedirs(cfg.manifests_dir, exist_ok=True)
    provenance.build(cfg.manifests_dir, db, cfg.effective_tier_rules())
    return delta.new_files(cfg.live_roots, db, cfg.hot_root)


def detect_readonly(cfg: EngineConfig) -> list[dict]:
    """``detect()`` that never touches the configured ``index_db``.

    Builds the provenance index into a throwaway temporary database, so
    read-only/dry-run commands (``observe``, ``delta``, ``cadence --dry-run``)
    report the new-set without mutating any configured corpus path.
    """
    tmpdir = tempfile.mkdtemp(prefix="ce-index-")
    try:
        return detect(cfg, os.path.join(tmpdir, "index.sqlite"))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _unique_inbox_name(inbox: str, name: str, sha: str) -> str:
    """Return an inbox filename that does not collide with an existing artifact.

    Two distinct sources can share a basename; without this, the second seeded
    artifact would silently overwrite the first in the inbox (and both would be
    logged cadence-seen, dropping one forever). On collision, disambiguate with a
    sha prefix — deterministic, mirroring the distill-queue's collision policy.
    """
    if not os.path.exists(os.path.join(inbox, name)):
        return name
    stem, ext = os.path.splitext(name)
    return f"{stem}-{sha[:8].lower()}{ext}"


def classify_new(cfg: EngineConfig, new: list[dict]) -> list[dict]:
    """Stage 2: tag each new file with archetype + aggressive flag."""
    aggressive = set(cfg.aggressive_archetypes)
    rows: list[dict] = []
    for f in new:
        arch = _classify.classify(f["path"]).name
        rows.append({**f, "archetype": arch, "aggressive": arch in aggressive})
    return rows


def route(cfg: EngineConfig, manifest_path: str, rows: list[dict],
          apply: bool) -> dict:
    """Stage 3: queue aggressive sources; mechanically seed near-lossless to inbox."""
    inbox = _inbox_dir(cfg)
    queue = _queue_dir(cfg)
    seeded = queued = 0
    hints: dict[str, str] = {}  # inbox filename -> archetype (for gate routing)
    for row in rows:
        if row["aggressive"]:
            if apply:
                distill_queue.enqueue(
                    queue, source_path=row["path"], source_sha=row["sha256"],
                    suggested_domain=cfg.default_domain, inbox_dir=inbox,
                    export_prefixes=cfg.export_prefixes,
                    faithfulness_floor=cfg.faithfulness_floor)
                _seen(cfg, manifest_path, row["path"], row["sha256"], row["size"],
                      "queued-aggressive")
            queued += 1
            continue
        if apply:
            with open(row["path"], "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
            base = os.path.basename(row["path"])
            title = os.path.splitext(base)[0]
            atype = cfg.archetype_type_map.get(row["archetype"], "reference-note")
            artifact = seed.build_artifact(
                body=raw + _LEDGER, sha256=row["sha256"], title=title,
                src_path=row["path"], artifact_type=atype,
                artifact_id=cfg.id_prefix + title.lower().replace(" ", "-")[:60],
                default_status=cfg.default_status)
            os.makedirs(inbox, exist_ok=True)
            # Disambiguate so a same-basename source can't overwrite a prior seed.
            name = _unique_inbox_name(inbox, base, row["sha256"])
            with open(os.path.join(inbox, name), "w", encoding="utf-8") as fh:
                fh.write(artifact)
            hints[name] = row["archetype"]
            _seen(cfg, manifest_path, row["path"], row["sha256"], row["size"],
                  "seeded-near-lossless")
        seeded += 1
    return {"seeded": seeded, "queued": queued, "hints": hints}


def _archetype_for_inbox(cfg: EngineConfig, name: str, hint: dict) -> str:
    if name in hint:
        return hint[name]
    gate_path = os.path.join(_inbox_dir(cfg), name + ".gate.json")
    if os.path.exists(gate_path):
        try:
            with open(gate_path, encoding="utf-8") as fh:
                return json.load(fh).get("archetype", "EXPLORATORY_CHAT")
        except (OSError, json.JSONDecodeError):
            pass
    return "EXPLORATORY_CHAT"


def gate_and_promote(cfg: EngineConfig, manifest_path: str, hint: dict,
                     apply: bool) -> dict:
    """Stages 4-5: ensure a ``.gate.json`` then promote each inbox artifact.

    Per-artifact failures are caught and reported, never fatal to the run.
    """
    inbox = _inbox_dir(cfg)
    promoted: list[str] = []
    failures: list[dict] = []
    inbox_mds = sorted(glob.glob(os.path.join(inbox, "*.md")))
    for art in inbox_mds:
        name = os.path.basename(art)
        archetype = _archetype_for_inbox(cfg, name, hint)
        if not apply:
            continue
        gatecalc.write_gate(art, archetype, cfg.index_db,
                            aggressive_archetypes=cfg.aggressive_archetypes)
        try:
            res = _promote.promote(
                art, cfg.hot_root, manifest_path,
                domain_map=cfg.domain_map, default_domain=cfg.default_domain,
                coverage_floors=cfg.coverage_floors,
                aggressive_archetypes=cfg.aggressive_archetypes,
                faithfulness_floor=cfg.faithfulness_floor,
                max_est_tokens=cfg.chunk_max_est_tokens,
                max_chars=cfg.chunk_max_chars, path_style=cfg.path_style)
            promoted.append(res["dst_abs"])
        except _promote.PromotionError as exc:
            failures.append({"artifact": name, "error": str(exc)})
    return {"promoted": len(promoted), "promoted_paths": promoted,
            "failures": failures, "inbox_pending": len(inbox_mds)}


def dedup_hot(cfg: EngineConfig, manifest_path: str, just_promoted: list[str],
              apply: bool) -> list[dict]:
    """Stage 6: cluster hot near-dups; existing-hot-always-wins.

    A cluster with any established (not just-promoted) member keeps an established
    canonical and moves only the just-promoted losers cold. All-new clusters fall
    back to :func:`neardup.pick_canonical`.
    """
    promoted = {os.path.abspath(p) for p in just_promoted}
    near_dup_cold = _near_dup_cold(cfg)
    md_files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(cfg.hot_root):
        dirnames[:] = [d for d in dirnames if d != "_inbox"]
        for n in filenames:
            if n.lower().endswith(".md"):
                md_files.append(os.path.join(dirpath, n))
    clusters = neardup.find_clusters(
        md_files, threshold=cfg.near_dup_threshold,
        export_prefixes=cfg.export_prefixes, generic_stems=cfg.generic_stems)
    moves: list[dict] = []
    for cluster in clusters:
        established = [p for p in cluster if os.path.abspath(p) not in promoted]
        if established:
            canonical, _ = neardup.pick_canonical(established)
            losers = [p for p in cluster if os.path.abspath(p) in promoted]
        else:
            canonical, losers = neardup.pick_canonical(cluster)
        for loser in losers:
            rel = os.path.relpath(loser, cfg.hot_root)
            moves.append({"loser": loser, "canonical": canonical,
                          "dst": os.path.join(near_dup_cold, rel)})
    if apply:
        for m in moves:
            os.makedirs(os.path.dirname(m["dst"]), exist_ok=True)
            sha = sha256_file(m["loser"])
            size = os.path.getsize(m["loser"])
            shutil.move(m["loser"], m["dst"])
            manifests.append(manifest_path, op="move", src_abs=m["loser"],
                             dst_abs=m["dst"], sha256=sha, size_bytes=size,
                             reason=f"cadence near-dup new-vs-hot; keeper={m['canonical']}",
                             stage="cadence-neardup", reversible=True,
                             path_style=cfg.path_style)
    return moves


def normalize_step(cfg: EngineConfig, manifest_path: str, apply: bool) -> list[dict]:
    """Stage 7: normalize hot frontmatter/encoding (idempotent)."""
    return normalize.run(cfg.hot_root, cfg.index_db, manifest_path, apply=apply,
                         id_prefix=cfg.id_prefix, valid_statuses=cfg.valid_statuses,
                         status_map=cfg.status_map, default_status=cfg.default_status,
                         path_style=cfg.path_style)


def layer0_step(cfg: EngineConfig, manifest_path: str, apply: bool) -> dict:
    """Stage 0: lossless dedup of the corpus (runs FIRST so detect sees it)."""
    return layer0.run(
        org_root=cfg.org_root, live_roots=cfg.live_roots, held_root=cfg.held_root,
        superseded_root=cfg.superseded_root or os.path.join(cfg.held_root or "", "superseded-originals"),
        manifest_path=manifest_path, apply=apply,
        exclude_globs=cfg.exclude_globs, path_style=cfg.path_style)


def reindex_step(cfg: EngineConfig, apply: bool, runner=None) -> dict:
    """Stage 8: refresh the recall index via the qmd adapter.

    A missing/failed backend is reported, never fatal — the corpus mutations from
    earlier stages are already logged and reversible; reindex can be re-run.
    """
    import subprocess

    from ..adapters import qmd as qmd_adapter
    try:
        return qmd_adapter.reindex(qmd=cfg.qmd, runner=runner, apply=apply)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "skipped": True}


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def run(cfg: EngineConfig, apply: bool = False, runner=None,
        manifest_path: str | None = None) -> dict:
    """Full pipeline. Dry-run reports the plan; apply executes + logs.

    Stage 0 (Layer-0 dedup) runs FIRST so detect sees the deduped tree.
    """
    mp = manifest_path or resolve_manifest_path(cfg, "cadence")
    l0 = layer0_step(cfg, mp, apply)
    # Dry-run must not mutate the configured index_db -> detect via a throwaway db.
    new = detect(cfg) if apply else detect_readonly(cfg)
    rows = classify_new(cfg, new)
    routed = route(cfg, mp, rows, apply)
    gp = gate_and_promote(cfg, mp, routed["hints"], apply)
    moves = dedup_hot(cfg, mp, gp["promoted_paths"], apply) if apply else []
    norm = normalize_step(cfg, mp, apply) if apply else []
    idx = reindex_step(cfg, apply, runner=runner)
    return {
        "manifest_path": mp,
        "layer0": l0,
        "new": len(new),
        "seeded": routed["seeded"],
        "queued": routed["queued"],
        "promoted": gp["promoted"],
        "inbox_pending": gp["inbox_pending"],
        "failures": gp["failures"],
        "near_dup_moves": len(moves),
        "normalized": sum(1 for p in norm if p.get("changed")),
        "reindex": idx,
    }


def baseline(cfg: EngineConfig, apply: bool, manifest_path: str | None = None) -> dict:
    """Record every currently-new corpus file as cadence-seen WITHOUT curating it.

    Run once (``--apply``) to establish the starting point so subsequent runs only
    act on content that arrives AFTER the baseline.
    """
    mp = manifest_path or resolve_manifest_path(cfg, "baseline")
    # Dry-run baseline reports the new-set without touching the configured index.
    new = detect(cfg) if apply else detect_readonly(cfg)
    if apply:
        for f in new:
            _seen(cfg, mp, f["path"], f["sha256"], f["size"], "baseline")
    return {"baselined": len(new), "manifest_path": mp}
