"""Backend-agnostic reindex executor.

The engine refreshes its recall index incrementally after a cadence run. *Which*
commands accomplish that is the backend's concern (see
:mod:`context_engine.adapters.qmd` for the qmd command list); this module only
sequences them through an injectable ``runner`` so unit tests need no live
backend.

A dry-run (``apply=False``) returns the planned commands without invoking the
runner — the safe default surfaced by ``context-engine cadence --dry-run``.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence


def run(commands: Sequence[Sequence[str]], *,
        runner: Callable[[list[str]], str],
        apply: bool = True,
        labels: Optional[Sequence[str]] = None) -> dict:
    """Execute ``commands`` in order via ``runner``.

    Parameters
    ----------
    commands : sequence of argv lists, e.g. ``[["update"], ["embed", "-c", "hot"]]``.
    runner   : ``argv -> output`` callable. Injected; never imported here.
    apply    : when ``False``, return ``{"planned": [...]}`` and call nothing.
    labels   : optional per-command keys for the result dict (default ``stepN``).

    Returns ``{"planned": [...]}`` on dry-run, else ``{label: output, ...}``.
    """
    planned = [list(c) for c in commands]
    if not apply:
        return {"planned": planned}
    results: dict[str, str] = {}
    for i, cmd in enumerate(planned):
        label = labels[i] if labels and i < len(labels) else f"step{i}"
        results[label] = runner(cmd)
    return results
