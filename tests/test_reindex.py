"""Reindex executor: the runner is injected, so no live backend is needed."""
from context_engine.core import reindex


def test_dry_run_returns_planned_without_calling_runner():
    calls = []

    def runner(argv):
        calls.append(argv)
        return "should not run"

    out = reindex.run([["update"], ["embed", "-c", "hot"]],
                      runner=runner, apply=False)
    assert out == {"planned": [["update"], ["embed", "-c", "hot"]]}
    assert calls == []


def test_apply_invokes_runner_in_order_with_labels():
    calls = []

    def runner(argv):
        calls.append(argv)
        return "ran:" + argv[0]

    out = reindex.run([["update"], ["status"]], runner=runner, apply=True,
                      labels=["update", "status"])
    assert calls == [["update"], ["status"]]
    assert out == {"update": "ran:update", "status": "ran:status"}


def test_apply_default_step_labels():
    out = reindex.run([["a"], ["b"]], runner=lambda a: "ok", apply=True)
    assert set(out) == {"step0", "step1"}
