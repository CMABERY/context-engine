from context_engine.core import provenance
from context_engine.utils import hashing, manifests


def test_tier_for_rules():
    rules = [("/corpus/_hot/", "hot"), ("/corpus/_held/", "cold")]
    assert provenance.tier_for("C:\\corpus\\_hot\\a.md", rules) == "hot"
    assert provenance.tier_for("/mnt/c/corpus/_held/b.md", rules) == "cold"
    assert provenance.tier_for("/mnt/c/corpus/live/c.md", rules) == "live"
    assert provenance.tier_for("anything", None) == "live"


def test_build_and_resolve(tmp_path):
    # A real file the manifest will point at (so current=1).
    src = tmp_path / "live" / "a.md"
    src.parent.mkdir()
    src.write_text("content", encoding="utf-8")
    sha = hashing.sha256_file(str(src))

    manifests_dir = tmp_path / "_prov"
    mp = str(manifests_dir / "m.jsonl")
    manifests.append(mp, op="seed", src_abs=str(src), dst_abs=str(src),
                     sha256=sha, size_bytes=src.stat().st_size, reason="r",
                     stage="s")

    db = str(tmp_path / "INDEX.sqlite")
    provenance.build(str(manifests_dir), db, [(str(tmp_path / "live"), "live")])

    rec = provenance.resolve(db, sha)
    assert rec["sha256"] == sha.upper()
    assert rec["current"] is True
    assert rec["tier"] == "live"
    assert any("a.md" in p for p in rec["paths"])

    # case-insensitive sha lookup
    assert provenance.resolve(db, sha.lower())["current"] is True


def test_resolve_unknown_sha(tmp_path):
    manifests_dir = tmp_path / "_prov"
    manifests_dir.mkdir()
    db = str(tmp_path / "INDEX.sqlite")
    provenance.build(str(manifests_dir), db)
    rec = provenance.resolve(db, "DEADBEEF")
    assert rec["paths"] == []
    assert rec["current"] is False


def test_dangling_report(tmp_path):
    present = tmp_path / "here.md"
    present.write_text("x", encoding="utf-8")
    manifests_dir = tmp_path / "_prov"
    manifests_dir.mkdir()
    db = str(tmp_path / "INDEX.sqlite")
    provenance.build(str(manifests_dir), db)
    report = provenance.dangling_report(db, [str(present), str(tmp_path / "gone.md")])
    by_path = {r["path"]: r for r in report}
    assert by_path[str(present)]["dangling"] is False
    assert by_path[str(tmp_path / "gone.md")]["dangling"] is True


def test_resolve_prefers_current_record(tmp_path):
    # Two manifest records for the SAME sha: one dst is an existing file (current),
    # one dst is a missing path. Names are chosen so plain alphabetical order would
    # pick the missing one -- this pins the 'current DESC' part of the ORDER BY.
    existing = tmp_path / "live" / "z_current.md"
    existing.parent.mkdir()
    existing.write_text("x", encoding="utf-8")
    missing = tmp_path / "live" / "a_missing.md"  # never created on disk

    manifests_dir = tmp_path / "_prov"
    mp = str(manifests_dir / "m.jsonl")
    sha = "ABCDEF0123456789"
    manifests.append(mp, op="move", src_abs=None, dst_abs=str(existing),
                     sha256=sha, size_bytes=1, reason="r", stage="s")
    manifests.append(mp, op="move", src_abs=None, dst_abs=str(missing),
                     sha256=sha, size_bytes=1, reason="r", stage="s")

    db = str(tmp_path / "INDEX.sqlite")
    provenance.build(str(manifests_dir), db, [(str(tmp_path / "live"), "live")])
    rec = provenance.resolve(db, sha)
    # current record wins despite "a_missing" sorting before "z_current"
    assert rec["current"] is True
    assert rec["path"].endswith("z_current.md")
    assert rec["paths"][0].endswith("z_current.md")


def test_dangling_report_recoverable_by_name(tmp_path):
    # A current INDEX record shares the basename of a now-missing artifact path:
    # the file moved/was relocated, so it is recoverable, not dangling.
    present = tmp_path / "hot" / "doc.md"
    present.parent.mkdir()
    present.write_text("x", encoding="utf-8")
    manifests_dir = tmp_path / "_prov"
    mp = str(manifests_dir / "m.jsonl")
    manifests.append(mp, op="promote", src_abs=None, dst_abs=str(present),
                     sha256="AB", size_bytes=1, reason="r", stage="s")
    db = str(tmp_path / "INDEX.sqlite")
    provenance.build(str(manifests_dir), db)

    missing_other = str(tmp_path / "elsewhere" / "doc.md")  # shares basename
    r = provenance.dangling_report(db, [missing_other])[0]
    assert r["exists"] is False
    assert r["recoverable_by_name"] is True
    assert r["dangling"] is False
