
import pytest

from context_engine import config
from context_engine.config import ConfigError
from context_engine.models import EngineConfig


def test_default_config_is_not_configured():
    cfg = EngineConfig()
    assert cfg.is_configured() is False
    assert cfg.missing_paths()  # non-empty


def test_from_dict_sets_paths_and_qmd():
    cfg = EngineConfig.from_dict({
        "org_root": "/c/x", "live_roots": ["/c/x/live"], "hot_root": "/c/x/_hot",
        "inbox_dir": "/c/x/_hot/_inbox", "index_db": "/c/x/_prov/i.sqlite",
        "manifests_dir": "/c/x/_prov",
        "qmd": {"bin": "/opt/qmd", "cold_index": "archive"},
        "unknown_key": "ignored",
    })
    assert cfg.is_configured() is True
    assert cfg.qmd.bin == "/opt/qmd"
    assert cfg.qmd.cold_index == "archive"


def test_to_dict_from_dict_roundtrip():
    cfg = EngineConfig.from_dict({"hot_root": "/c/x/_hot", "id_prefix": "ACME-"})
    again = EngineConfig.from_dict(cfg.to_dict())
    assert again.hot_root == "/c/x/_hot"
    assert again.id_prefix == "ACME-"
    assert again.qmd.hot_collection == cfg.qmd.hot_collection


def test_load_config_reads_yaml(tmp_path):
    p = tmp_path / "context-engine.yml"
    p.write_text("hot_root: /c/x/_hot\nid_prefix: ACME-\nqmd:\n  bin: qmd2\n",
                 encoding="utf-8")
    cfg = config.load_config(str(p))
    assert cfg.hot_root == "/c/x/_hot"
    assert cfg.id_prefix == "ACME-"
    assert cfg.qmd.bin == "qmd2"


def test_load_config_missing_raises(tmp_path):
    with pytest.raises(ConfigError):
        config.load_config(str(tmp_path / "nope.yml"))


def test_load_config_non_mapping_raises(tmp_path):
    p = tmp_path / "bad.yml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        config.load_config(str(p))


def test_find_config_walks_up(tmp_path):
    (tmp_path / "context-engine.yml").write_text("hot_root: /x\n", encoding="utf-8")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    found = config.find_config(str(deep))
    assert found == str(tmp_path / "context-engine.yml")


def test_require_configured(tmp_path):
    with pytest.raises(ConfigError):
        config.require_configured(EngineConfig())
    cfg = EngineConfig(org_root="/c/x", live_roots=["/c/x/live"], hot_root="/c/x/_hot",
                       inbox_dir="/c/x/_hot/_inbox", index_db="/c/x/i.sqlite",
                       manifests_dir="/c/x/_prov")
    config.require_configured(cfg)  # does not raise


def test_resolve_manifest_path_explicit():
    cfg = EngineConfig(manifest_path="/c/x/m.jsonl", manifests_dir="/c/x")
    assert config.resolve_manifest_path(cfg, "cadence") == "/c/x/m.jsonl"


def test_resolve_manifest_path_derived(tmp_path):
    cfg = EngineConfig(manifests_dir=str(tmp_path))
    mp = config.resolve_manifest_path(cfg, "cadence")
    assert mp.startswith(str(tmp_path))
    assert "cadence" in mp and mp.endswith(".jsonl")


def test_resolve_manifest_path_needs_dir():
    with pytest.raises(ConfigError):
        config.resolve_manifest_path(EngineConfig(), "cadence")


def test_load_or_find_defaults_when_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = config.load_or_find(None)
    assert isinstance(cfg, EngineConfig)
    assert cfg.is_configured() is False
