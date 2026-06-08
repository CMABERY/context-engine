"""Load, validate, and resolve :class:`~context_engine.models.EngineConfig`.

The engine ships **no** built-in config that points at a real corpus. An
operator must supply a YAML file (``--config``); until then, mutating commands
refuse to run. Read-only commands (``doctor``) work with defaults so the tool is
always inspectable.
"""
from __future__ import annotations

import os
from typing import Optional

import yaml

from .models import EngineConfig, ProjectConfig
from .utils.manifests import now_utc

# Default config filename searched for in the cwd and its ancestors.
CONFIG_FILENAME = "context-engine.yml"


class ConfigError(Exception):
    """Raised when a config is missing, unparseable, or unsafe to use."""


def load_config(path: str) -> EngineConfig:
    """Load and parse an engine config from ``path``.

    Raises :class:`ConfigError` if the file is missing or not a YAML mapping.
    """
    if not os.path.isfile(path):
        raise ConfigError(f"config file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via tests
        raise ConfigError(f"config is not valid YAML ({path}): {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"config root must be a mapping, got {type(data).__name__}")
    return EngineConfig.from_dict(data)


def load_project_config(path: str) -> ProjectConfig:
    """Load a reusable project/profile pack config from ``path``."""
    if not os.path.isfile(path):
        raise ConfigError(f"project config file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via tests
        raise ConfigError(f"project config is not valid YAML ({path}): {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(
            f"project config root must be a mapping, got {type(data).__name__}")
    return ProjectConfig.from_dict(data)


def find_config(start: Optional[str] = None) -> Optional[str]:
    """Search ``start`` (default cwd) and its ancestors for ``context-engine.yml``.

    Returns the absolute path of the first match, or ``None``.
    """
    here = os.path.abspath(start or os.getcwd())
    while True:
        candidate = os.path.join(here, CONFIG_FILENAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def load_or_find(path: Optional[str]) -> EngineConfig:
    """Load ``path`` if given, else discover a config; else return safe defaults.

    Never raises for a *missing* discovered config — returns an unconfigured
    (fail-safe) :class:`EngineConfig` so read-only commands still function.
    """
    if path:
        return load_config(path)
    found = find_config()
    if found:
        return load_config(found)
    return EngineConfig()


def require_configured(cfg: EngineConfig) -> None:
    """Raise :class:`ConfigError` unless every mutation-required path is set.

    This is the fail-safe that protects a live corpus from an unconfigured or
    default-only install: ``cadence --apply`` and ``baseline --apply`` call it.
    """
    missing = cfg.missing_paths()
    if missing:
        raise ConfigError(
            "refusing to run a mutating operation without a configured corpus; "
            "missing required path(s): " + ", ".join(missing)
            + ". Provide them via --config <context-engine.yml>."
        )


def resolve_manifest_path(cfg: EngineConfig, stage: str) -> str:
    """Return the manifest path to append to for this run.

    Uses ``cfg.manifest_path`` if set, otherwise derives a timestamped file under
    ``manifests_dir`` keyed by ``stage`` so concurrent stages do not interleave.
    """
    if cfg.manifest_path:
        return cfg.manifest_path
    if not cfg.manifests_dir:
        raise ConfigError("manifests_dir is required to derive a manifest path")
    stamp = now_utc().replace(":", "").replace("-", "")
    safe_stage = stage.replace(os.sep, "-").replace(" ", "-")
    return os.path.join(cfg.manifests_dir, f"manifest_{safe_stage}_{stamp}.jsonl")


def dump_config(cfg: EngineConfig) -> str:
    """Serialize a config back to YAML (useful for ``doctor`` / debugging)."""
    return yaml.safe_dump(cfg.to_dict(), sort_keys=False, allow_unicode=True)
