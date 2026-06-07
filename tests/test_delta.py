"""Delta seen-set behaviour: a file is new iff its sha is in NEITHER the index
NOR any hot artifact's sources[].sha256 link-back."""
from context_engine.core import delta, provenance
from context_engine.utils import hashing, manifests


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


def test_delete_op_does_not_mark_content_seen(tmp_path):
    # A redundant-copy `delete` must NOT suppress curation of the surviving
    # canonical (same content hash). Only curation/preservation ops mark seen.
    live = tmp_path / "live"
    hot = tmp_path / "_hot"
    live.mkdir()
    hot.mkdir()
    canonical = live / "doc.md"
    canonical.write_text("shared content", encoding="utf-8")
    sha = hashing.sha256_file(str(canonical))

    manifests_dir = tmp_path / "_prov"
    mp = str(manifests_dir / "m.jsonl")
    # simulate layer0 having deleted a byte-identical copy (same sha)
    manifests.append(mp, op="delete", src_abs=str(live / "doc (1).md"),
                     dst_abs=None, sha256=sha, size_bytes=1, reason="dedup",
                     stage="layer0")
    db = str(tmp_path / "INDEX.sqlite")
    provenance.build(str(manifests_dir), db)

    # the delete sha is NOT in the seen-set...
    assert sha.upper() not in delta.index_shas(db)
    # ...so the canonical is still detected as new
    new = delta.new_files([str(live)], db, str(hot))
    assert any(f["path"].endswith("doc.md") for f in new)
