import json
import os

import pytest

from context_engine.core import promote
from context_engine.core.promote import PromotionError

_BODY = ("---\nid: KB-test\ntype: reference-note\nstatus: seeded\n"
         "sources:\n  - sha256: AABBCC\n    path: /x/src.md\n---\n\n"
         "# Test Note\n\n## Section\nshort content\n")


def _stage(tmp_path, *, body=_BODY, gate=None):
    inbox = tmp_path / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    art = inbox / "artifact.md"
    art.write_text(body, encoding="utf-8")
    if gate is not None:
        (inbox / "artifact.md.gate.json").write_text(json.dumps(gate),
                                                     encoding="utf-8")
    return str(art)


def test_promote_success_routes_to_domain(tmp_path):
    hot = tmp_path / "_hot"
    hot.mkdir()
    mp = str(tmp_path / "m.jsonl")
    art = _stage(tmp_path, gate={"archetype": "REFERENCE_NOTE",
                                 "coverage": 1.0, "missing": []})
    res = promote.promote(art, str(hot), mp)
    assert res["ok"] is True
    assert res["domain"] == "reference"
    assert os.path.exists(res["dst_abs"])
    assert os.path.exists(mp)  # manifest written
    assert not os.path.exists(art)  # moved


def test_promote_requires_gate(tmp_path):
    hot = tmp_path / "_hot"
    hot.mkdir()
    art = _stage(tmp_path)  # no gate.json
    with pytest.raises(PromotionError):
        promote.promote(art, str(hot), str(tmp_path / "m.jsonl"))


def test_promote_rejects_low_coverage(tmp_path):
    hot = tmp_path / "_hot"
    hot.mkdir()
    art = _stage(tmp_path, gate={"archetype": "REFERENCE_NOTE",
                                 "coverage": 0.5, "missing": ["x"]})
    with pytest.raises(PromotionError):
        promote.promote(art, str(hot), str(tmp_path / "m.jsonl"))


def test_promote_requires_sources_linkback(tmp_path):
    hot = tmp_path / "_hot"
    hot.mkdir()
    body = ("---\nid: KB-x\ntype: reference-note\n---\n\n"
            "# T\n\n## S\nbody\n")  # no sources[]
    art = _stage(tmp_path, body=body,
                 gate={"archetype": "REFERENCE_NOTE", "coverage": 1.0, "missing": []})
    with pytest.raises(PromotionError):
        promote.promote(art, str(hot), str(tmp_path / "m.jsonl"))


def test_promote_refuses_destination_collision(tmp_path):
    hot = tmp_path / "_hot"
    dst_dir = hot / "reference"
    dst_dir.mkdir(parents=True)
    # A different hot artifact already occupies the destination name.
    (dst_dir / "artifact.md").write_text("EXISTING", encoding="utf-8")
    art = _stage(tmp_path, gate={"archetype": "REFERENCE_NOTE",
                                 "coverage": 1.0, "missing": []})
    with pytest.raises(PromotionError):
        promote.promote(art, str(hot), str(tmp_path / "m.jsonl"))
    # existing hot artifact is NOT overwritten, and the inbox artifact stays put
    assert (dst_dir / "artifact.md").read_text(encoding="utf-8") == "EXISTING"
    assert os.path.exists(art)


def test_promote_rejects_chunk_lint_failure(tmp_path):
    hot = tmp_path / "_hot"
    hot.mkdir()
    big = ("---\nid: KB-x\ntype: reference-note\nsources:\n  - sha256: AB\n---\n\n"
           "# T\n\n## Big\n" + ("x" * 4000) + "\n")
    art = _stage(tmp_path, body=big,
                 gate={"archetype": "REFERENCE_NOTE", "coverage": 1.0, "missing": []})
    with pytest.raises(PromotionError):
        promote.promote(art, str(hot), str(tmp_path / "m.jsonl"))
