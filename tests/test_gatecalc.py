import json
import os

from context_engine.core import gatecalc, provenance
from context_engine.utils import hashing


def _empty_index(tmp_path):
    manifests_dir = tmp_path / "_prov"
    manifests_dir.mkdir(exist_ok=True)
    db = str(tmp_path / "INDEX.sqlite")
    provenance.build(str(manifests_dir), db)
    return db


def _artifact(tmp_path, source_path, sha, body):
    art = tmp_path / "_inbox" / "artifact.md"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(
        f"---\nid: KB-x\ntype: reference-note\nsources:\n"
        f"  - sha256: {sha}\n    path: {source_path}\n---\n\n{body}\n",
        encoding="utf-8")
    return str(art)


def test_compute_near_lossless_coverage(tmp_path):
    db = _empty_index(tmp_path)
    source = tmp_path / "live" / "src.md"
    source.parent.mkdir()
    source.write_text("Budget $500 on 12/31/2024 for PROJECTX.", encoding="utf-8")
    sha = hashing.sha256_file(str(source))
    # Artifact reproduces the source content -> full coverage. Inline path used
    # for source resolution (index is empty).
    art = _artifact(tmp_path, str(source), sha,
                    "# Note\n\n## S\nBudget $500 on 12/31/2024 for PROJECTX.")
    report = gatecalc.compute(art, "REFERENCE_NOTE", db)
    assert report["archetype"] == "REFERENCE_NOTE"
    assert report["coverage"] == 1.0


def test_compute_aggressive_faithfulness(tmp_path):
    db = _empty_index(tmp_path)
    source = tmp_path / "live" / "src.md"
    source.parent.mkdir()
    source.write_text("We spent $500.", encoding="utf-8")
    sha = hashing.sha256_file(str(source))
    art = _artifact(tmp_path, str(source), sha, "# c\n\n## s\nWe spent $500.")
    report = gatecalc.compute(art, "EXPLORATORY_CHAT", db)
    assert "faithfulness" in report
    assert report["archetype"] == "EXPLORATORY_CHAT"


def test_compute_unresolvable_source_returns_none(tmp_path):
    db = _empty_index(tmp_path)
    art = _artifact(tmp_path, str(tmp_path / "missing.md"), "DEAD", "# x\n\n## s\nbody")
    assert gatecalc.compute(art, "REFERENCE_NOTE", db) is None


def test_write_gate_is_idempotent(tmp_path):
    db = _empty_index(tmp_path)
    source = tmp_path / "live" / "src.md"
    source.parent.mkdir()
    source.write_text("content with PROJECTX", encoding="utf-8")
    sha = hashing.sha256_file(str(source))
    art = _artifact(tmp_path, str(source), sha, "# n\n\n## s\ncontent with PROJECTX")
    first = gatecalc.write_gate(art, "REFERENCE_NOTE", db)
    assert first is not None
    assert os.path.exists(art + ".gate.json")
    # Second call: sidecar exists -> None
    assert gatecalc.write_gate(art, "REFERENCE_NOTE", db) is None
    with open(art + ".gate.json", encoding="utf-8") as fh:
        assert json.load(fh)["archetype"] == "REFERENCE_NOTE"
