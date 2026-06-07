"""Deterministic 'outside-signal' no-loss extractor and gate.

``extract_facts()`` pulls load-bearing signals from source text. Scope is
DELIBERATELY narrow (not 'every integer'): naive over-extraction makes the gate
unpassable. ``gate()`` reports ``{missing, coverage}`` for near-lossless
archetypes; ``faithfulness()`` runs the reverse, hallucination-catching check for
aggressive archetypes (every specific the artifact asserts must appear in the
source). The hard enforcement (zero UNEXPLAINED missing) lives in
:mod:`context_engine.core.promote`, which reconciles ``missing`` against the
artifact's Stripping Ledger.

Pure functions over text — no I/O, no config.
"""
from __future__ import annotations

import re

_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")
_MONEY_RE = re.compile(r"\$\d[\d,]*\d(?:\.\d+)?|\$\d(?:\.\d+)?")
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?%")
_NUMBER_RE = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")
_ALLCAPS_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_PROPER_RE = re.compile(r"\b(?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+)+\b")
_DECISION_RE = re.compile(
    r"^.*\b(?:decided|decide|chose|chosen|rejected|adopt(?:ed)?|selected|"
    r"will|must|shall|deferred|settled)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
_FENCE_RE = re.compile(r"```[a-zA-Z0-9_-]*\n(.*?)```", re.DOTALL)


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_facts(source_text: str) -> list[str]:
    """Extract load-bearing facts (coverage direction) from source text."""
    facts: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        v = value.strip()
        if not v:
            return
        key = _normalize(v).lower()
        if key not in seen:
            seen.add(key)
            facts.append(v)

    for block in _FENCE_RE.findall(source_text):
        add(block.strip())

    scalar_text = _FENCE_RE.sub(" ", source_text)

    for rx in (_DATE_RE, _MONEY_RE):
        for m in rx.findall(scalar_text):
            add(m)
    for m in _ALLCAPS_RE.findall(scalar_text):
        add(m)
    for m in _PROPER_RE.findall(scalar_text):
        add(m)
    # finditer + group(0) so we keep the whole decision LINE, not a sub-group.
    for m in _DECISION_RE.finditer(scalar_text):
        add(_normalize(m.group(0)))
    for m in _NUMBER_RE.findall(scalar_text):
        add(m)

    return facts


def gate(source_text: str, artifact_text: str) -> dict:
    """Coverage gate: which source facts are absent from the artifact."""
    facts = extract_facts(source_text)
    if not facts:
        return {"missing": [], "coverage": 1.0}
    art_norm = _normalize(artifact_text).lower()
    missing = [f for f in facts if _normalize(f).lower() not in art_norm]
    coverage = (len(facts) - len(missing)) / len(facts)
    return {"missing": missing, "coverage": coverage}


def atomic_facts(text: str) -> list[str]:
    """Short, checkable specifics for the FAITHFULNESS direction (not prose or
    code/thinking fences): money, percentages, dates, ALLCAPS tokens, and
    multi-word Proper-Noun phrases. Deliberately excludes free-text decision
    lines and fenced blocks, which cannot be substring-verified across paraphrase.
    """
    facts: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        v = value.strip()
        if not v:
            return
        key = _normalize(v).lower()
        if key not in seen:
            seen.add(key)
            facts.append(v)

    scalar = _FENCE_RE.sub(" ", text)
    for rx in (_MONEY_RE, _PERCENT_RE, _DATE_RE):
        for m in rx.findall(scalar):
            add(m)
    for m in _ALLCAPS_RE.findall(scalar):
        add(m)
    for m in _PROPER_RE.findall(scalar):
        add(m)
    return facts


def faithfulness(source_text: str, artifact_text: str) -> dict:
    """Reverse, hallucination-catching check for AGGRESSIVE distillation: every
    atomic specific the ARTIFACT asserts must appear in the SOURCE. Returns
    ``{unsupported: [...], score: 0..1}``. The cold original (sha256-linked) is
    the real no-loss net; this gate only ensures the hot artifact does not
    fabricate.
    """
    facts = atomic_facts(artifact_text)
    if not facts:
        return {"unsupported": [], "score": 1.0}
    src_norm = _normalize(source_text).lower()
    unsupported = [f for f in facts if _normalize(f).lower() not in src_norm]
    score = (len(facts) - len(unsupported)) / len(facts)
    return {"unsupported": unsupported, "score": score}
