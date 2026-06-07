from context_engine.core import normalize


def test_apply_id_convention_adds_prefix_and_maps_status():
    fm = normalize.apply_id_convention({"status": "active"}, "my-slug")
    assert fm["id"] == "KB-my-slug"
    assert fm["status"] == "reviewed"   # active -> reviewed
    assert fm["distill"] == 3           # default


def test_apply_id_convention_custom_prefix_keeps_existing_prefixed_id():
    fm = normalize.apply_id_convention({"id": "ACME-keep"}, "slug", id_prefix="ACME-")
    assert fm["id"] == "ACME-keep"


def test_apply_id_convention_unknown_status_defaults():
    fm = normalize.apply_id_convention({"status": "weird"}, "s")
    assert fm["status"] == "seeded"


def test_repair_encoding_fixes_mojibake():
    bad = "em\xe2\x80\x94dash"
    assert normalize.repair_encoding(bad) == "em—dash"
    # idempotent
    assert normalize.repair_encoding("em—dash") == "em—dash"


def test_normalize_file_reemits_frontmatter():
    text = "---\nstatus: active\n---\n\n# Title\n\nbody\n"
    out = normalize.normalize_file(text, "title", None, None)
    assert out.startswith("---\n")
    assert "id: KB-title" in out
    assert "status: reviewed" in out
    assert "# Title" in out


def test_normalize_file_no_frontmatter_passthrough():
    text = "# Just a title\n\nno frontmatter\n"
    assert normalize.normalize_file(text, "x", None, None) == text


def test_run_changes_files_and_logs(tmp_path):
    hot = tmp_path / "_hot"
    hot.mkdir()
    (hot / "a.md").write_text("---\nstatus: active\n---\n\n# A\n\nbody\n",
                              encoding="utf-8")
    mp = str(tmp_path / "m.jsonl")
    plan = normalize.run(str(hot), None, mp, apply=True)
    assert any(p["changed"] for p in plan)
    content = (hot / "a.md").read_text(encoding="utf-8")
    assert "status: reviewed" in content
