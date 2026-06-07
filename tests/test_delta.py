"""Delta seen-set behaviour: a file is new iff its sha is in NEITHER the index
NOR any hot artifact's sources[].sha256 link-back."""
from context_engine.core import delta
from context_engine.utils import hashing


def test_new_file_detected_when_unseen(tmp_path):
    live = tmp_path / "live"
    hot = tmp_path / "_hot"
    live.mkdir()
    hot.mkdir()
    (live / "a.md").write_text("hello", encoding="utf-8")
    db = str(tmp_path / "nope.sqlite")  # absent index -> empty seen-set
    new = delta.new_files([str(live)], db, str(hot))
    assert len(new) == 1
    assert new[0]["path"].endswith("a.md")


def test_hot_source_linkback_excludes_file(tmp_path):
    live = tmp_path / "live"
    hot = tmp_path / "_hot"
    live.mkdir()
    hot.mkdir()
    src = live / "a.md"
    src.write_text("hello", encoding="utf-8")
    sha = hashing.sha256_file(str(src))

    # A hot artifact citing the source's sha256 marks it as already curated.
    (hot / "artifact.md").write_text(
        f"---\nid: KB-x\nsources:\n  - sha256: {sha}\n---\n\n# T\n\n## S\nbody\n",
        encoding="utf-8")

    db = str(tmp_path / "nope.sqlite")
    new = delta.new_files([str(live)], db, str(hot))
    assert new == []


def test_hot_source_shas_skips_inbox(tmp_path):
    hot = tmp_path / "_hot"
    inbox = hot / "_inbox"
    inbox.mkdir(parents=True)
    (inbox / "pending.md").write_text(
        "---\nsources:\n  - sha256: AAA\n---\n\n# t\n", encoding="utf-8")
    assert delta.hot_source_shas(str(hot)) == set()


def test_batch_dedup_same_content(tmp_path):
    live = tmp_path / "live"
    hot = tmp_path / "_hot"
    live.mkdir()
    hot.mkdir()
    (live / "a.md").write_text("identical", encoding="utf-8")
    (live / "b.md").write_text("identical", encoding="utf-8")
    db = str(tmp_path / "nope.sqlite")
    new = delta.new_files([str(live)], db, str(hot))
    # Same sha -> only the first encountered is returned.
    assert len(new) == 1
