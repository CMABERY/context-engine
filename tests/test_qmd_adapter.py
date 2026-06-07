"""qmd adapter — command construction + recall behaviour with an injected runner.

Adapted from corpus-free fixtures: all paths here are synthetic placeholders.
"""
from context_engine.adapters import qmd
from context_engine.models import QmdConfig

CFG = QmdConfig()

HOT_STRONG = "result: hot/reference/x.md  score: 0.81\nresult: hot/reference/y.md  score: 0.55\n"
HOT_WEAK = "result: hot/reference/x.md  score: 0.12\n"
HOT_MISS = "No results found.\n"
COLD_HIT = "result: cold/held/bar.md  score: 0.72\n"


# --- command construction -------------------------------------------------

def test_hot_command_shape():
    cmd = qmd.hot_command("my query", CFG)
    assert cmd[0] == "query"
    assert "--json" in cmd
    assert "--index" not in cmd
    assert cmd[-1] == '"my query"'


def test_cold_command_uses_search_and_index():
    cmd = qmd.cold_command("my query", CFG)
    assert cmd[0] == "search"
    assert "query" not in cmd
    assert "--index" in cmd
    assert "cold" in cmd


def test_cold_command_respects_custom_index():
    cmd = qmd.cold_command("q", QmdConfig(cold_index="archive"))
    assert "archive" in cmd


def test_query_quoting_escapes_quotes():
    cmd = qmd.hot_command('say "hi"', CFG)
    assert cmd[-1] == '"say \\"hi\\""'


def test_reindex_commands():
    commands, labels = qmd.reindex_commands(CFG)
    assert commands == [["update"], ["embed", "-c", "hot"], ["status"]]
    assert labels == ["update", "embed", "status"]
    # honors hot_collection
    cmds2, _ = qmd.reindex_commands(QmdConfig(hot_collection="primary"))
    assert ["embed", "-c", "primary"] in cmds2


# --- parsing --------------------------------------------------------------

def test_parse_results_text_and_miss():
    assert qmd.parse_results(HOT_STRONG)[0]["score"] == 0.81
    assert qmd.parse_results(HOT_MISS) == []


def test_parse_results_json_with_noise():
    raw = 'Reranking...\n[{"score": 0.9, "file": "qmd://hot/a.md"}]\n'
    out = qmd.parse_results(raw)
    assert out[0]["score"] == 0.9
    assert out[0]["path"].endswith("a.md")


def test_should_fallback():
    assert qmd.should_fallback(HOT_MISS) is True
    assert qmd.should_fallback(HOT_WEAK) is True
    assert qmd.should_fallback(HOT_STRONG) is False


# --- recall (both tiers always run) --------------------------------------

def test_recall_runs_both_tiers():
    calls = []

    def fake_runner(args):
        calls.append(args)
        return COLD_HIT if ("--index" in args) else HOT_STRONG

    out = qmd.recall("q", qmd=CFG, runner=fake_runner)
    hot_calls = [c for c in calls if "query" in c and "--index" not in c]
    cold_calls = [c for c in calls if "--index" in c]
    assert len(hot_calls) == 1 and len(cold_calls) == 1
    assert out["hot"][0]["score"] == 0.81
    assert out["cold"][0]["path"].endswith("bar.md")
    assert out["tiers"] == ["hot", "cold"]
    assert out["weak_hot"] is False


def test_recall_dedup_and_cap():
    hot = [{"path": "qmd://hot/x.md", "score": 0.8}]
    cold = [{"path": "qmd://hot/x.md?index=cold", "score": 0.7},
            {"path": "qmd://cold/u.md?index=cold", "score": 0.6}]
    deduped = qmd._dedup_cold(hot, cold)
    assert not any("x.md" in r["path"] for r in deduped)
    assert any("u.md" in r["path"] for r in deduped)


def test_recall_weak_hot_flag():
    def fake_runner(args):
        return COLD_HIT if "--index" in args else HOT_WEAK
    out = qmd.recall("q", qmd=CFG, runner=fake_runner)
    assert out["weak_hot"] is True
    assert len(out["cold"]) > 0  # cold still surfaced


# --- probe ----------------------------------------------------------------

def test_probe_available():
    out = qmd.probe(qmd=CFG, runner=lambda a: "qmd 1.4.2")
    assert out["available"] is True


def test_probe_unavailable_on_error():
    def boom(args):
        raise OSError("not found")
    out = qmd.probe(qmd=CFG, runner=boom)
    assert out["available"] is False
