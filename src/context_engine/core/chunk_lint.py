"""Chunk-shape lint for hot artifacts.

The hot surface is consumed one section at a time (each H2/H3 section is the
embed/rerank unit), so oversized or heading-less sections degrade recall
granularity. A "section" runs from one H2/H3 heading to the next; content before
the first H2/H3 is a section lacking a leading heading.

Flags (one dict per violation)::

    missing_leading_heading : section has no leading H2/H3
    over_est_tokens         : section est-tokens (chars/4) over the limit
    over_chars              : section length over the char limit

Limits are configurable (``max_est_tokens`` / ``max_chars``) so different memory
surfaces can tune granularity without forking the linter.
"""
from __future__ import annotations

DEFAULT_MAX_EST_TOKENS = 850
DEFAULT_MAX_CHARS = 3600


def _est_tokens(text: str) -> int:
    return len(text) // 4


def _strip_doc_header(body: str) -> str:
    """Strip a leading YAML frontmatter block, leading H1 title lines, and blank
    lines (legitimate document-header structure), returning the remainder. Used
    so a header (frontmatter + '# Title') isn't mistaken for a malformed,
    heading-less content section.
    """
    text = body
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + len("\n---\n"):]
    out: list[str] = []
    skipping = True
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if skipping and (s == "" or s.startswith("# ")):
            continue
        skipping = False
        out.append(line)
    return "".join(out)


def _split_sections(text: str) -> list[tuple[str | None, str]]:
    lines = text.splitlines(keepends=True)
    sections: list[tuple[str | None, str]] = []
    cur_heading: str | None = None
    cur_lines: list[str] = []

    def _is_h23(line: str) -> bool:
        s = line.lstrip()
        return s.startswith("## ") or s.startswith("### ")

    for line in lines:
        if _is_h23(line):
            if cur_heading is not None or "".join(cur_lines).strip():
                sections.append((cur_heading, "".join(cur_lines)))
            cur_heading = line
            cur_lines = [line]
        else:
            cur_lines.append(line)
    if cur_heading is not None or "".join(cur_lines).strip():
        sections.append((cur_heading, "".join(cur_lines)))
    return sections


def lint_text(
    text: str,
    *,
    max_est_tokens: int = DEFAULT_MAX_EST_TOKENS,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict]:
    """Lint markdown ``text`` directly. Returns a list of flag dicts (empty = OK)."""
    flags: list[dict] = []
    for idx, (heading, body) in enumerate(_split_sections(text)):
        label = heading.strip() if heading else f"<section #{idx} (no heading)>"

        if heading is None and _strip_doc_header(body).strip():
            # Only flag a heading-less leading block if real content remains
            # after removing legitimate document-header structure (frontmatter
            # + H1 title). A pure header is not a malformed content section.
            flags.append({
                "rule": "missing_leading_heading",
                "section": label,
                "detail": "section has no leading H2/H3 heading",
            })

        n_chars = len(body)
        n_tokens = _est_tokens(body)
        if n_tokens > max_est_tokens:
            flags.append({
                "rule": "over_est_tokens",
                "section": label,
                "detail": f"{n_tokens} est-tokens (chars/4) > {max_est_tokens}",
            })
        if n_chars > max_chars:
            flags.append({
                "rule": "over_chars",
                "section": label,
                "detail": f"{n_chars} chars > {max_chars}",
            })
    return flags


def lint(
    path: str,
    *,
    max_est_tokens: int = DEFAULT_MAX_EST_TOKENS,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[dict]:
    """Lint the markdown file at ``path``."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return lint_text(text, max_est_tokens=max_est_tokens, max_chars=max_chars)
