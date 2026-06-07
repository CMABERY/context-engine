import hashlib

from context_engine.utils import hashing


def test_sha256_file_is_uppercase_hex(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello world")
    digest = hashing.sha256_file(str(p))
    assert digest == hashlib.sha256(b"hello world").hexdigest().upper()
    assert digest == digest.upper()
    assert len(digest) == 64


def test_sha256_text_and_bytes_agree():
    assert hashing.sha256_text("abc") == hashing.sha256_bytes(b"abc")


def test_sha256_bytes_matches_external_vector():
    # Pin to an independent hashlib vector so a wrong digest (e.g. MD5) is caught,
    # not just internal self-consistency.
    assert hashing.sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest().upper()


def test_sha256_text_locks_utf8_contract():
    # Non-ASCII input pins the UTF-8 encoding contract of sha256_text.
    assert hashing.sha256_text("café") == \
        hashlib.sha256("café".encode("utf-8")).hexdigest().upper()


def test_scan_groups_duplicates(tmp_path):
    (tmp_path / "a.md").write_text("same", encoding="utf-8")
    (tmp_path / "b.md").write_text("same", encoding="utf-8")
    (tmp_path / "c.md").write_text("different", encoding="utf-8")
    buckets = hashing.scan(str(tmp_path))
    dup_groups = [paths for paths in buckets.values() if len(paths) > 1]
    assert len(dup_groups) == 1
    assert len(dup_groups[0]) == 2


def test_scan_respects_exclude_globs(tmp_path):
    (tmp_path / "keep.md").write_text("x", encoding="utf-8")
    skip_dir = tmp_path / ".venv"
    skip_dir.mkdir()
    (skip_dir / "lib.py").write_text("y", encoding="utf-8")
    buckets = hashing.scan(str(tmp_path), ["**/.venv/**"])
    all_paths = [p for ps in buckets.values() for p in ps]
    assert any("keep.md" in p for p in all_paths)
    assert not any(".venv" in p for p in all_paths)
