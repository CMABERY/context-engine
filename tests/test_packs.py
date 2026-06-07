import pytest

from context_engine.models import PackRequest
from context_engine.packs import templates
from context_engine.packs.compiler import compile_pack, render_pack

_SECTIONS = ["## Objective", "## Role", "## Task", "## Included hot artifacts",
             "## Cold evidence", "## Exclusions", "## Assumptions", "## Risks",
             "## Verification requirements", "## Next action"]


def test_render_pack_has_all_sections():
    md = render_pack(project="P", role="execution", task="do X", objective="O",
                     hot=[{"path": "hot/a.md", "score": 0.9}], cold=[],
                     exclusions=["no corpus"], assumptions=["a1"], risks=["r1"])
    for sec in _SECTIONS:
        assert sec in md
    assert "# Context Pack — P / execution" in md


def test_execution_role_omits_cold():
    md = render_pack(project="P", role="execution", task="t", objective="o",
                     hot=[], cold=[{"path": "cold/x.md", "score": 0.5}],
                     exclusions=[], assumptions=[], risks=[])
    assert "Omitted" in md  # cold deliberately excluded for execution


def test_verification_role_includes_cold():
    md = render_pack(project="P", role="verification", task="t", objective="o",
                     hot=[], cold=[{"path": "cold/x.md", "score": 0.5,
                                    "sha256": "ABCDEF0123456789"}],
                     exclusions=[], assumptions=[], risks=[])
    assert "cold/x.md" in md
    assert "Cold evidence (1)" in md


def test_compile_pack_uses_injected_recall_and_caps_hot():
    hits = [{"path": f"hot/{i}.md", "score": 0.9 - i * 0.01} for i in range(10)]
    req = PackRequest(project="P", role="execution", task="t", max_hot=3)
    md = compile_pack(req, recall_results={"hot": hits, "cold": [], "weak_hot": False})
    assert "Included hot artifacts (3)" in md
    assert "hot/0.md" in md
    assert "hot/4.md" not in md


def test_compile_pack_weak_hot_adds_risk():
    req = PackRequest(project="P", role="research", task="t")
    md = compile_pack(req, recall_results={"hot": [], "cold": [], "weak_hot": True})
    assert "Hot recall was weak" in md


def test_research_role_surfaces_cold_via_compile():
    req = PackRequest(project="P", role="research", task="t", max_cold=2)
    cold = [{"path": "cold/a.md", "score": 0.6}, {"path": "cold/b.md", "score": 0.5}]
    md = compile_pack(req, recall_results={"hot": [], "cold": cold, "weak_hot": False})
    assert "cold/a.md" in md and "cold/b.md" in md


def test_unknown_role_raises():
    with pytest.raises(ValueError):
        templates.get_role("nonsense")
    with pytest.raises(ValueError):
        compile_pack(PackRequest(project="P", role="nope", task="t"),
                     recall_results={"hot": [], "cold": []})


def test_all_roles_render():
    for role in templates.ROLES:
        md = compile_pack(PackRequest(project="P", role=role, task="t"),
                          recall_results={"hot": [], "cold": [], "weak_hot": False})
        assert f"/ {role}" in md
