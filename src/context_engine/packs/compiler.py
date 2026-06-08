"""Context-pack compiler.

``render_pack`` is a **pure** function: given role + task + already-retrieved hot
(and optional cold) hits, it emits the markdown pack. It does no I/O, so it is
unit-tested by injecting recall results — no backend required.

``compile_pack`` is the thin orchestration: it runs recall (via the qmd adapter
or an injected runner / pre-fetched results), applies the role's admissibility
rules, then calls ``render_pack``.

A pack always contains: objective, role, task, included hot artifacts, optional
cold evidence, exclusions, assumptions, risks, verification requirements, and a
next-action prompt.
"""
from __future__ import annotations

from typing import Optional

from ..models import EngineConfig, PackRequest, admissibility_rank, normalize_admissibility
from .templates import RoleSpec, get_role


def _fmt_hits(hits: list[dict]) -> list[str]:
    lines = []
    for h in hits:
        path = h.get("path", "?")
        score = h.get("score")
        sha = h.get("sha256")
        score_s = f" — score {score:.3f}" if isinstance(score, (int, float)) else ""
        sha_s = f" — sha256 `{str(sha)[:16]}…`" if sha else ""
        lines.append(f"- `{path}`{score_s}{sha_s}")
    return lines


def _section(title: str, body_lines: list[str]) -> str:
    body = "\n".join(body_lines) if body_lines else "_(none)_"
    return f"## {title}\n\n{body}\n"


def _filter_by_admissibility(
    hits: list[dict], max_admissibility: str,
) -> tuple[list[dict], list[str]]:
    allowed = admissibility_rank(max_admissibility)
    included: list[dict] = []
    exclusions: list[str] = []
    max_level = normalize_admissibility(max_admissibility)
    for hit in hits:
        raw_level = hit.get("admissibility")
        if raw_level is None:
            level = normalize_admissibility(None, default="internal")
        else:
            level = normalize_admissibility(str(raw_level), default="proprietary")
        if admissibility_rank(level) <= allowed:
            included.append(hit)
            continue
        path = hit.get("path", "?")
        exclusions.append(
            f"Excluded `{path}` because admissibility {level} exceeds max {max_level}.")
    return included, exclusions


def render_pack(*, project: str, role: str, task: str, objective: str,
                hot: list[dict], cold: list[dict],
                exclusions: list[str], assumptions: list[str], risks: list[str],
                role_spec: Optional[RoleSpec] = None,
                weak_hot: bool = False) -> str:
    """Render a context pack to markdown. Pure — no I/O."""
    spec = role_spec or get_role(role)

    parts: list[str] = []
    parts.append(f"# Context Pack — {project} / {role}\n")
    parts.append(
        "> Role-specific projection of governed memory. sha256 is the source "
        "authority; paths are hints. Do not read the raw corpus unless this pack "
        "directs you to.\n"
    )

    parts.append(_section("Objective", [objective or "_(derive from the task below)_"]))
    parts.append(_section("Role", [spec.framing]))
    parts.append(_section("Task", [task]))

    parts.append(_section(
        f"Included hot artifacts ({len(hot)})",
        _fmt_hits(hot) or ["_No hot artifacts surfaced for this task._"]))

    if spec.include_cold:
        parts.append(_section(
            f"Cold evidence ({len(cold)})",
            _fmt_hits(cold) or ["_No cold evidence surfaced._"]))
    else:
        parts.append(_section("Cold evidence", [
            f"_Omitted — {spec.cold_reason}_"]))

    parts.append(_section("Exclusions", [f"- {e}" for e in exclusions]))
    parts.append(_section("Assumptions", [f"- {a}" for a in assumptions]))

    risk_lines = [f"- {r}" for r in risks]
    if weak_hot:
        risk_lines.append(
            "- Hot recall was weak (top hot score below the rerank floor); the "
            "included hot artifacts may be loosely related to the task.")
    parts.append(_section("Risks", risk_lines))

    parts.append(_section("Verification requirements",
                          [f"- {v}" for v in spec.verification_requirements]))

    parts.append(_section("Next action",
                          [spec.next_action.format(task=task, project=project)]))

    return "\n".join(parts).rstrip() + "\n"


def compile_pack(request: PackRequest, *, config: Optional[EngineConfig] = None,
                 recall_runner=None, recall_results: Optional[dict] = None,
                 ) -> str:
    """Compile a context pack for ``request``.

    ``recall_results`` (a ``{"hot": [...], "cold": [...], "weak_hot": bool}`` dict)
    short-circuits retrieval — used by tests and callers that already have hits.
    Otherwise recall runs via the qmd adapter using ``config.qmd`` and an optional
    injected ``recall_runner``.
    """
    config = config or EngineConfig()
    spec = get_role(request.role)

    if recall_results is None:
        from ..adapters import qmd as qmd_adapter
        recall_results = qmd_adapter.recall(
            request.task, qmd=config.qmd, runner=recall_runner)

    hot_hits, hot_exclusions = _filter_by_admissibility(
        list(recall_results.get("hot", [])), request.max_admissibility)
    cold_hits, cold_exclusions = _filter_by_admissibility(
        list(recall_results.get("cold", [])), request.max_admissibility)
    hot = hot_hits[: request.max_hot]
    cold = (cold_hits[: request.max_cold] if spec.include_cold else [])
    weak_hot = bool(recall_results.get("weak_hot", False))

    exclusions = (
        list(spec.default_exclusions)
        + list(request.exclusions)
        + hot_exclusions
        + (cold_exclusions if spec.include_cold else [])
    )
    objective = request.objective or (
        f"Equip the {request.role} agent to act on the task using governed memory.")

    return render_pack(
        project=request.project, role=request.role, task=request.task,
        objective=objective, hot=hot, cold=cold, exclusions=exclusions,
        assumptions=list(request.assumptions), risks=list(request.risks),
        role_spec=spec, weak_hot=weak_hot)
