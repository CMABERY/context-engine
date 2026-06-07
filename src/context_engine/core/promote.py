"""Promotion gate: inbox -> hot/<domain>/, enforced and logged.

Four gates, in order:

1. ``chunk_lint`` passes (no section-shape flags),
2. a sibling ``.gate.json`` report exists,
3. no-loss verification by archetype — near-lossless: coverage >= per-archetype
   floor AND zero UNEXPLAINED missing facts (each missing fact must appear in the
   artifact's Stripping Ledger); aggressive: faithfulness >= floor AND a
   non-empty Stripping Ledger,
4. a ``sources[]`` sha256 link-back is present in the frontmatter.

All policy (domain map, floors, aggressive set, chunk limits) is parameterized
with generic defaults — no corpus-specific vocabulary is baked in.
"""
from __future__ import annotations

import json
import os
import re
import shutil

import yaml

from ..models import (
    DEFAULT_AGGRESSIVE_ARCHETYPES,
    DEFAULT_COVERAGE_FLOORS,
    DEFAULT_DOMAIN_MAP,
)
from ..utils import hashing, manifests
from . import chunk_lint

DEFAULT_FAITHFULNESS_FLOOR = 0.90
DEFAULT_FALLBACK_FLOOR = 0.95
DEFAULT_DOMAIN = "reference"

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_LEDGER_RE = re.compile(
    r"^##+\s*stripping ledger\s*$\n(.*?)(?=^\#{1,2}\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


class PromotionError(Exception):
    pass


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _parse_frontmatter(text: str) -> dict:
    m = _FM_RE.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _ledger_text(text: str) -> str:
    m = _LEDGER_RE.search(text)
    return m.group(1) if m else ""


def promote(inbox_path: str, hot_root: str, manifest_path: str, *,
            domain_map: dict[str, str] | None = None,
            default_domain: str = DEFAULT_DOMAIN,
            coverage_floors: dict[str, float] | None = None,
            aggressive_archetypes: list[str] | None = None,
            faithfulness_floor: float = DEFAULT_FAITHFULNESS_FLOOR,
            fallback_floor: float = DEFAULT_FALLBACK_FLOOR,
            max_est_tokens: int = chunk_lint.DEFAULT_MAX_EST_TOKENS,
            max_chars: int = chunk_lint.DEFAULT_MAX_CHARS,
            path_style: str = "native") -> dict:
    """Run all four gates and, if they pass, move the artifact into its domain."""
    domain_map = domain_map if domain_map is not None else DEFAULT_DOMAIN_MAP
    coverage_floors = (coverage_floors if coverage_floors is not None
                       else DEFAULT_COVERAGE_FLOORS)
    aggressive = set(aggressive_archetypes
                     if aggressive_archetypes is not None
                     else DEFAULT_AGGRESSIVE_ARCHETYPES)

    if not os.path.isfile(inbox_path):
        raise PromotionError(f"inbox artifact not found: {inbox_path}")
    with open(inbox_path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    # Gate 1 — chunk_lint must pass (empty flag list).
    flags = chunk_lint.lint(inbox_path, max_est_tokens=max_est_tokens,
                            max_chars=max_chars)
    if flags:
        raise PromotionError(f"chunk_lint failed ({len(flags)} flags): {flags[:3]}")

    # Gate 2 — sibling .gate.json must exist.
    gate_path = inbox_path + ".gate.json"
    if not os.path.isfile(gate_path):
        raise PromotionError(f"no .gate.json report beside artifact: {gate_path}")
    with open(gate_path, "r", encoding="utf-8") as fh:
        report = json.loads(fh.read())
    archetype = report.get("archetype", "EXPLORATORY_CHAT")

    # Gate 3 — no-loss verification, routed by archetype.
    if archetype in aggressive:
        score = float(report.get("faithfulness", 0.0))
        unsupported = list(report.get("unsupported", []))
        if score < faithfulness_floor:
            raise PromotionError(
                f"faithfulness {score:.3f} below floor {faithfulness_floor} "
                f"({archetype}); unsupported specifics: {unsupported[:5]}")
        if not _ledger_text(text).strip():
            raise PromotionError(
                f"{archetype} requires a non-empty Stripping Ledger "
                f"(documents dropped categories)")
        gate_summary = f"faithfulness={score:.3f}>={faithfulness_floor}, ledger present"
    else:
        coverage = float(report.get("coverage", 0.0))
        missing = list(report.get("missing", []))
        floor = coverage_floors.get(archetype, fallback_floor)
        if coverage < floor:
            raise PromotionError(
                f"coverage {coverage:.3f} below {archetype} floor {floor}")
        ledger = _normalize(_ledger_text(text))
        unexplained = [f for f in missing if _normalize(f) not in ledger]
        if unexplained:
            raise PromotionError(
                f"{len(unexplained)} unexplained dropped fact(s) "
                f"(not in Stripping Ledger): {unexplained[:5]}")
        gate_summary = f"coverage={coverage:.3f}>={floor}, 0 unexplained drops"

    # Gate 4 — sources[] sha256 link-back present.
    fm = _parse_frontmatter(text)
    sources = fm.get("sources") or []
    if not (isinstance(sources, list) and sources and
            all(isinstance(s, dict) and s.get("sha256") for s in sources)):
        raise PromotionError("missing sources[] sha256 link-back in frontmatter")

    # All gates pass — move into the domain subfolder and log.
    domain = domain_map.get(str(fm.get("type", "")).lower(), default_domain)
    dst_dir = os.path.join(hot_root, domain)
    os.makedirs(dst_dir, exist_ok=True)
    dst_abs = os.path.join(dst_dir, os.path.basename(inbox_path))
    # Destination collision policy: never overwrite an existing hot artifact.
    # Raising (vs. shutil.move's platform-dependent overwrite/OSError) keeps the
    # failure deterministic and non-fatal — gate_and_promote catches it.
    if os.path.exists(dst_abs):
        raise PromotionError(
            f"destination already exists (hot name collision): {dst_abs}. "
            f"Resolve or rename the existing artifact before promoting.")

    sha = hashing.sha256_file(inbox_path)
    size = os.path.getsize(inbox_path)
    src_abs = os.path.abspath(inbox_path)
    shutil.move(inbox_path, dst_abs)

    manifests.append(
        manifest_path, op="promote",
        src_abs=src_abs, dst_abs=os.path.abspath(dst_abs),
        sha256=sha, size_bytes=size,
        reason=f"promoted {archetype} artifact ({gate_summary})",
        stage="promote", reversible=True, path_style=path_style,
    )
    return {"ok": True, "dst_abs": os.path.abspath(dst_abs),
            "archetype": archetype, "gate": gate_summary, "domain": domain}
