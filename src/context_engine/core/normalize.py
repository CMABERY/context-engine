"""Frontmatter + encoding normalization for the hot surface.

Normalizes artifacts to a unified convention:

* ``id``: ``<id_prefix><slug>`` (lowercased) — prefix is configurable
  (defaults to a generic ``KB-``),
* ``status``: mapped to a unified enum,
* ``distill``: default ``3`` if missing,
* encoding: common UTF-8 mojibake repaired (idempotent),
* ``sources``: optionally backfilled from an extractions map via the provenance
  INDEX.

Everything corpus-specific (the id prefix, the status vocabulary) is a parameter.
"""
from __future__ import annotations

import json
import os
import sqlite3

import yaml

from ..models import DEFAULT_STATUS_MAP, DEFAULT_VALID_STATUSES
from ..utils import manifests as _manifests
from ..utils.hashing import sha256_file

# Mojibake replacement table: latin-1 misread UTF-8 sequences -> correct Unicode.
_MOJIBAKE_TABLE: list[tuple[str, str]] = [
    ("\xe2\x80\x94", "—"),  # em dash
    ("\xe2\x80\x93", "–"),  # en dash
    ("\xe2\x80\x99", "’"),  # right single quote / apostrophe
    ("\xe2\x80\x98", "‘"),  # left single quote
    ("\xe2\x80\x9c", "“"),  # left double quote
    ("\xe2\x80\x9d", "”"),  # right double quote
    ("\xe2\x80\xa6", "…"),  # horizontal ellipsis
    ("\xe2\x80\x8b", ""),        # zero-width space (remove)
    ("\xc3\xa9", "\xe9"),        # e acute
    ("\xc3\xa0", "\xe0"),        # a grave
    ("\xc3\xb3", "\xf3"),        # o acute
    ("\xc3\xbc", "\xfc"),        # u diaeresis
    ("\xc2\xa0", " "),           # non-breaking space -> space
    ("\xc2\xb7", "\xb7"),        # middle dot
    ("�", ""),              # Unicode replacement char (remove)
]


def apply_id_convention(fm: dict, fallback_slug: str, *,
                        id_prefix: str = "KB-",
                        valid_statuses: list[str] | None = None,
                        status_map: dict[str, str] | None = None,
                        default_status: str = "seeded") -> dict:
    """Return a new frontmatter dict with a prefixed id, unified status, distill default."""
    valid = set(valid_statuses if valid_statuses is not None else DEFAULT_VALID_STATUSES)
    smap = status_map if status_map is not None else DEFAULT_STATUS_MAP
    result = dict(fm)

    existing_id = result.get("id", "")
    if not existing_id or not str(existing_id).startswith(id_prefix):
        slug = (str(existing_id) if existing_id else fallback_slug).lower()
        result["id"] = id_prefix + slug

    raw_status = str(result.get("status", "")).strip().lower()
    if raw_status in valid:
        result["status"] = raw_status
    elif raw_status in smap:
        result["status"] = smap[raw_status]
    else:
        result["status"] = default_status

    if "distill" not in result:
        result["distill"] = 3
    return result


def repair_encoding(text: str) -> str:
    """Fix common UTF-8 mojibake best-effort. Idempotent."""
    for mojibake, correct in _MOJIBAKE_TABLE:
        if mojibake in text:
            text = text.replace(mojibake, correct)
    return text


def sha256_for_path(db: str, query_path: str) -> str | None:
    """Return the sha256 in the provenance INDEX matching ``query_path`` by basename."""
    query_base = os.path.basename(query_path.replace("\\", "/")).lower()
    if not query_base:
        return None
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT sha256, path FROM files").fetchall()
    finally:
        conn.close()
    for sha, stored_path in rows:
        if os.path.basename(stored_path.replace("\\", "/")).lower() == query_base:
            return sha
    return None


def backfill_sources(fm: dict, extractions_json_path: str, db: str) -> dict:
    """Merge resolved provenance entries into ``fm["sources"]`` from extractions.json."""
    if not os.path.isfile(extractions_json_path):
        return fm
    try:
        with open(extractions_json_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return fm

    result = dict(fm)
    existing_sources: list[dict] = list(result.get("sources") or [])
    existing_shas = {s["sha256"] for s in existing_sources if "sha256" in s}
    new_sources = list(existing_sources)
    for entry in entries:
        name = entry.get("name", "")
        path = entry.get("path", name)
        sha = sha256_for_path(db, path) or sha256_for_path(db, name)
        if sha and sha not in existing_shas:
            new_sources.append({"sha256": sha, "title": name, "path": path})
            existing_shas.add(sha)
    result["sources"] = new_sources
    return result


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            try:
                data = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                return {}, text
            body = text[end + len("\n---\n"):]
            if isinstance(data, dict):
                return data, body
    return {}, text


def normalize_file(text: str, fallback_slug: str,
                   extractions_json_path: str | None, db: str | None, *,
                   id_prefix: str = "KB-",
                   valid_statuses: list[str] | None = None,
                   status_map: dict[str, str] | None = None,
                   default_status: str = "seeded") -> str:
    """Normalize a single markdown file's text (encoding + frontmatter)."""
    text = repair_encoding(text)
    fm, body = _split_frontmatter(text)
    if not fm and not text.startswith("---\n"):
        return text
    if not fm:
        return text
    fm = apply_id_convention(fm, fallback_slug, id_prefix=id_prefix,
                             valid_statuses=valid_statuses, status_map=status_map,
                             default_status=default_status)
    if extractions_json_path and db:
        fm = backfill_sources(fm, extractions_json_path, db)
    fm_yaml = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip("\n")
    return "---\n" + fm_yaml + "\n---\n\n" + body.lstrip("\n")


def run(hot_root: str, db: str | None, manifest_path: str, apply: bool = False, *,
        extractions_map: dict[str, str] | None = None,
        id_prefix: str = "KB-",
        valid_statuses: list[str] | None = None,
        status_map: dict[str, str] | None = None,
        default_status: str = "seeded",
        path_style: str = "native") -> list[dict]:
    """Walk ``hot_root/**/*.md``, normalize each file, return a plan list.

    Skips ``_inbox/`` directories and ``README.md``. On ``apply=True`` writes
    normalized content back and appends a manifest entry per changed file.
    """
    plan: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(hot_root):
        dirnames[:] = [d for d in dirnames if d != "_inbox"]
        for name in sorted(filenames):
            if name == "README.md" or not name.endswith(".md"):
                continue
            abs_path = os.path.join(dirpath, name)
            slug = os.path.splitext(name)[0].lower().replace(" ", "-")
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    original = f.read()
            except OSError:
                continue
            ext_path = extractions_map.get(abs_path) if extractions_map else None
            normalized = normalize_file(
                original, slug, ext_path, db, id_prefix=id_prefix,
                valid_statuses=valid_statuses, status_map=status_map,
                default_status=default_status)
            entry = {"path": abs_path, "slug": slug,
                     "changed": normalized != original}
            plan.append(entry)
            if apply and entry["changed"]:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(normalized)
                new_sha = sha256_file(abs_path)
                size = os.path.getsize(abs_path)
                _manifests.append(
                    manifest_path, op="normalize", src_abs=abs_path,
                    dst_abs=abs_path, sha256=new_sha, size_bytes=size,
                    reason="normalize-hot: id-convention+status-enum+encoding-repair",
                    stage="normalize", reversible=True, path_style=path_style,
                )
    return plan
