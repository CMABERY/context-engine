"""Shared pytest fixtures — tiny SYNTHETIC files only, never the private corpus."""
from __future__ import annotations

import os

import pytest

from context_engine.models import EngineConfig, QmdConfig


def _write(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


@pytest.fixture
def write_md():
    """Return a ``(path, text) -> path`` writer for building synthetic files."""
    return _write


@pytest.fixture
def synth_corpus(tmp_path):
    """A fully-configured EngineConfig over an empty synthetic corpus tree.

    Returns ``(cfg, root)``. All directories exist; no content is created — tests
    add the tiny files they need.
    """
    org = tmp_path / "_organized"
    live = org / "live"
    hot = org / "_hot"
    inbox = hot / "_inbox"
    queue = inbox / "_queue"
    held = org / "_held"
    prov = org / "_provenance"
    for d in (live, hot, inbox, queue, held, prov):
        d.mkdir(parents=True, exist_ok=True)

    cfg = EngineConfig(
        org_root=str(org),
        live_roots=[str(live)],
        hot_root=str(hot),
        inbox_dir=str(inbox),
        queue_dir=str(queue),
        held_root=str(held),
        superseded_root=str(held / "superseded-originals"),
        near_dup_cold=str(held / "near-dup"),
        manifests_dir=str(prov),
        index_db=str(prov / "INDEX.sqlite"),
        path_style="native",
        qmd=QmdConfig(),
    )
    return cfg, tmp_path
