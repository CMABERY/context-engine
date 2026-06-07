# Architecture

`context-engine` is organized as a set of small, single-purpose modules that each
implement one stage of the governed memory loop. Nothing in the engine embeds a
corpus location, drive letter, client name, or other corpus-specific identifier —
all of that arrives through `EngineConfig`.

## Layers

```
                       ┌─────────────────────────────────────────────┐
            CLI  ──────►  cli.py   (argparse; doctor/observe/delta/    │
                       │            baseline/cadence/pack/audit)       │
                       └───────────────┬─────────────────────────────┘
                                       │
            config.py ◄────────────────┤  loads + validates EngineConfig,
            models.py                  │  enforces the fail-safe gate
                                       │
        ┌──────────────────────────────┴──────────────────────────────┐
        │                          core/                                │
        │  cadence (orchestrator)                                       │
        │   ├─ layer0 ─ dedup            ├─ gatecalc ─ noloss           │
        │   ├─ delta                     ├─ promote ─ chunk_lint        │
        │   ├─ classify                  ├─ neardup                     │
        │   ├─ distill_queue / seed      ├─ normalize                   │
        │   └─ provenance                └─ reindex                     │
        └───────┬───────────────────────────────────┬──────────────────┘
                │                                     │
        adapters/qmd.py                        packs/   audit/
        (recall + reindex,                     (compiler,  (hot_surface,
         injectable runner)                     templates)  read-only)
                │
        utils/ (hashing, manifests, paths)  ◄── shared by everything
```

## Module responsibilities

### Foundation — `utils/`
* **hashing** — streamed `sha256` (UPPERCASE hex), duplicate scan.
* **manifests** — append-only JSONL provenance writer; one record per mutation.
* **paths** — cross-platform path normalization (Windows ↔ POSIX/WSL mounts).

### Configuration — `config.py`, `models.py`
* **models.EngineConfig** — every tunable, with generic defaults; corpus paths
  default to `None` so an unconfigured install fails safe.
* **config** — YAML load/validate, manifest-path resolution, and
  `require_configured()` — the gate mutating commands call.

### Core stages — `core/`
* **delta** — sha256 seen-set detection (index ∪ hot link-backs).
* **classify** — deterministic archetype cascade (governance/code first).
* **noloss** — fact extraction; coverage and faithfulness gates.
* **gatecalc** — resolves an inbox artifact's source, computes its `.gate.json`.
* **chunk_lint** — section-shape lint (recall-granularity guard).
* **promote** — four-gate enforcement: lint, gate report, no-loss, sha link-back.
* **dedup** / **layer0** — exact-duplicate + version-lineage cleanup.
* **neardup** — title-bucket + Jaccard near-duplicate clustering.
* **normalize** — frontmatter/id/status/encoding normalization.
* **seed** — the near-lossless artifact builder (frontmatter + sha link-back).
* **distill_queue** — out-of-band queue for aggressive distillation.
* **reindex** — backend-agnostic command executor (injectable runner).
* **provenance** — rebuildable sqlite index projected from the manifests.
* **cadence** — the orchestrator that wires the above into one pipeline.

### Adapters — `adapters/`
* **qmd** — hot (vector/rerank) + cold (BM25) recall and incremental reindex.
  The `runner` (argv → output) is injectable, so tests never need a live backend.

### Packs — `packs/`
* **templates** — `RoleSpec` per role (which tiers are admissible, framing,
  verification requirements, next-action).
* **compiler** — `render_pack` (pure) + `compile_pack` (recall → render).

### Audit — `audit/`
* **hot_surface** — read-only schema/structure/near-dup audit; never mutates.

## Data flow

1. **Detect.** `provenance.build` replays manifests into a sqlite index;
   `delta.new_files` returns `*.md` whose sha256 is in neither the index nor any
   hot artifact's `sources[]`.
2. **Classify & route.** Each new file is classified; aggressive content is
   queued, near-lossless content is seeded into the inbox.
3. **Gate & promote.** Each inbox artifact gets a `.gate.json`; `promote` enforces
   four gates, then moves it into `hot/<domain>/` and logs the move.
4. **Consolidate.** Near-duplicates are clustered (existing hot wins); frontmatter
   is normalized.
5. **Reindex.** The recall index is refreshed.
6. **Compile.** `pack` projects governed memory into a role-scoped markdown pack.
7. **Audit.** `audit hot` reports the surface's health, read-only.

Every mutating step appends a reversible record to a manifest. The sqlite index
is disposable — **the manifests are the truth.**

## Design principles

1. Hot = curated operational memory; cold = preserved evidentiary memory.
2. `sha256` is the source-link authority; paths are hints.
3. Context packs are role-specific projections of memory.
4. Agents do not read raw corpus by default.
5. Cold access requires a reason.
6. The engine is an admissibility/compilation layer, not the truth source.
7. Determinism and reversibility: pure functions where possible; every mutation
   logged and reversible.
8. No corpus-specific identifiers in code — everything generic and config-driven.
