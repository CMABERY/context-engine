"""Deterministic ``.gate.json`` computation for cadence promotion.

Bridges an out-of-band-written inbox artifact into the promotion gate: resolves
the artifact's cited source via the provenance INDEX, then computes the
archetype-appropriate no-loss report (faithfulness for aggressive chat,
source-coverage for near-lossless). Pure ``compute()`` + sidecar-writing
``write_gate()``.
"""
from __future__ import annotations

import json
import os

import yaml

from ..models import DEFAULT_AGGRESSIVE_ARCHETYPES
from ..utils.paths import to_local
from . import noloss, provenance


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


def _read_source(db: str, artifact_text: str) -> str | None:
    """Resolve and read the artifact's cited source. Tries the INDEX first
    (move-invariant by sha256), then falls back to the inline ``sources[].path``
    — essential on the first run, when a freshly-seeded source is not in the
    INDEX yet."""
    fm = _frontmatter(artifact_text)
    for s in (fm.get("sources") or []):
        if not isinstance(s, dict):
            continue
        # 1. INDEX resolution by sha256 (move-invariant)
        if s.get("sha256"):
            rec = provenance.resolve(db, str(s["sha256"]))
            for stored in rec.get("paths", []):
                local = to_local(stored)
                if os.path.exists(local):
                    with open(local, "r", encoding="utf-8", errors="replace") as fh:
                        return fh.read()
        # 2. Fallback: the inline provenance path recorded in the artifact
        inline = s.get("path")
        if inline:
            local = to_local(str(inline))
            if os.path.exists(local):
                with open(local, "r", encoding="utf-8", errors="replace") as fh:
                    return fh.read()
    return None


def compute(artifact_path: str, archetype: str, db: str,
            *, aggressive_archetypes: list[str] | None = None) -> dict | None:
    """Return the gate report dict, or ``None`` if the source cannot be resolved."""
    aggressive = set(aggressive_archetypes
                     if aggressive_archetypes is not None
                     else DEFAULT_AGGRESSIVE_ARCHETYPES)
    with open(artifact_path, "r", encoding="utf-8", errors="replace") as fh:
        artifact = fh.read()
    source = _read_source(db, artifact)
    if source is None:
        return None
    if archetype in aggressive:
        r = noloss.faithfulness(source, artifact)
        return {"archetype": archetype, "faithfulness": r["score"],
                "unsupported": r["unsupported"]}
    r = noloss.gate(source, artifact)
    return {"archetype": archetype, "coverage": r["coverage"],
            "missing": r["missing"]}


def write_gate(artifact_path: str, archetype: str, db: str,
               *, aggressive_archetypes: list[str] | None = None) -> dict | None:
    """Write ``<artifact_path>.gate.json`` if absent. Idempotent: returns ``None``
    if a sidecar already exists or the source is unresolvable."""
    gate_path = artifact_path + ".gate.json"
    if os.path.exists(gate_path):
        return None
    report = compute(artifact_path, archetype, db,
                     aggressive_archetypes=aggressive_archetypes)
    if report is None:
        return None
    with open(gate_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False))
    return report
