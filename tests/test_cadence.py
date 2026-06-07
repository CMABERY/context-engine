"""End-to-end cadence pipeline over a tiny SYNTHETIC corpus (no live backend)."""
import os

from context_engine.core import cadence


def _fake_reindex_runner(argv):
    return "reindex ok: " + " ".join(argv)


def _seed_corpus(cfg):
    live = cfg.live_roots[0]
    # near-lossless reference note (chunk-clean, no chat markers)
    with open(os.path.join(live, "note.md"), "w", encoding="utf-8") as fh:
        fh.write("# Topic\n\n## A\nshort body\n\n## B\nmore body\n")
    # aggressive multi-turn chat -> queued for distillation
    with open(os.path.join(live, "chat.md"), "w", encoding="utf-8") as fh:
        fh.write("## Prompt\nq1\n## Response\na1\n## Prompt\nq2\n## Response\na2\n")


def test_cadence_dry_run_detects_without_mutating(synth_corpus):
    cfg, _ = synth_corpus
    _seed_corpus(cfg)
    summary = cadence.run(cfg, apply=False, runner=_fake_reindex_runner)
    assert summary["new"] == 2
    # dry-run does not promote/seed/queue
    assert summary["promoted"] == 0
    # inbox stays empty
    assert os.listdir(cfg.inbox_dir) == ["_queue"] or os.listdir(cfg.inbox_dir) == []


def test_cadence_apply_seeds_promotes_and_queues(synth_corpus):
    cfg, _ = synth_corpus
    _seed_corpus(cfg)
    summary = cadence.run(cfg, apply=True, runner=_fake_reindex_runner)

    assert summary["new"] == 2
    assert summary["seeded"] == 1
    assert summary["queued"] == 1
    assert summary["promoted"] == 1
    assert summary["failures"] == []

    # the near-lossless note was promoted into the reference domain
    promoted = os.path.join(cfg.hot_root, "reference", "note.md")
    assert os.path.exists(promoted)

    # the aggressive chat produced a distill-queue descriptor
    queue_files = os.listdir(cfg.queue_dir)
    assert any(f.endswith(".distill.json") for f in queue_files)

    # reindex ran via the injected runner
    assert "reindex" in summary


def test_cadence_apply_is_idempotent_on_second_run(synth_corpus):
    cfg, _ = synth_corpus
    _seed_corpus(cfg)
    cadence.run(cfg, apply=True, runner=_fake_reindex_runner)
    # second run: both files are now seen (promoted source + queued cadence-seen)
    second = cadence.run(cfg, apply=True, runner=_fake_reindex_runner)
    assert second["new"] == 0
    assert second["promoted"] == 0


def test_baseline_marks_everything_seen(synth_corpus):
    cfg, _ = synth_corpus
    _seed_corpus(cfg)
    result = cadence.baseline(cfg, apply=True)
    assert result["baselined"] == 2
    # after baseline, nothing is new
    assert cadence.detect(cfg) == []
