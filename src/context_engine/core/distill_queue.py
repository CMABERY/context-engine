"""Out-of-band distill queue for aggressive (chat-style) content.

The cadence driver enqueues a descriptor per aggressive source; a human or agent
reads the queue, writes a faithful artifact into the inbox, and re-runs the driver
(which then computes the gate report and promotes). Descriptors are deterministic
and idempotent per source sha256.
"""
from __future__ import annotations

import glob
import json
import os
import re

from ..models import DEFAULT_DISTILL_INSTRUCTIONS, DEFAULT_EXPORT_PREFIXES

# Default faithfulness floor woven into the instruction text when the caller does
# not interpolate its own.
_DEFAULT_FLOOR = 0.90


def slug_for(source_path: str, export_prefixes: list[str] | None = None) -> str:
    """Derive a filesystem-safe slug from a source filename.

    Strips a leading export-tool prefix (e.g. ``claude-``/``chatgpt-``) and
    collapses non-alphanumerics to single hyphens.
    """
    prefixes = export_prefixes if export_prefixes is not None else DEFAULT_EXPORT_PREFIXES
    stem = os.path.splitext(os.path.basename(source_path))[0].lower()
    for prefix in prefixes:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return stem


def list_queue(queue_dir: str) -> list[dict]:
    if not os.path.isdir(queue_dir):
        return []
    out: list[dict] = []
    for path in sorted(glob.glob(os.path.join(queue_dir, "*.distill.json"))):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def enqueue(queue_dir: str, *, source_path: str, source_sha: str,
            suggested_domain: str, inbox_dir: str,
            archetype: str = "EXPLORATORY_CHAT",
            export_prefixes: list[str] | None = None,
            instructions: str | None = None,
            faithfulness_floor: float = _DEFAULT_FLOOR) -> dict | None:
    """Write ``<queue_dir>/<slug>.distill.json``. Idempotent.

    Returns ``None`` if a descriptor for this source sha already exists. If the
    slug collides with a *different* sha's descriptor, the filename is
    disambiguated with a sha prefix so neither is silently overwritten.
    """
    os.makedirs(queue_dir, exist_ok=True)
    sha = source_sha.upper()
    for existing in list_queue(queue_dir):
        if existing.get("source_sha256") == sha:
            return None
    slug = slug_for(source_path, export_prefixes)
    filename = f"{slug}.distill.json"
    target_name = f"{slug}.md"
    # Same-slug-different-sha collision (same sha was excluded above): disambiguate.
    if os.path.exists(os.path.join(queue_dir, filename)):
        suffix = sha[:8].lower()
        filename = f"{slug}-{suffix}.distill.json"
        target_name = f"{slug}-{suffix}.md"
    if instructions is None:
        instructions = DEFAULT_DISTILL_INSTRUCTIONS.format(
            faithfulness_floor=faithfulness_floor)
    entry = {
        "source_path": source_path,
        "source_sha256": sha,
        "archetype": archetype,
        "suggested_domain": suggested_domain,
        "target_inbox_path": os.path.join(inbox_dir, target_name),
        "instructions": instructions,
    }
    with open(os.path.join(queue_dir, filename), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, indent=2))
    return entry
