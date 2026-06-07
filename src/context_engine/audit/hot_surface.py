"""Read-only governance audit of the hot surface.

Static checks over every ``*.md`` under the hot root (excluding ``_inbox`` and
README infrastructure files). NOTHING is mutated. The audit reports structural
and schema health so the operational authority remains the live repo/tests — the
engine only certifies admissibility.

Checks per artifact:

* frontmatter parses to a mapping,
* required fields present (default ``id``, ``status``, ``sources``),
* a ``sources[]`` entry carries a sha256 link-back,
* ``type`` (if present) routes via the domain map,
* an H1 title exists,
* chunk-shape is clean (:mod:`context_engine.core.chunk_lint`),
* artifact size is under the advisory ceiling.

Plus a corpus-wide near-duplicate scan.
"""
from __future__ import annotations

import os

import yaml

from ..core import chunk_lint, neardup
from ..models import DEFAULT_DOMAIN_MAP

DEFAULT_REQUIRED_FIELDS = ("id", "status", "sources")
DEFAULT_OVERSIZE_BYTES = 51_200
_SKIP_BASENAMES = {"README.md", "_README.md"}


def _split_frontmatter(text: str) -> tuple[dict | None, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            try:
                data = yaml.safe_load(text[4:end])
            except yaml.YAMLError:
                return None, text[end + len("\n---\n"):]
            body = text[end + len("\n---\n"):]
            return (data if isinstance(data, dict) else None), body
    return None, text


def _has_h1(body: str) -> bool:
    for line in body.splitlines():
        if line.startswith("# "):
            return True
    return False


def audit_text(text: str, *, required_fields=DEFAULT_REQUIRED_FIELDS,
               domain_map: dict | None = None,
               max_est_tokens: int = chunk_lint.DEFAULT_MAX_EST_TOKENS,
               max_chars: int = chunk_lint.DEFAULT_MAX_CHARS) -> list[dict]:
    """Return a list of finding dicts for one artifact's text (empty = clean)."""
    domain_map = domain_map if domain_map is not None else DEFAULT_DOMAIN_MAP
    findings: list[dict] = []
    fm, body = _split_frontmatter(text)

    if fm is None:
        findings.append({"rule": "frontmatter_invalid",
                         "detail": "missing or unparseable YAML frontmatter"})
        return findings  # nothing else is checkable without frontmatter

    for fld in required_fields:
        if fld not in fm or fm.get(fld) in (None, "", [], {}):
            findings.append({"rule": "missing_field",
                             "detail": f"required field '{fld}' absent or empty"})

    sources = fm.get("sources") or []
    has_sha = isinstance(sources, list) and any(
        isinstance(s, dict) and s.get("sha256") for s in sources)
    if "sources" not in required_fields or sources:
        if not has_sha:
            findings.append({"rule": "missing_sha256_linkback",
                             "detail": "no sources[].sha256 provenance link-back"})

    art_type = str(fm.get("type", "")).lower()
    if art_type and art_type not in domain_map:
        findings.append({"rule": "unknown_type",
                         "detail": f"type '{art_type}' not in domain map"})

    if not _has_h1(body):
        findings.append({"rule": "missing_h1_title",
                         "detail": "no H1 ('# Title') heading in body"})

    for flag in chunk_lint.lint_text(text, max_est_tokens=max_est_tokens,
                                     max_chars=max_chars):
        findings.append({"rule": f"chunk:{flag['rule']}",
                         "detail": f"{flag['section']}: {flag['detail']}"})
    return findings


def audit_hot(hot_root: str, *, required_fields=DEFAULT_REQUIRED_FIELDS,
              domain_map: dict | None = None,
              oversize_bytes: int = DEFAULT_OVERSIZE_BYTES,
              near_dup_threshold: float = 0.60,
              max_est_tokens: int = chunk_lint.DEFAULT_MAX_EST_TOKENS,
              max_chars: int = chunk_lint.DEFAULT_MAX_CHARS,
              export_prefixes: list[str] | None = None,
              generic_stems: list[str] | None = None) -> dict:
    """Audit every artifact under ``hot_root``. Returns a structured report."""
    findings: list[dict] = []
    md_files: list[str] = []
    n_files = 0

    for dirpath, dirnames, filenames in os.walk(hot_root):
        dirnames[:] = [d for d in dirnames if d != "_inbox"]
        for name in sorted(filenames):
            if not name.endswith(".md") or name in _SKIP_BASENAMES:
                continue
            path = os.path.join(dirpath, name)
            md_files.append(path)
            n_files += 1
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError as exc:
                findings.append({"path": path, "rule": "read_error",
                                 "detail": str(exc)})
                continue
            for f in audit_text(text, required_fields=required_fields,
                                domain_map=domain_map, max_est_tokens=max_est_tokens,
                                max_chars=max_chars):
                findings.append({"path": path, **f})
            try:
                if os.path.getsize(path) > oversize_bytes:
                    findings.append({"path": path, "rule": "oversize",
                                     "detail": f"{os.path.getsize(path)} bytes "
                                               f"> {oversize_bytes}"})
            except OSError:
                pass

    near_dups = neardup.find_clusters(
        md_files, threshold=near_dup_threshold,
        export_prefixes=export_prefixes, generic_stems=generic_stems)
    for cluster in near_dups:
        findings.append({"path": cluster[0], "rule": "near_duplicate",
                         "detail": f"near-dup cluster: {cluster}"})

    by_rule: dict[str, int] = {}
    for f in findings:
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1

    return {
        "hot_root": hot_root,
        "files": n_files,
        "findings": findings,
        "findings_by_rule": by_rule,
        "near_dup_clusters": near_dups,
        "verdict": "PASS" if not findings else "FAIL",
    }
