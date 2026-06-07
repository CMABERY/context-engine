import json

from context_engine.core import layer0


def _build_tree(tmp_path):
    org = tmp_path / "org"
    live = org / "live"
    held = org / "_held"
    live.mkdir(parents=True)
    held.mkdir(parents=True)
    # byte-identical accidental copy -> delete the (1)
    (live / "base.md").write_text("v1", encoding="utf-8")
    (live / "base (1).md").write_text("v1", encoding="utf-8")
    # true revision lineage -> move the (1) cold
    (live / "rev.md").write_text("AAA", encoding="utf-8")
    (live / "rev (1).md").write_text("BBB", encoding="utf-8")
    return org, live, held


def test_layer0_dry_run_plan(tmp_path):
    org, live, held = _build_tree(tmp_path)
    plan = layer0.run(org_root=str(org), live_roots=[str(live)],
                      held_root=str(held),
                      superseded_root=str(held / "superseded"),
                      manifest_path=str(tmp_path / "m.jsonl"), apply=False)
    assert plan["live_delete"] == 1
    assert plan["lineage_move"] == 1
    # nothing happened
    assert (live / "base (1).md").exists()
    assert (live / "rev (1).md").exists()


def test_layer0_apply_mutates_and_logs(tmp_path):
    org, live, held = _build_tree(tmp_path)
    mp = str(tmp_path / "m.jsonl")
    layer0.run(org_root=str(org), live_roots=[str(live)], held_root=str(held),
               superseded_root=str(held / "superseded"), manifest_path=mp,
               apply=True)
    # accidental redundant copy deleted; base kept
    assert not (live / "base (1).md").exists()
    assert (live / "base.md").exists()
    # lineage moved cold, original gone from live
    assert not (live / "rev (1).md").exists()
    assert (held / "superseded" / "live" / "rev (1).md").exists()
    # manifest recorded both ops
    with open(mp, encoding="utf-8") as fh:
        ops = [json.loads(line)["op"] for line in fh if line.strip()]
    assert "delete" in ops
    assert "move" in ops
