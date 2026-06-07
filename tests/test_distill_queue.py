import os

from context_engine.core import distill_queue


def test_slug_strips_export_prefix():
    assert distill_queue.slug_for("claude-Foo Bar.md") == "foo-bar"
    assert distill_queue.slug_for("chatgpt-Baz_Qux.md") == "baz-qux"
    assert distill_queue.slug_for("Plain Title.md") == "plain-title"


def test_enqueue_creates_descriptor(tmp_path):
    queue = str(tmp_path / "_queue")
    inbox = str(tmp_path / "_inbox")
    entry = distill_queue.enqueue(
        queue, source_path="claude-Foo Bar.md",
        source_sha="A" * 64, suggested_domain="decisions", inbox_dir=inbox)
    assert entry is not None
    assert os.path.exists(os.path.join(queue, "foo-bar.distill.json"))
    assert entry["target_inbox_path"].endswith("foo-bar.md")
    assert entry["source_sha256"] == "A" * 64


def test_enqueue_idempotent_same_sha(tmp_path):
    queue = str(tmp_path / "_queue")
    inbox = str(tmp_path / "_inbox")
    distill_queue.enqueue(queue, source_path="a.md", source_sha="B" * 64,
                          suggested_domain="d", inbox_dir=inbox)
    again = distill_queue.enqueue(queue, source_path="a.md", source_sha="b" * 64,
                                  suggested_domain="d", inbox_dir=inbox)
    assert again is None
    assert len(distill_queue.list_queue(queue)) == 1


def test_enqueue_slug_collision_disambiguates(tmp_path):
    queue = str(tmp_path / "_queue")
    inbox = str(tmp_path / "_inbox")
    # Same slug ("foo-bar") but DIFFERENT sha -> must not overwrite.
    distill_queue.enqueue(queue, source_path="claude-Foo Bar.md",
                          source_sha="1" * 64, suggested_domain="d", inbox_dir=inbox)
    second = distill_queue.enqueue(queue, source_path="Foo Bar.md",
                                   source_sha="2" * 64, suggested_domain="d",
                                   inbox_dir=inbox)
    assert second is not None
    files = sorted(os.listdir(queue))
    assert "foo-bar.distill.json" in files
    # disambiguated by sha prefix
    assert any(f.startswith("foo-bar-") and f.endswith(".distill.json") for f in files)
    assert len(distill_queue.list_queue(queue)) == 2
