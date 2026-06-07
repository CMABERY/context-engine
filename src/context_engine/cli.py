"""``context-engine`` command-line interface.

Commands::

    context-engine doctor
    context-engine observe   [--config CFG]
    context-engine delta     [--config CFG]
    context-engine baseline  [--config CFG] [--apply]
    context-engine cadence   [--config CFG] [--dry-run | --apply]
    context-engine pack --project P --role R --task "..." [--config CFG] [--out FILE]
    context-engine audit hot [--config CFG]

``doctor`` and ``pack`` run without a config so the tool is always inspectable.
The scan/audit commands (``observe``, ``delta``, ``audit hot``, and the
``baseline``/``cadence`` dry-runs) need corpus read paths via ``--config`` — they
cannot inspect a corpus whose location is unknown. The ``--apply`` mutators
(``baseline --apply``, ``cadence --apply``) additionally call the fail-safe gate
and refuse to run without a fully-configured corpus.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import __version__
from .config import ConfigError, load_or_find, require_configured
from .models import EngineConfig, PackRequest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _need(cfg: EngineConfig, *field_names: str) -> None:
    """Raise ConfigError if any named config path is unset (read-path check)."""
    missing = [f for f in field_names if not getattr(cfg, f)]
    if missing:
        raise ConfigError(
            "missing required config path(s) for this command: "
            + ", ".join(missing) + ". Provide them via --config."
        )


def _emit(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    else:
        print(obj)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_doctor(args) -> int:
    from .adapters import qmd as qmd_adapter

    cfg = load_or_find(args.config)
    report: dict = {
        "context_engine_version": __version__,
        "python": sys.version.split()[0],
    }

    # PyYAML
    try:
        import yaml  # noqa: F401
        report["pyyaml"] = "ok"
    except Exception as exc:  # pragma: no cover
        report["pyyaml"] = f"MISSING: {exc}"

    # Config
    report["config_source"] = args.config or "(discovered or defaults)"
    report["configured"] = cfg.is_configured()
    report["missing_paths"] = cfg.missing_paths()

    # Recall backend
    probe = qmd_adapter.probe(qmd=cfg.qmd)
    report["qmd_available"] = probe["available"]
    report["qmd_detail"] = probe["detail"]

    ok = report["pyyaml"] == "ok"
    if args.json:
        report["status"] = "ok" if ok else "degraded"
        _emit(report, True)
    else:
        print(f"context-engine {report['context_engine_version']}  (doctor)")
        print(f"  python            : {report['python']}")
        print(f"  PyYAML            : {report['pyyaml']}")
        print(f"  config source     : {report['config_source']}")
        print(f"  corpus configured : {report['configured']}"
              + ("" if report["configured"]
                 else f" (missing: {', '.join(report['missing_paths'])})"))
        print(f"  qmd backend       : "
              f"{'available' if probe['available'] else 'NOT available'}"
              f" — {probe['detail']}")
        print()
        print("  doctor status     : " + ("OK" if ok else "DEGRADED"))
        if not report["configured"]:
            print("  note: read-only commands work; mutating commands need a "
                  "configured corpus (--config).")
        if not probe["available"]:
            print("  note: install/point at qmd to enable live recall; packs and "
                  "tests work without it.")
    return 0 if ok else 1


def cmd_observe(args) -> int:
    from .core import cadence

    cfg = load_or_find(args.config)
    _need(cfg, "live_roots", "hot_root", "index_db", "manifests_dir")
    new = cadence.detect_readonly(cfg)
    rows = cadence.classify_new(cfg, new)
    seeded = sum(1 for r in rows if not r["aggressive"])
    queued = sum(1 for r in rows if r["aggressive"])
    out = {
        "new": len(new),
        "would_seed_near_lossless": seeded,
        "would_queue_aggressive": queued,
        "items": [{"path": r["path"], "archetype": r["archetype"],
                   "aggressive": r["aggressive"]} for r in rows],
    }
    if args.json:
        _emit(out, True)
    else:
        print(f"observe: {len(new)} new file(s) — "
              f"{seeded} near-lossless, {queued} aggressive")
        for r in rows:
            tag = "queue" if r["aggressive"] else "seed "
            print(f"  [{tag}] {r['archetype']:<20} {r['path']}")
    return 0


def cmd_delta(args) -> int:
    from .core import cadence

    cfg = load_or_find(args.config)
    _need(cfg, "live_roots", "hot_root", "index_db", "manifests_dir")
    new = cadence.detect_readonly(cfg)
    if args.json:
        _emit({"new": len(new), "items": new}, True)
    else:
        print(f"delta: {len(new)} unseen *.md")
        for f in new:
            print(f"  {f['sha256'][:16]}…  {f['path']}")
    return 0


def cmd_baseline(args) -> int:
    from .core import cadence

    cfg = load_or_find(args.config)
    _need(cfg, "live_roots", "hot_root", "index_db", "manifests_dir")
    if args.apply:
        require_configured(cfg)
    summary = cadence.baseline(cfg, apply=args.apply)
    mode = "APPLY" if args.apply else "DRY-RUN"
    if args.json:
        _emit({"mode": mode, **summary}, True)
    else:
        print(f"baseline {mode}: {summary['baselined']} file(s) "
              + ("recorded as seen" if args.apply else "would be recorded"))
    return 0


def cmd_cadence(args) -> int:
    from .core import cadence

    cfg = load_or_find(args.config)
    apply = bool(args.apply)
    # dry-run still scans the corpus, so it needs read paths
    _need(cfg, "org_root", "live_roots", "hot_root", "held_root",
          "index_db", "manifests_dir")
    if apply:
        require_configured(cfg)
    summary = cadence.run(cfg, apply=apply)
    mode = "APPLY" if apply else "DRY-RUN"
    if args.json:
        _emit({"mode": mode, **summary}, True)
    else:
        print(f"=== cadence {mode} ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    return 0


def cmd_pack(args) -> int:
    from .adapters import qmd as qmd_adapter
    from .packs.compiler import compile_pack
    from .packs.templates import ROLES

    cfg = load_or_find(args.config)
    if args.role not in ROLES:
        print(f"error: unknown role {args.role!r}; valid roles: {', '.join(ROLES)}",
              file=sys.stderr)
        return 2

    request = PackRequest(
        project=args.project, role=args.role, task=args.task,
        objective=args.objective or "", max_hot=args.max_hot, max_cold=args.max_cold)

    # If the recall backend is unavailable, compile from empty recall so packs
    # still render (against synthetic fixtures / offline) with a stated risk.
    probe = qmd_adapter.probe(qmd=cfg.qmd)
    if probe["available"]:
        markdown = compile_pack(request, config=cfg)
    else:
        request.risks.append(
            "Recall backend unavailable at compile time; hot/cold sections are "
            "empty. Re-run with a configured qmd backend for live retrieval.")
        markdown = compile_pack(
            request, config=cfg,
            recall_results={"hot": [], "cold": [], "tiers": [], "weak_hot": True})

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        print(f"wrote context pack -> {args.out}")
    else:
        sys.stdout.write(markdown)
    return 0


def cmd_audit(args) -> int:
    from .audit import hot_surface

    cfg = load_or_find(args.config)
    if args.target != "hot":
        print(f"error: unknown audit target {args.target!r}", file=sys.stderr)
        return 2
    _need(cfg, "hot_root")
    report = hot_surface.audit_hot(
        cfg.hot_root, domain_map=cfg.domain_map, oversize_bytes=cfg.oversize_bytes,
        export_prefixes=cfg.export_prefixes, generic_stems=cfg.generic_stems)
    if args.json:
        _emit(report, True)
    else:
        print(f"audit hot: {report['files']} artifact(s) — verdict "
              f"{report['verdict']}")
        for rule, n in sorted(report["findings_by_rule"].items()):
            print(f"  {n:>4}  {rule}")
    return 0 if report["verdict"] == "PASS" else 1


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--config", help="path to a context-engine.yml config")
    parent.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")

    ap = argparse.ArgumentParser(
        prog="context-engine",
        description="A governed agentic memory / context-control engine.")
    ap.add_argument("--version", action="version",
                    version=f"context-engine {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", parents=[parent],
                   help="report environment + backend availability"
                   ).set_defaults(func=cmd_doctor)
    sub.add_parser("observe", parents=[parent],
                   help="report new corpus files + classification preview"
                   ).set_defaults(func=cmd_observe)
    sub.add_parser("delta", parents=[parent],
                   help="report unseen *.md by sha256"
                   ).set_defaults(func=cmd_delta)

    p_base = sub.add_parser("baseline", parents=[parent],
                            help="record the current corpus as seen")
    p_base.add_argument("--apply", action="store_true",
                        help="write the cadence-seen ledger (default: dry-run)")
    p_base.set_defaults(func=cmd_baseline)

    p_cad = sub.add_parser("cadence", parents=[parent],
                           help="run the curation pipeline")
    grp = p_cad.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true",
                     help="report the plan without mutating (default)")
    grp.add_argument("--apply", action="store_true",
                     help="execute the plan and log every mutation")
    p_cad.set_defaults(func=cmd_cadence)

    p_pack = sub.add_parser("pack", parents=[parent],
                            help="compile a role-specific context pack")
    p_pack.add_argument("--project", required=True)
    p_pack.add_argument("--role", required=True,
                        help="orchestration | execution | verification | research | handoff")
    p_pack.add_argument("--task", required=True)
    p_pack.add_argument("--objective", default="")
    p_pack.add_argument("--max-hot", type=int, default=8, dest="max_hot")
    p_pack.add_argument("--max-cold", type=int, default=3, dest="max_cold")
    p_pack.add_argument("--out", help="write the pack to FILE (default: stdout)")
    p_pack.set_defaults(func=cmd_pack)

    p_audit = sub.add_parser("audit", parents=[parent],
                             help="read-only governance audit")
    p_audit.add_argument("target", choices=["hot"], help="audit target")
    p_audit.set_defaults(func=cmd_audit)

    return ap


def main(argv: Optional[list[str]] = None) -> int:
    # Packs and reports use UTF-8 (em dashes, bullets); keep stdout consistent
    # across platforms/consoles when output is piped or redirected.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        # e.g. a misconfigured index_db pointing at a non-sqlite file, or a bad
        # path_style — a user/config error, not a crash. Present it cleanly.
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
