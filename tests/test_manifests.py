import json

from context_engine.utils import manifests


def _read_lines(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_append_writes_one_record_with_schema(tmp_path):
    mp = str(tmp_path / "m.jsonl")
    rec = manifests.append(
        mp, op="promote", src_abs=str(tmp_path / "s.md"),
        dst_abs=str(tmp_path / "d.md"), sha256="abc123", size_bytes=10,
        reason="r", stage="test")
    assert set(rec) >= {"op", "src_abs", "dst_abs", "sha256", "size_bytes",
                        "mtime_utc", "ts_utc", "stage", "reversible", "reason"}
    # sha is uppercased
    assert rec["sha256"] == "ABC123"
    lines = _read_lines(mp)
    assert len(lines) == 1
    assert lines[0]["op"] == "promote"


def test_append_is_append_only(tmp_path):
    mp = str(tmp_path / "m.jsonl")
    for i in range(3):
        manifests.append(mp, op="x", src_abs=None, dst_abs=None,
                         sha256="d", size_bytes=i, reason="r", stage="s")
    assert len(_read_lines(mp)) == 3


def test_path_style_posix(tmp_path):
    mp = str(tmp_path / "m.jsonl")
    rec = manifests.append(mp, op="x", src_abs="C:\\corpus\\a.md", dst_abs=None,
                           sha256="d", size_bytes=1, reason="r", stage="s",
                           path_style="posix")
    assert rec["src_abs"] == "/mnt/c/corpus/a.md"


def test_path_style_windows(tmp_path):
    mp = str(tmp_path / "m.jsonl")
    rec = manifests.append(mp, op="x", src_abs="/mnt/c/corpus/a.md", dst_abs=None,
                           sha256="d", size_bytes=1, reason="r", stage="s",
                           path_style="windows")
    assert rec["src_abs"] == "C:\\corpus\\a.md"
