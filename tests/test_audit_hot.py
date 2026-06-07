from context_engine.audit import hot_surface

_GOOD = ("---\nid: KB-good\nstatus: seeded\ntype: reference-note\n"
         "sources:\n  - sha256: AABBCC\n---\n\n# Good Note\n\n## Section\nshort\n")


def test_good_artifact_passes(tmp_path):
    hot = tmp_path / "_hot" / "reference"
    hot.mkdir(parents=True)
    (hot / "good.md").write_text(_GOOD, encoding="utf-8")
    report = hot_surface.audit_hot(str(tmp_path / "_hot"))
    assert report["files"] == 1
    assert report["verdict"] == "PASS"
    assert report["findings"] == []


def test_audit_text_flags_missing_frontmatter():
    findings = hot_surface.audit_text("# No frontmatter\n\n## S\nbody\n")
    rules = {f["rule"] for f in findings}
    assert "frontmatter_invalid" in rules


def test_audit_text_flags_missing_field():
    text = "---\nid: KB-x\n---\n\n# Title\n\n## S\nbody\n"  # no status, no sources
    findings = hot_surface.audit_text(text)
    assert "missing_field" in {f["rule"] for f in findings}


def test_audit_text_flags_linkback_when_sources_lack_sha():
    # sources present but without a sha256 -> linkback finding (not missing_field)
    text = ("---\nid: KB-x\nstatus: seeded\nsources:\n  - title: t\n---\n\n"
            "# Title\n\n## S\nbody\n")
    rules = {f["rule"] for f in hot_surface.audit_text(text)}
    assert "missing_sha256_linkback" in rules
    assert "missing_field" not in rules  # all required fields are present


def test_audit_text_flags_missing_h1():
    text = ("---\nid: KB-x\nstatus: seeded\nsources:\n  - sha256: AB\n---\n\n"
            "## Section only\nbody\n")
    findings = hot_surface.audit_text(text)
    assert any(f["rule"] == "missing_h1_title" for f in findings)


def test_audit_flags_oversize(tmp_path):
    hot = tmp_path / "_hot"
    hot.mkdir()
    big_body = "## S\n" + ("x" * 200) + "\n"
    (hot / "big.md").write_text(
        f"---\nid: KB-b\nstatus: seeded\ntype: reference-note\n"
        f"sources:\n  - sha256: AB\n---\n\n# B\n\n{big_body}", encoding="utf-8")
    report = hot_surface.audit_hot(str(hot), oversize_bytes=50)
    assert any(f["rule"] == "oversize" for f in report["findings"])
    assert report["verdict"] == "FAIL"


def test_audit_detects_near_duplicates(tmp_path):
    hot = tmp_path / "_hot"
    hot.mkdir()
    common = " ".join(f"w{i}" for i in range(40))
    for name in ("topic.md", "topic (1).md"):
        (hot / name).write_text(
            f"---\nid: KB-x\nstatus: seeded\ntype: reference-note\n"
            f"sources:\n  - sha256: AB\n---\n\n# Topic\n\n## S\n{common}\n",
            encoding="utf-8")
    report = hot_surface.audit_hot(str(hot), near_dup_threshold=0.5)
    assert any(f["rule"] == "near_duplicate" for f in report["findings"])
