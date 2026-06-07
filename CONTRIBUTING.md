# Contributing

Thanks for extending the context engine. This project values determinism,
reversibility, and — above all — **never committing private corpus content**
(see [docs/security-and-privacy.md](docs/security-and-privacy.md)).

## Dev setup

```bash
python -m venv .venv
. .venv/Scripts/activate        # Windows
# source .venv/bin/activate     # POSIX
python -m pip install -e ".[dev]"
```

Requires Python ≥ 3.10. The only runtime dependency is PyYAML; a recall backend
(`qmd`) is optional — the full test suite runs without it.

## The checks CI runs (run them locally before pushing)

```bash
ruff check src tests        # lint (blocking in CI)
pytest -q                   # tests — must stay green (blocking in CI)
mypy src                    # type check (advisory in CI)
```

Plus a **privacy gate** that fails the build on any secret, real host/home path,
or corpus-specific token in tracked source/tests/examples. Add identifiers
specific to *your* corpus via the `PRIVACY_TOKENS` repo variable — never hard-code
them here. See `.github/workflows/ci.yml`.

## Conventions

- **Tests are mandatory and synthetic.** Every change ships with tests that use
  tiny synthetic fixtures (`tests/conftest.py`). Never depend on a real corpus.
- **No corpus-specific identifiers in code, docstrings, examples, or tests.**
  Paths, names, and vocabularies come from `EngineConfig`; defaults are generic.
- **Mutations are append-only-logged and reversible.** New pipeline steps log to
  a manifest via `utils/manifests.append`.
- **Match the surrounding style.** Stdlib-first; dataclasses + argparse; keep
  functions small and pure where possible.

## Where to extend

| Want to add… | Touch |
|---|---|
| a pack role | `packs/templates.py` (`ROLE_SPECS`) |
| a classification/gating policy | `context-engine.yml` (config-driven) |
| a pipeline stage | a new module in `core/`, wired into `core/cadence.py` |
| a recall backend | `adapters/` — see the roadmap's v0.3 adapter-interface note |

## Pull requests

Keep PRs focused. Include tests, keep `ruff`/`pytest` green, and confirm the
privacy gate passes. Describe what changed and why.
