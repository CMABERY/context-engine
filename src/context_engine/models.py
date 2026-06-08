"""Typed data models for the context engine.

Everything configurable lives in :class:`EngineConfig`. The defaults here are
deliberately **generic** — there are no absolute paths, drive letters, mount
roots, client names, or project identifiers baked in. Corpus location is
supplied by the operator via a YAML config (see ``examples/context-engine.yml``)
and every corpus path defaults to ``None`` so a misconfigured or default-only
install **fails safe**: mutating commands refuse to run until paths are set.

Models are plain ``dataclasses`` (stdlib) — no third-party validation
dependency. :mod:`context_engine.config` provides loading/validation helpers.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Generic policy defaults (corpus-agnostic)
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDE_GLOBS: list[str] = [
    "**/.venv/**",
    "**/.git/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "_provenance/**",
]

# type (frontmatter) -> hot domain subfolder. Generic vocabulary only.
DEFAULT_DOMAIN_MAP: dict[str, str] = {
    "decision-record": "decisions",
    "decision-log": "decisions",
    "canonical-record": "decisions",
    "system-prompt": "governance",
    "governance": "governance",
    "canonical-constitution": "governance",
    "protocol": "orchestration",
    "orchestration": "orchestration",
    "reference-note": "reference",
    "doctrine": "reference",
}

# classifier archetype -> frontmatter `type` used when the engine mechanically
# seeds a near-lossless artifact (which the domain map then routes).
DEFAULT_ARCHETYPE_TYPE_MAP: dict[str, str] = {
    "DECISION_LOG": "decision-log",
    "GOVERNANCE_PROMPT": "governance",
    "CODE_SPEC": "reference-note",
    "EVAL_BUNDLE": "reference-note",
    "FINISHED_REPORT": "reference-note",
    "REFERENCE_NOTE": "reference-note",
    "WRAPPED_DELIVERABLE": "reference-note",
    "EXPLORATORY_CHAT": "decision-record",
}

# Near-lossless archetypes gate on source-coverage; aggressive archetypes gate
# on faithfulness instead (the cold original is the real no-loss net).
DEFAULT_COVERAGE_FLOORS: dict[str, float] = {
    "WRAPPED_DELIVERABLE": 0.95,
    "REFERENCE_NOTE": 0.95,
    "GOVERNANCE_PROMPT": 0.95,
    "CODE_SPEC": 0.95,
    "EVAL_BUNDLE": 0.95,
    "DECISION_LOG": 0.40,
    "FINISHED_REPORT": 0.80,
}

DEFAULT_AGGRESSIVE_ARCHETYPES: list[str] = ["EXPLORATORY_CHAT"]

# Leading export-tool prefixes stripped when deriving slugs/titles. Generic
# assistant export conventions, not corpus-specific.
DEFAULT_EXPORT_PREFIXES: list[str] = ["claude-", "chatgpt-"]

# Basename stems whose identity lives in the parent dir — never near-dup clustered.
DEFAULT_GENERIC_STEMS: list[str] = [
    "readme", "changelog", "notes", "index", "status", "manifest",
    "examples", "todo", "license", "contributing", "summary", "overview",
    "_index",
]

DEFAULT_DISTILL_INSTRUCTIONS: str = (
    "Distill faithfully (faithfulness >= {faithfulness_floor}): preserve every "
    "decision, name, number, currency amount, percentage, and date, and every "
    "reusable prompt; drop model thinking blocks, tool/web-search dumps, and "
    "dead-end chains. Include a '## Stripping Ledger' section listing the dropped "
    "categories, and a sources[] sha256 link-back in the YAML frontmatter. Write "
    "the result to target_inbox_path."
)

# Unified status enum for normalization and seeding.
DEFAULT_VALID_STATUSES: list[str] = [
    "draft", "reviewed", "stable", "seeded", "evergreen", "archived",
]
DEFAULT_STATUS_MAP: dict[str, str] = {
    "active": "reviewed", "current": "reviewed", "published": "reviewed",
    "frozen": "stable", "final": "stable", "complete": "stable",
    "completed": "stable", "in-progress": "draft", "in_progress": "draft",
    "wip": "draft", "todo": "draft", "obsolete": "archived",
    "deprecated": "archived", "retired": "archived", "planted": "seeded",
    "seed": "seeded",
}

ADMISSIBILITY_LEVELS: tuple[str, ...] = (
    "public", "internal", "private", "proprietary")


def normalize_admissibility(value: str | None, *, default: str = "internal") -> str:
    """Return a normalized admissibility level, defaulting unknowns conservatively."""
    level = str(value or default).strip().lower()
    return level if level in ADMISSIBILITY_LEVELS else default


def admissibility_rank(value: str | None) -> int:
    """Ordinal rank for admissibility comparisons."""
    return ADMISSIBILITY_LEVELS.index(normalize_admissibility(value))


# ---------------------------------------------------------------------------
# Recall-backend config
# ---------------------------------------------------------------------------

@dataclass
class QmdConfig:
    """Configuration for the ``qmd`` recall/index adapter.

    All values are generic. ``cwd`` and ``bin`` point wherever the operator's
    backend lives; they default to a relative cwd and a bare ``qmd`` on PATH so
    nothing host-specific is embedded.
    """

    cwd: str = "."
    bin: str = "qmd"
    # Wrap each invocation in ``wsl bash -lc '...'`` (Windows host calling a
    # WSL-installed backend). When already inside POSIX, set login_shell instead.
    wsl_wrap: bool = False
    # Run via ``bash -lc`` so ``~`` expands and the login PATH is honored.
    login_shell: bool = False
    hot_collection: str = "hot"
    cold_index: str = "cold"
    hot_verb: str = "query"
    cold_verb: str = "search"
    json_flag: str = "--json"
    rerank_floor: float = 0.30   # flags "weak" hot hits; does NOT gate cold
    cold_cap: int = 5            # max cold hits surfaced after dedup

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "QmdConfig":
        data = data or {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Engine config
# ---------------------------------------------------------------------------

# Corpus path fields — these MUST be set for any mutating operation. Listed here
# so validation and the CLI fail-safe can check them generically.
_MUTATION_PATH_FIELDS = ("org_root", "live_roots", "hot_root", "inbox_dir",
                         "index_db", "manifests_dir")


@dataclass
class EngineConfig:
    """The full engine configuration. Corpus paths default to ``None``/empty."""

    # --- corpus paths (fail-safe: unset by default) ---
    org_root: Optional[str] = None
    live_roots: list[str] = field(default_factory=list)
    hot_root: Optional[str] = None
    inbox_dir: Optional[str] = None
    queue_dir: Optional[str] = None
    held_root: Optional[str] = None
    superseded_root: Optional[str] = None
    near_dup_cold: Optional[str] = None
    manifests_dir: Optional[str] = None
    index_db: Optional[str] = None
    # Optional fixed manifest path; if unset, the engine derives a timestamped
    # one under manifests_dir per run.
    manifest_path: Optional[str] = None

    # --- recall backend ---
    qmd: QmdConfig = field(default_factory=QmdConfig)

    # --- policy knobs (generic, safe defaults) ---
    path_style: str = "native"
    exclude_globs: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_GLOBS))
    # ordered (substring, tier) rules; first match wins. Empty -> all "live".
    tier_rules: list[list[str]] = field(default_factory=list)
    domain_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_DOMAIN_MAP))
    default_domain: str = "reference"
    archetype_type_map: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ARCHETYPE_TYPE_MAP))
    aggressive_archetypes: list[str] = field(
        default_factory=lambda: list(DEFAULT_AGGRESSIVE_ARCHETYPES))
    coverage_floors: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_COVERAGE_FLOORS))
    faithfulness_floor: float = 0.90
    chunk_max_est_tokens: int = 850
    chunk_max_chars: int = 3600
    export_prefixes: list[str] = field(
        default_factory=lambda: list(DEFAULT_EXPORT_PREFIXES))
    generic_stems: list[str] = field(
        default_factory=lambda: list(DEFAULT_GENERIC_STEMS))
    near_dup_threshold: float = 0.90
    id_prefix: str = "KB-"
    default_status: str = "seeded"
    valid_statuses: list[str] = field(
        default_factory=lambda: list(DEFAULT_VALID_STATUSES))
    status_map: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_STATUS_MAP))
    distill_instructions: str = DEFAULT_DISTILL_INSTRUCTIONS
    require_confidence_for_types: list[str] = field(default_factory=list)
    valid_confidences: list[str] = field(
        default_factory=lambda: ["low", "medium", "high"])
    # Advisory size ceiling (bytes) for the hot-surface audit.
    oversize_bytes: int = 51_200

    # ------------------------------------------------------------------ #
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "EngineConfig":
        """Build a config from a parsed YAML/JSON mapping (unknown keys ignored)."""
        data = dict(data or {})
        qmd = QmdConfig.from_dict(data.pop("qmd", None))
        known = {f.name for f in fields(cls)} - {"qmd"}
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(qmd=qmd, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if f.name == "qmd":
                out["qmd"] = {qf.name: getattr(val, qf.name) for qf in fields(val)}
            else:
                out[f.name] = val
        return out

    def with_overrides(self, **kwargs: Any) -> "EngineConfig":
        return replace(self, **kwargs)

    # ------------------------------------------------------------------ #
    def missing_paths(self) -> list[str]:
        """Return the names of mutation-required path fields that are unset."""
        missing = []
        for name in _MUTATION_PATH_FIELDS:
            val = getattr(self, name)
            if not val:
                missing.append(name)
        return missing

    def is_configured(self) -> bool:
        """True iff every mutation-required corpus path is set (fail-safe gate)."""
        return not self.missing_paths()

    def effective_tier_rules(self) -> list[tuple[str, str]]:
        """Tier rules to use, deriving sensible ones from paths if none given.

        If ``tier_rules`` is empty, derive: hot_root -> 'hot', superseded/held
        -> 'cold'. This keeps the provenance index useful out of the box without
        embedding any corpus-specific layout in code.
        """
        if self.tier_rules:
            return [(r[0], r[1]) for r in self.tier_rules]
        derived: list[tuple[str, str]] = []
        if self.hot_root:
            derived.append((self.hot_root, "hot"))
        for cold in (self.superseded_root, self.held_root, self.near_dup_cold):
            if cold:
                derived.append((cold, "cold"))
        return derived


# ---------------------------------------------------------------------------
# Lightweight result models for the public API surface
# ---------------------------------------------------------------------------

@dataclass
class RecallHit:
    path: str
    score: float
    tier: str = "hot"


@dataclass
class PackRequest:
    """A request to compile a context pack."""

    project: str
    role: str
    task: str
    objective: str = ""
    # cap on hot artifacts and cold evidence items included
    max_hot: int = 8
    max_cold: int = 3
    max_admissibility: str = "internal"
    # explicit extra exclusions / assumptions / risks the caller wants recorded
    exclusions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class PackDefaults:
    """Reusable pack defaults loaded from a project/profile config."""

    max_hot: Optional[int] = None
    max_cold: Optional[int] = None
    max_admissibility: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PackDefaults":
        data = data or {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def merged(self, other: "PackDefaults") -> "PackDefaults":
        return PackDefaults(
            max_hot=other.max_hot if other.max_hot is not None else self.max_hot,
            max_cold=other.max_cold if other.max_cold is not None else self.max_cold,
            max_admissibility=(
                other.max_admissibility
                if other.max_admissibility is not None else self.max_admissibility),
        )


@dataclass
class ProjectPackConfig:
    """Pack defaults and per-role overrides for a project/profile config."""

    defaults: PackDefaults = field(default_factory=PackDefaults)
    roles: dict[str, PackDefaults] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProjectPackConfig":
        data = data or {}
        roles = {
            str(role): PackDefaults.from_dict(value)
            for role, value in dict(data.get("roles") or {}).items()
        }
        return cls(defaults=PackDefaults.from_dict(data.get("defaults")), roles=roles)

    def for_role(self, role: str) -> PackDefaults:
        return self.defaults.merged(self.roles.get(role, PackDefaults()))


@dataclass
class ProjectConfig:
    """Reusable project/profile defaults layered on top of engine config."""

    project: str = ""
    profile: str = ""
    objective: str = ""
    prefer_domains: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    packs: ProjectPackConfig = field(default_factory=ProjectPackConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProjectConfig":
        data = dict(data or {})
        packs = ProjectPackConfig.from_dict(data.pop("packs", None))
        known = {f.name for f in fields(cls)} - {"packs"}
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(packs=packs, **kwargs)

    def to_pack_request(
        self, *, role: str, task: str, project: str | None = None,
        objective: str | None = None, max_hot: int | None = None,
        max_cold: int | None = None, max_admissibility: str | None = None,
    ) -> PackRequest:
        defaults = self.packs.for_role(role)
        resolved_project = project or self.project or self.profile
        resolved_objective = objective if objective is not None else self.objective
        return PackRequest(
            project=resolved_project,
            role=role,
            task=task,
            objective=resolved_objective or "",
            max_hot=max_hot if max_hot is not None else (
                defaults.max_hot if defaults.max_hot is not None else 8),
            max_cold=max_cold if max_cold is not None else (
                defaults.max_cold if defaults.max_cold is not None else 3),
            max_admissibility=normalize_admissibility(
                max_admissibility or defaults.max_admissibility),
            exclusions=list(self.exclusions),
            assumptions=list(self.assumptions),
        )
