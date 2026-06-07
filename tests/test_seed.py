import yaml

from context_engine.core import seed


def _frontmatter(text):
    assert text.startswith("---\n")
    end = text.find("\n---\n", 4)
    return yaml.safe_load(text[4:end])


def test_build_artifact_adds_frontmatter_and_source():
    out = seed.build_artifact(
        body="# Title\n\n## S\nbody\n", sha256="ABC", title="Title",
        src_path="/x/src.md", artifact_type="reference-note", artifact_id="KB-title")
    fm = _frontmatter(out)
    assert fm["id"] == "KB-title"
    assert fm["type"] == "reference-note"
    assert fm["status"] == "seeded"
    assert fm["sources"][0]["sha256"] == "ABC"
    assert fm["sources"][0]["path"] == "/x/src.md"
    assert "## S" in out


def test_build_artifact_merges_existing_frontmatter():
    body = "---\nid: EXISTING\ncustom: keepme\n---\n\n# T\n\nbody\n"
    out = seed.build_artifact(
        body=body, sha256="Z", title="T", src_path="/x", artifact_type="doctrine",
        artifact_id="KB-fallback")
    fm = _frontmatter(out)
    assert fm["id"] == "EXISTING"        # existing id preserved
    assert fm["custom"] == "keepme"      # other keys preserved
    assert fm["type"] == "doctrine"      # type set
    assert fm["sources"][0]["sha256"] == "Z"


def test_run_seeds_mapping(tmp_path):
    src = tmp_path / "src.md"
    src.write_text("# Doc\n\n## S\ncontent\n", encoding="utf-8")
    dst_dir = tmp_path / "_hot" / "reference"
    mp = str(tmp_path / "m.jsonl")
    plan = seed.run(mappings=[(str(src), str(dst_dir), "reference-note")],
                    manifest_path=mp, apply=True)
    assert len(plan) == 1
    assert (dst_dir / "src.md").exists()
