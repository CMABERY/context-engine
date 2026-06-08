"""CLI smoke tests against synthetic fixtures — doctor, pack, read-only commands,
and the fail-safe refusal on mutating commands without a configured corpus."""
import os

from context_engine import config
from context_engine.cli import main


def _write_config(cfg, tmp_path):
    path = tmp_path / "context-engine.yml"
    path.write_text(config.dump_config(cfg), encoding="utf-8")
    return str(path)


def test_doctor_runs(capsys):
    rc = main(["doctor"])
    out = capsys.readouterr().out
    assert rc in (0, 1)
    assert "context-engine" in out
    assert "doctor status" in out


def test_doctor_json(capsys):
    rc = main(["doctor", "--json"])
    out = capsys.readouterr().out
    assert rc in (0, 1)
    assert '"python"' in out


def test_pack_writes_file(tmp_path, capsys):
    out_file = tmp_path / "pack.md"
    rc = main(["pack", "--project", "Demo", "--role", "execution",
               "--task", "do the thing", "--out", str(out_file)])
    assert rc == 0
    content = out_file.read_text(encoding="utf-8")
    assert "# Context Pack — Demo / execution" in content
    assert "## Next action" in content


def test_pack_uses_project_config_defaults(tmp_path):
    project_cfg = tmp_path / "project-config.yml"
    project_cfg.write_text(
        "\n".join([
            "project: ResearchKB",
            "objective: Synthesize governed research.",
            "packs:",
            "  defaults:",
            "    max_hot: 4",
            "    max_cold: 1",
            "  roles:",
            "    synthesis:",
            "      max_hot: 2",
            "exclusions:",
            "  - Uncited claims.",
            "assumptions:",
            "  - Hot claims cite cold evidence.",
        ]),
        encoding="utf-8",
    )
    out_file = tmp_path / "pack.md"

    rc = main([
        "pack", "--project-config", str(project_cfg), "--role", "synthesis",
        "--task", "write a memo", "--out", str(out_file)])

    assert rc == 0
    content = out_file.read_text(encoding="utf-8")
    assert "# Context Pack — ResearchKB / synthesis" in content
    assert "Synthesize governed research." in content
    assert "Uncited claims." in content
    assert "Hot claims cite cold evidence." in content


def test_pack_unknown_role(capsys):
    rc = main(["pack", "--project", "P", "--role", "bogus", "--task", "t"])
    assert rc == 2


def test_delta_without_config_refuses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no discoverable config here
    rc = main(["delta"])
    assert rc == 2  # ConfigError -> exit 2


def test_delta_with_config(tmp_path, synth_corpus):
    cfg, _ = synth_corpus
    live = cfg.live_roots[0]
    with open(os.path.join(live, "a.md"), "w", encoding="utf-8") as fh:
        fh.write("# a\n\n## s\nbody\n")
    cfg_path = _write_config(cfg, tmp_path)
    rc = main(["delta", "--config", cfg_path, "--json"])
    assert rc == 0


def test_observe_with_config(tmp_path, synth_corpus, capsys):
    cfg, _ = synth_corpus
    live = cfg.live_roots[0]
    with open(os.path.join(live, "a.md"), "w", encoding="utf-8") as fh:
        fh.write("# a\n\n## s\nbody\n")
    cfg_path = _write_config(cfg, tmp_path)
    rc = main(["observe", "--config", cfg_path])
    assert rc == 0


def test_cadence_dry_run_with_config(tmp_path, synth_corpus, capsys):
    cfg, _ = synth_corpus
    cfg_path = _write_config(cfg, tmp_path)
    rc = main(["cadence", "--dry-run", "--config", cfg_path])
    assert rc == 0
    assert "cadence DRY-RUN" in capsys.readouterr().out


def test_baseline_apply_without_config_refuses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["baseline", "--apply"])
    assert rc == 2


def test_cadence_apply_refuses_non_sqlite_index(tmp_path, synth_corpus, capsys):
    cfg, _ = synth_corpus
    # index_db misconfigured to point at a real (non-db) file -> clean refusal.
    with open(cfg.index_db, "w", encoding="utf-8") as fh:
        fh.write("not a database")
    cfg_path = _write_config(cfg, tmp_path)
    rc = main(["cadence", "--apply", "--config", cfg_path])
    assert rc == 2  # clean exit, not an uncaught traceback
    assert "non-sqlite" in capsys.readouterr().err
    # the file was preserved
    with open(cfg.index_db, encoding="utf-8") as fh:
        assert fh.read() == "not a database"


def test_audit_hot_with_config(tmp_path, synth_corpus):
    cfg, _ = synth_corpus
    # one clean artifact -> PASS
    ref = os.path.join(cfg.hot_root, "reference")
    os.makedirs(ref, exist_ok=True)
    with open(os.path.join(ref, "good.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nid: KB-g\nstatus: seeded\ntype: reference-note\n"
                 "sources:\n  - sha256: AB\n---\n\n# G\n\n## S\nshort\n")
    cfg_path = _write_config(cfg, tmp_path)
    rc = main(["audit", "hot", "--config", cfg_path])
    assert rc == 0
