from context_engine.core import dedup
from context_engine.utils import hashing


def test_live_tree_dupes_prefers_base_name(tmp_path):
    org = tmp_path / "org"
    live = org / "live"
    live.mkdir(parents=True)
    (live / "a.md").write_text("same", encoding="utf-8")
    (live / "a (1).md").write_text("same", encoding="utf-8")
    index = hashing.scan(str(org))
    dupes = dedup.live_tree_dupes(index, [str(live)], str(org / "_held"))
    assert len(dupes) == 1
    assert dupes[0]["canonical"].endswith("a.md")
    assert any("a (1).md" in r for r in dupes[0]["redundant"])


def test_held_dupes(tmp_path):
    held = tmp_path / "_held"
    held.mkdir()
    (held / "x.md").write_text("dup", encoding="utf-8")
    (held / "y.md").write_text("dup", encoding="utf-8")
    index = hashing.scan(str(tmp_path))
    dupes = dedup.held_dupes(index, str(held))
    assert len(dupes) == 1
    assert len(dupes[0]["redundant"]) == 1


def test_classify_version_pairs_accidental_vs_lineage(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    (live / "same.md").write_text("v", encoding="utf-8")
    (live / "same (1).md").write_text("v", encoding="utf-8")       # accidental
    (live / "diff.md").write_text("A", encoding="utf-8")
    (live / "diff (1).md").write_text("B", encoding="utf-8")       # lineage
    pairs = dedup.classify_version_pairs([str(live)])
    kinds = {p["variant"].split("\\")[-1].split("/")[-1]: p["kind"] for p in pairs}
    assert kinds["same (1).md"] == "accidental"
    assert kinds["diff (1).md"] == "lineage"
