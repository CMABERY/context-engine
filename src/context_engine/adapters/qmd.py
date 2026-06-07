"""qmd recall + reindex adapter.

Bridges the engine to the ``qmd`` CLI:

* **hot** recall  — ``qmd query --json`` (typed vector + rerank),
* **cold** recall — ``qmd search --json --index <cold>`` (BM25/FTS),
* **reindex**     — ``update`` -> ``embed -c <hot>`` -> ``status``.

Both tiers run on every recall: hot is primary, cold is ALWAYS surfaced as a
secondary section so not-yet-embedded material stays reachable. The reranker
floor only *flags* weak hot hits; it never gates cold.

Everything host-specific (binary path, working dir, WSL wrapping, collection
names) comes from :class:`~context_engine.models.QmdConfig`. The ``runner`` seam
(``argv -> combined stdout+stderr``) is injectable, so unit tests never require
qmd to be installed.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from typing import Callable, Optional

from ..models import QmdConfig

Runner = Callable[[list[str]], str]

# Text-mode regexes (mock fixtures and legacy text output).
_SCORE_RE = re.compile(r"score:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_PATH_RE = re.compile(r"(?:result:|^)\s*(\S+\.md)")
_MISS_RE = re.compile(r"no results", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _try_parse_json(text: str) -> list[dict] | None:
    """Parse qmd ``--json`` output, tolerating leading/trailing non-JSON noise.

    qmd writes JSON to stdout and progress to stderr; combined, trailing noise
    may follow the closing ``]``. Slice from the first ``[`` to the last ``]``.
    """
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(text[start: end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        path = item.get("file", "")
        if score is None:
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        results.append({"path": path, "score": score})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def parse_results(text: str) -> list[dict]:
    """Parse qmd output into ``[{path, score}]`` sorted descending.

    Handles JSON (``--json``) and text (mock/legacy) shapes; ``[]`` on miss/empty.
    """
    if not text.strip() or _MISS_RE.search(text):
        return []
    json_results = _try_parse_json(text)
    if json_results is not None:
        return json_results
    results: list[dict] = []
    for line in text.splitlines():
        sm = _SCORE_RE.search(line)
        pm = _PATH_RE.search(line)
        if sm and pm:
            results.append({"path": pm.group(1), "score": float(sm.group(1))})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def should_fallback(hot_output: str, rerank_floor: float = 0.30) -> bool:
    """True if hot results are absent or the top score is below ``rerank_floor``.

    A pure flagging helper (metadata only); it does NOT gate cold recall.
    """
    results = parse_results(hot_output)
    if not results:
        return True
    return results[0]["score"] < rerank_floor


def _normalize_path(path: str) -> str:
    """Strip a ``?index=...`` query suffix so cold paths compare to hot paths."""
    if "?" in path:
        path = path[: path.index("?")]
    return path


def _dedup_cold(hot_results: list[dict], cold_results: list[dict]) -> list[dict]:
    """Return cold results with any path matching a hot path removed."""
    hot_paths = {_normalize_path(r["path"]) for r in hot_results}
    return [r for r in cold_results if _normalize_path(r["path"]) not in hot_paths]


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

def hot_command(query: str, qmd: QmdConfig) -> list[str]:
    """argv for a hot (vector/rerank) recall.

    The query is a RAW argv element — no surrounding quotes. Quoting is the
    runner's job: ``subprocess`` handles argv directly, and the shell-wrapped
    path shell-quotes via :func:`build_shell_command`.
    """
    return [qmd.hot_verb, qmd.json_flag, query]


def cold_command(query: str, qmd: QmdConfig) -> list[str]:
    """argv for a cold (BM25/FTS) recall.

    Uses ``search`` (NOT ``query``) on the cold index — ``query --index cold``
    would trigger a large reranker-model download.
    """
    return [qmd.cold_verb, qmd.json_flag, "--index", qmd.cold_index, query]


def reindex_commands(qmd: QmdConfig) -> tuple[list[list[str]], list[str]]:
    """Return ``(commands, labels)`` for an incremental reindex.

    ``update`` re-scans markdown, ``embed -c <hot>`` refreshes the hot vector
    collection (the only embedded one), ``status`` reports health.
    """
    commands = [["update"], ["embed", "-c", qmd.hot_collection], ["status"]]
    labels = ["update", "embed", "status"]
    return commands, labels


# ---------------------------------------------------------------------------
# Default runner (shell out to qmd)
# ---------------------------------------------------------------------------

def build_shell_command(qmd: QmdConfig, args: list[str]) -> str:
    """Build a POSIX-shell command string for the ``bash -lc`` runner paths.

    Every component — the binary, the cwd, and each arg (including the raw query)
    — is shell-quoted, so spaces and shell metacharacters are safe. The shell
    that runs this is bash (``wsl bash -lc`` / ``bash -lc``), so POSIX quoting
    via :func:`shlex.quote` is correct.
    """
    quoted = " ".join(shlex.quote(a) for a in [qmd.bin, *args])
    return f"cd {shlex.quote(qmd.cwd)} && {quoted}"


def make_runner(qmd: QmdConfig) -> Runner:
    """Build the default subprocess runner from config.

    Honors ``wsl_wrap`` (Windows host -> WSL backend) and ``login_shell``
    (``bash -lc`` for ``~`` expansion / login PATH). In direct mode the raw argv
    is passed to ``subprocess`` (which quotes per-OS); in shell mode the command
    is shell-quoted via :func:`build_shell_command`. Returns combined
    stdout+stderr so JSON-on-stdout and progress-on-stderr are both captured.
    """
    def runner(args: list[str]) -> str:
        if qmd.wsl_wrap or qmd.login_shell:
            cmd = build_shell_command(qmd, args)
            argv = (["wsl", "bash", "-lc", cmd] if qmd.wsl_wrap
                    else ["bash", "-lc", cmd])
            proc = subprocess.run(argv, capture_output=True, text=True)
        else:
            argv = [qmd.bin, *args]
            proc = subprocess.run(argv, capture_output=True, text=True, cwd=qmd.cwd)
        return (proc.stdout or "") + (proc.stderr or "")
    return runner


# ---------------------------------------------------------------------------
# Public recall / reindex / probe
# ---------------------------------------------------------------------------

def recall(query: str, *, qmd: Optional[QmdConfig] = None,
           runner: Optional[Runner] = None) -> dict:
    """Run hot query AND cold search; return both as labeled sections.

    Return shape::

        {"hot": [{path, score}...], "cold": [...], "tiers": [...], "weak_hot": bool}

    Cold is deduped against hot (path-normalized) then capped at ``cold_cap``.
    """
    qmd = qmd or QmdConfig()
    runner = runner or make_runner(qmd)

    hot_raw = runner(hot_command(query, qmd))
    cold_raw = runner(cold_command(query, qmd))

    hot_results = parse_results(hot_raw)
    cold_results = parse_results(cold_raw)
    unique_cold = _dedup_cold(hot_results, cold_results)[: qmd.cold_cap]

    tiers: list[str] = []
    if hot_results:
        tiers.append("hot")
    if unique_cold:
        tiers.append("cold")

    return {
        "hot": hot_results,
        "cold": unique_cold,
        "tiers": tiers,
        "weak_hot": should_fallback(hot_raw, qmd.rerank_floor),
    }


def reindex(*, qmd: Optional[QmdConfig] = None, runner: Optional[Runner] = None,
            apply: bool = True) -> dict:
    """Run the incremental reindex via the generic executor.

    Dry-run (``apply=False``) returns the planned commands without calling qmd.
    """
    from ..core import reindex as _reindex  # local import avoids core<->adapter cycle

    qmd = qmd or QmdConfig()
    commands, labels = reindex_commands(qmd)
    run = runner or make_runner(qmd)
    return _reindex.run(commands, runner=run, apply=apply, labels=labels)


def probe(*, qmd: Optional[QmdConfig] = None,
          runner: Optional[Runner] = None) -> dict:
    """Best-effort availability check for ``doctor``.

    Returns ``{"available": bool, "detail": str}``. Never raises — a missing
    backend, missing WSL, or non-zero exit all resolve to ``available=False``.
    """
    qmd = qmd or QmdConfig()
    run = runner or make_runner(qmd)
    try:
        out = run(["--version"])
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "detail": f"{type(exc).__name__}: {exc}"}
    out = (out or "").strip()
    if not out:
        return {"available": False, "detail": "no output from `qmd --version`"}
    low = out.lower()
    if "not found" in low or "no such" in low or "command not found" in low:
        return {"available": False, "detail": out.splitlines()[0][:200]}
    return {"available": True, "detail": out.splitlines()[0][:200]}
