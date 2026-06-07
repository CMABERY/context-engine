"""Seed the hot surface from existing material — the near-lossless builder.

``build_artifact`` wraps a body in the engine's frontmatter convention
(``id``/``type``/``status`` + a sha256-keyed ``sources[]`` link-back). It is used
by the cadence pipeline's near-lossless route and by any operator-driven seeding.

Unlike promotion, seeding applies **no** no-loss gate — it is for content already
known to be near-verbatim. There are NO built-in source mappings here: the
reference implementation's defaults pointed at a specific private corpus, so
callers must pass their own ``mappings`` explicitly.
"""
from __future__ import annotations

import glob
import os
import tempfile

import yaml

from ..utils import manifests as _manifests
from ..utils.hashing import sha256_file
from . import chunk_lint

DEFAULT_STATUS = "seeded"

# Generic basenames whose identity lives in the PARENT dir — disambiguated by
# prefixing the parent dir name so they don't collide in one domain folder.
_GENERIC_BASENAMES = {"CANONICAL_ARTIFACT.md", "README.md", "index.md", "summary.md"}


def _artifact_basename(src: str) -> str:
    base = os.path.basename(src)
    if base in _GENERIC_BASENAMES:
        return f"{os.path.basename(os.path.dirname(src))}__{base}"
    return base


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            try:
                data = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                # Malformed source frontmatter: keep whole file as body
                # (preserve-all) and prepend our valid block.
                return {}, text
            body = text[end + len("\n---\n"):]
            if isinstance(data, dict):
                return data, body
    return {}, text


def build_artifact(*, body: str, sha256: str, title: str, src_path: str,
                   artifact_type: str, artifact_id: str,
                   default_status: str = DEFAULT_STATUS) -> str:
    """Build a hot artifact: merge/add frontmatter + a sha256-keyed source link."""
    existing, real_body = _split_frontmatter(body)
    fm = dict(existing)
    fm.setdefault("id", artifact_id)
    fm["type"] = artifact_type
    fm.setdefault("status", default_status)
    fm["sources"] = [{"sha256": sha256, "title": title, "path": src_path}]
    fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{fm_text}\n---\n\n{real_body.lstrip()}"


def lint_body(text: str, *, max_est_tokens: int = chunk_lint.DEFAULT_MAX_EST_TOKENS,
              max_chars: int = chunk_lint.DEFAULT_MAX_CHARS) -> list[dict]:
    """Chunk-lint artifact text by writing it to a temp file."""
    fd, path = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return chunk_lint.lint(path, max_est_tokens=max_est_tokens, max_chars=max_chars)
    finally:
        os.unlink(path)


def _expand(mappings: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for src, dst_dir, atype in mappings:
        matches = glob.glob(src, recursive=True) if any(c in src for c in "*?[") \
            else [src]
        for m in sorted(matches):
            out.append((m, dst_dir, atype))
    return out


def run(*, mappings: list[tuple[str, str, str]], manifest_path: str, apply: bool,
        id_prefix: str = "KB-", default_status: str = DEFAULT_STATUS,
        path_style: str = "native") -> list[dict]:
    """Seed each ``(src_glob, dst_dir, artifact_type)`` mapping into the hot surface.

    Dry-run (default) returns the plan and writes nothing. There are no built-in
    mappings — the caller supplies them, keeping all paths out of the codebase.
    """
    plan: list[dict] = []
    for src, dst_dir, atype in _expand(mappings):
        if not os.path.isfile(src):
            continue
        sha = sha256_file(src)
        size = os.path.getsize(src)
        with open(src, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        name = _artifact_basename(src)
        title = os.path.splitext(name)[0]
        art_id = id_prefix + title.lower().replace(" ", "-")[:60]
        artifact = build_artifact(
            body=raw, sha256=sha, title=title, src_path=src,
            artifact_type=atype, artifact_id=art_id, default_status=default_status)
        flags = lint_body(artifact)
        dst = os.path.join(dst_dir, name)
        plan.append({"src": src, "dst": dst, "sha256": sha,
                     "size_bytes": size, "lint_flags": flags})
        if apply:
            os.makedirs(dst_dir, exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(artifact)
            _manifests.append(
                manifest_path, op="copy", src_abs=src, dst_abs=dst,
                sha256=sha, size_bytes=size, reason="seed-hot",
                stage="seed", reversible=True, path_style=path_style)
    return plan
