"""Role specifications for context packs.

A *context pack* is a role-specific projection of memory. The role determines
which memory tiers are admissible and how the agent should treat them — encoding
the engine's governance principles:

* Agents do **not** read the raw corpus by default (principle 5).
* Cold access requires a reason — proof, exact source, verification, or missing
  hot context (principle 6). So ``execution``/``orchestration`` packs exclude
  cold by default, while ``verification``/``research`` packs include it with the
  reason stated.

Each :class:`RoleSpec` is data, not code, so new roles are a dict entry.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoleSpec:
    name: str
    framing: str
    include_cold: bool
    cold_reason: str
    verification_requirements: tuple[str, ...]
    next_action: str  # ``str.format`` template; receives {task}, {project}
    default_exclusions: tuple[str, ...] = field(default_factory=tuple)


ROLE_SPECS: dict[str, RoleSpec] = {
    "orchestration": RoleSpec(
        name="orchestration",
        framing=(
            "You are orchestrating work. Use this pack to plan and delegate. "
            "Operate from curated hot memory only; do not open the raw corpus."
        ),
        include_cold=False,
        cold_reason="excluded — orchestration plans from curated hot memory.",
        verification_requirements=(
            "Confirm each delegated sub-task maps to an included hot artifact or a "
            "stated assumption.",
            "Flag any objective that cannot be grounded in the included context.",
        ),
        next_action=(
            "Produce a delegation plan for: {task}. For each step, cite the hot "
            "artifact(s) it relies on, or mark it as needing a cold-evidence pass."
        ),
        default_exclusions=(
            "Raw corpus / transcripts (not admissible at orchestration altitude).",
            "Cold originals (request a verification pack if proof is needed).",
        ),
    ),
    "execution": RoleSpec(
        name="execution",
        framing=(
            "You are executing a single task. Everything you need is in this pack. "
            "Do NOT read the raw corpus; if the pack is insufficient, say so rather "
            "than guessing."
        ),
        include_cold=False,
        cold_reason="excluded — execution works from the curated hot slice.",
        verification_requirements=(
            "Every claim in your output must trace to an included hot artifact.",
            "If a required fact is absent from the pack, stop and request it; do not "
            "fabricate.",
        ),
        next_action=(
            "Carry out: {task}. Use only the included hot artifacts. Note any gap "
            "that blocks completion instead of reading outside the pack."
        ),
        default_exclusions=(
            "Raw corpus, transcripts, and cold originals.",
            "Any source not surfaced as an included hot artifact.",
        ),
    ),
    "verification": RoleSpec(
        name="verification",
        framing=(
            "You are verifying claims against evidence. Cold originals are included "
            "BECAUSE verification is a valid reason to open the cold layer."
        ),
        include_cold=True,
        cold_reason="included — verification is an admissible reason for cold access.",
        verification_requirements=(
            "Check each hot artifact's assertions against the cold evidence by "
            "sha256 link-back, not by filename.",
            "Report any unsupported or contradicted claim with its source hash.",
            "Treat the cold original as authoritative where hot and cold disagree.",
        ),
        next_action=(
            "Verify: {task}. For each claim, cite the cold source (sha256) that "
            "supports or refutes it, and give a pass/fail verdict."
        ),
        default_exclusions=(
            "Material outside the cited sources (out of verification scope).",
        ),
    ),
    "research": RoleSpec(
        name="research",
        framing=(
            "You are researching an open question. Hot memory is the starting point; "
            "cold evidence is included because the hot surface may be incomplete."
        ),
        include_cold=True,
        cold_reason="included — research may need context missing from hot memory.",
        verification_requirements=(
            "Distinguish findings grounded in included context from inferences.",
            "Cite sources by sha256 where available; mark gaps explicitly.",
        ),
        next_action=(
            "Research: {task}. Synthesize across the hot and cold material provided, "
            "citing sources, and list what remains unknown."
        ),
        default_exclusions=(
            "Speculation presented as fact (label inferences clearly).",
        ),
    ),
    "synthesis": RoleSpec(
        name="synthesis",
        framing=(
            "You are authoring a high-signal synthesis from governed memory. Work "
            "from curated hot claims first, cite each claim as you write, and do "
            "not invent beyond the included artifacts."
        ),
        include_cold=False,
        cold_reason=(
            "excluded — synthesis works from promoted hot claims; request a "
            "verification pack when exact cold proof is needed."
        ),
        verification_requirements=(
            "Every synthesized assertion must trace to an included hot artifact.",
            "Flag missing evidence or contradictions as gaps rather than prose.",
            "Do not cite material excluded by admissibility.",
        ),
        next_action=(
            "Author the synthesis for: {task}. Cite included hot artifacts inline "
            "and end with unresolved / needs-evidence gaps."
        ),
        default_exclusions=(
            "Cold originals unless a verification pack is requested.",
            "Claims without an included hot artifact citation.",
        ),
    ),
    "handoff": RoleSpec(
        name="handoff",
        framing=(
            "You are receiving a handoff. This pack is the durable state of the "
            "work so far; continue from it without re-reading the raw corpus."
        ),
        include_cold=False,
        cold_reason="excluded — handoff carries curated state; request cold if needed.",
        verification_requirements=(
            "Reconstruct current status from the included artifacts before acting.",
            "Surface any ambiguity in the handed-off state rather than assuming.",
        ),
        next_action=(
            "Resume: {task}. Begin from the included state; list your first three "
            "concrete actions and any clarification you need."
        ),
        default_exclusions=(
            "Stale context superseded by the included artifacts.",
        ),
    ),
}

ROLES: tuple[str, ...] = tuple(ROLE_SPECS.keys())


def get_role(role: str) -> RoleSpec:
    """Return the :class:`RoleSpec` for ``role`` or raise ValueError."""
    try:
        return ROLE_SPECS[role]
    except KeyError:
        raise ValueError(
            f"unknown role {role!r}; valid roles: {', '.join(ROLES)}"
        ) from None
