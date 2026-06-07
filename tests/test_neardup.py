from context_engine.core import neardup


def test_normalize_title_strips_markers():
    assert neardup.normalize_title("claude-Foo Bar (2).md") == "foo bar"
    assert neardup.normalize_title("xModel Spec.md") == "model spec"
    assert neardup.normalize_title("Plain.md") == "plain"


def test_shingles_and_jaccard():
    a = neardup.shingles("the quick brown fox jumps over", k=3)
    b = neardup.shingles("the quick brown fox jumps over", k=3)
    assert a == b
    assert neardup.jaccard(a, b) == 1.0
    assert neardup.jaccard(set(), set()) == 0.0


def test_find_clusters_groups_near_identical(tmp_path):
    common = " ".join(f"word{i}" for i in range(50))
    (tmp_path / "topic.md").write_text(common + " alpha", encoding="utf-8")
    (tmp_path / "topic (1).md").write_text(common + " beta", encoding="utf-8")
    (tmp_path / "unrelated.md").write_text("completely different content here",
                                           encoding="utf-8")
    clusters = neardup.find_clusters(
        [str(tmp_path / "topic.md"), str(tmp_path / "topic (1).md"),
         str(tmp_path / "unrelated.md")], threshold=0.5)
    assert len(clusters) == 1
    assert len(clusters[0]) == 2


def test_pick_canonical_prefers_non_x_then_larger(tmp_path):
    big = tmp_path / "big.md"
    big.write_text("x" * 100, encoding="utf-8")
    small = tmp_path / "small.md"
    small.write_text("x" * 10, encoding="utf-8")
    xfile = tmp_path / "xprefixed.md"
    xfile.write_text("x" * 1000, encoding="utf-8")
    canonical, losers = neardup.pick_canonical([str(big), str(small), str(xfile)])
    assert canonical.endswith("big.md")  # non-x, larger than small
    assert len(losers) == 2


def test_generic_stems_excluded(tmp_path):
    (tmp_path / "README.md").write_text("a a a a a a", encoding="utf-8")
    (tmp_path / "readme.md").write_text("a a a a a a", encoding="utf-8")
    clusters = neardup.find_clusters(
        [str(tmp_path / "README.md"), str(tmp_path / "readme.md")], threshold=0.1)
    assert clusters == []
