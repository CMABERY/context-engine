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


def test_synthesis_role_renders_authoring_guidance():
    md = compile_pack(
        PackRequest(project="P", role="synthesis", task="write design memo"),
        recall_results={"hot": [], "cold": [], "weak_hot": False})

    assert "/ synthesis" in md
    assert "authoring a high-signal synthesis" in md
    assert "cite each claim" in md


def test_compile_pack_filters_hits_above_admissibility_and_records_exclusion():
    req = PackRequest(project="P", role="research", task="t", max_admissibility="internal")
    hot = [
        {"path": "hot/public.md", "score": 0.9, "admissibility": "public"},
        {"path": "hot/private.md", "score": 0.8, "admissibility": "private"},
    ]
    cold = [
        {"path": "cold/internal.md", "score": 0.7, "admissibility": "internal"},
        {"path": "cold/proprietary.md", "score": 0.6, "admissibility": "proprietary"},
    ]

    md = compile_pack(
        req, recall_results={"hot": hot, "cold": cold, "weak_hot": False})

    assert "hot/public.md" in md
    assert "cold/internal.md" in md
    assert "`hot/private.md` — score" not in md
    assert "`cold/proprietary.md` — score" not in md
    assert "Excluded `hot/private.md`" in md
    assert "admissibility private exceeds max internal" in md


def test_compile_pack_treats_unlabeled_hits_as_internal_not_public():
    hits = [
        {"path": "hot/public.md", "score": 0.9, "admissibility": "public"},
        {"path": "hot/missing.md", "score": 0.8},
        {"path": "hot/null.md", "score": 0.7, "admissibility": None},
        {"path": "hot/empty.md", "score": 0.6, "admissibility": ""},
    ]

    public_md = compile_pack(
        PackRequest(project="P", role="research", task="t",
                    max_admissibility="public"),
        recall_results={"hot": hits, "cold": [], "weak_hot": False})

    assert "`hot/public.md` — score" in public_md
    assert "`hot/missing.md` — score" not in public_md
    assert "`hot/null.md` — score" not in public_md
    assert "`hot/empty.md` — score" not in public_md
    assert (
        "Excluded `hot/missing.md` because admissibility internal exceeds max public"
        in public_md
    )
    assert (
        "Excluded `hot/null.md` because admissibility internal exceeds max public"
        in public_md
    )
    assert (
        "Excluded `hot/empty.md` because admissibility proprietary exceeds max public"
        in public_md
    )

    internal_md = compile_pack(
        PackRequest(project="P", role="research", task="t",
                    max_admissibility="internal"),
        recall_results={"hot": hits, "cold": [], "weak_hot": False})

    assert "`hot/missing.md` — score" in internal_md
    assert "`hot/null.md` — score" in internal_md
    assert "`hot/empty.md` — score" not in internal_md


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
