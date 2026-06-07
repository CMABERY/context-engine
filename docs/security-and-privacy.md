# Security & privacy

**The corpus this engine operates on is private. None of it belongs in this
repository.** This repo contains generic engine code, docs, examples, schemas,
tests, and adapters only. The rule is absolute:

> **No private corpus content — originals, hot/cold artifacts, transcripts, PII,
> provenance manifests, indexes, or backups — may ever be committed.**

## What must never be committed

* The corpus and its working trees: `_organized/`, `_hot/`, `_held/`, `_inbox/`,
  `transcripts/`, `projects/`, `archives/`, `corpus/`.
* Provenance: `_provenance/`, any `*.jsonl` manifest, `*.gate.json` sidecars.
* Indexes / databases: `*.sqlite` (and `-wal`/`-shm`).
* Captured backend output / samples containing real content.
* Backups and archives: `*.tar.gz`, `*.tgz`, `*.zip`, `*.bak`.
* Secrets: `.env`, `secrets/`, `*.pem`, `*.key`.

These are all blocked by [`.gitignore`](../.gitignore). **`.gitignore` is a
backstop, not the primary control** — the primary control is not putting corpus
content into the working tree in the first place.

## The leak surface is the code, not just files

When porting or extending the engine, the dangerous leaks are **inside code you
write**, not just stray data files:

* **No absolute corpus paths.** No `/mnt/c/...`, `C:\Users\...`, `/srv/...`
  literals. Paths come from `EngineConfig`; defaults are `None`.
* **No backend host details.** Binary paths, mount roots, and WSL specifics live
  in `qmd` config, never as literals.
* **No client / project / person identifiers.** Domain maps, id prefixes, and
  vocabularies are generic (`KB-`, `reference`, `decisions`). Don't bake a real
  client name, engagement code, or personal namespace into defaults.
* **No corpus specifics in docstrings or examples.** Generalize the prose; use
  synthetic, obviously-fake values in examples and tests.
* **No real captured output as fixtures.** Tests use tiny synthetic strings and
  injected runners — never real recall transcripts or exported chats.

## Fail-safe by design

* The engine ships **no** default config pointing at a real corpus. Every corpus
  path in `EngineConfig` defaults to `None`.
* `cadence --apply` and `baseline --apply` call `require_configured()` and
  **refuse to run** until every required corpus path is set.
* Read-only commands (`doctor`) work with defaults, so the tool is always
  inspectable without risking a corpus.
* The cadence is **dry-run by default**; mutation requires an explicit `--apply`.
* All mutations are append-only-logged and reversible.

## Verifying a clean repo

Before committing, sweep the whole tree for any corpus-specific token. This sweep
coming back empty is the verification evidence that the repo is clean. Build the
alternation from identifiers specific to *your* corpus — its root folder name,
your backend tool path, any client/project/person names, and your absolute path
roots:

```bash
# Replace the placeholders with YOUR corpus's real identifiers before running.
grep -rniE '<corpus-root-name>|<backend-tool>|<client-or-project>|<abs-path-root>' \
  --include='*.py' --include='*.md' --include='*.yml' --include='*.toml' \
  src tests docs examples README.md pyproject.toml
```

Expected result: **no matches**. Keep the real identifiers in your shell history /
local notes only — do not hard-code them into this doc, or you reintroduce the
very leak the sweep is meant to catch.

### Standing CI gate

`.github/workflows/ci.yml` runs this sweep on every push/PR as a **blocking
privacy gate**. It checks a generic baseline (private keys, AWS keys, real
`/home`, `/Users`, and `C:\Users` paths) over `src`, `tests`, `examples`,
`README.md`, and `pyproject.toml`. Because `grep` exits 0 on a match, the gate is
wired so a hit **fails** the build.

To extend the gate with identifiers specific to *your* corpus **without putting
them in the repo**, set a repository variable `PRIVACY_TOKENS` (a `grep -E`
alternation, e.g. `mycorp|acme-client|/srv/data`); CI folds it into the pattern at
run time. The real tokens live in the CI settings, never in tracked files.

## If you find corpus content in the repo

1. Do **not** commit. If already committed, treat it as a leak: purge it from
   history (`git filter-repo` / BFG) and rotate anything exposed.
2. Add or tighten a `.gitignore` pattern so it can't recur.
3. Trace how it got in (a fixture? a default path? a docstring?) and fix the
   source, not just the symptom.

## Reporting

If you discover a vulnerability or an inadvertent disclosure, do not open a public
issue with the sensitive content. Contact the maintainers privately and include
only what is necessary to reproduce.
