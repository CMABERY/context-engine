# Cadence — the curation pipeline

The cadence is the engine's recurring curation run. It is **dry-run by default**;
`--apply` mutates and logs. Every mutation is append-only and reversible.

```bash
context-engine cadence --config ./context-engine.yml --dry-run   # plan only
context-engine cadence --config ./context-engine.yml --apply      # execute + log
```

## Stages

The orchestrator (`core/cadence.py`) runs these in order:

| # | Stage | Module | What it does |
|---|-------|--------|--------------|
| 0 | **layer0** | `core/layer0` | Lossless dedup of the corpus: delete byte-identical redundant copies, move true revision lineages cold. Runs first so later stages see the deduped tree. |
| 1 | **detect** | `core/provenance` + `core/delta` | Rebuild the provenance index from manifests, then return `*.md` whose sha256 is unseen. |
| 2 | **classify** | `core/classify` | Tag each new file with an archetype and an aggressive/near-lossless flag. |
| 3 | **route** | `core/distill_queue` / `core/seed` | Aggressive content → distill queue. Near-lossless content → seeded into the inbox. Each evaluated source is logged `cadence-seen`. |
| 4 | **gatecalc** | `core/gatecalc` + `core/noloss` | For each inbox artifact, resolve its source and write a `.gate.json` (coverage or faithfulness). |
| 5 | **promote** | `core/promote` + `core/chunk_lint` | Enforce four gates; on pass, move into `hot/<domain>/` and log. |
| 6 | **dedup_hot** | `core/neardup` | Cluster hot near-duplicates; **existing hot always wins**; move just-promoted losers cold. |
| 7 | **normalize** | `core/normalize` | Normalize hot frontmatter (id/status/distill) and repair encoding. |
| 8 | **reindex** | `adapters/qmd` | Refresh the recall index incrementally (a missing backend is reported, never fatal). |

## The two routes

The classifier splits new content into two fundamentally different treatments.

### Near-lossless (seed → gate on coverage)

For reference notes, decision logs, governance, code specs, finished reports —
content where almost every fact matters. The engine seeds the source nearly
verbatim into the inbox, then the gate requires **source-coverage ≥ the
archetype's floor** (e.g. 0.95 for reference notes) with **zero unexplained
dropped facts** (any missing fact must appear in the artifact's `## Stripping
Ledger`).

### Aggressive (queue → gate on faithfulness)

For exploratory chat — content that is mostly noise (thinking blocks, dead ends).
Source-coverage is meaningless here, so the engine **queues** the source for
out-of-band distillation. A human or agent writes a faithful artifact into the
inbox; the gate then requires **faithfulness ≥ floor** (every specific the
artifact asserts must appear in the source — no fabrication) plus a non-empty
Stripping Ledger. The sha256-linked cold original is the real no-loss guarantee.

```
classify
   ├── near-lossless ──► seed ──► .gate.json (coverage) ──► promote
   └── aggressive ─────► distill_queue ──► (faithful artifact) ──► .gate.json (faithfulness) ──► promote
```

## The four promotion gates

`promote` refuses to move an artifact into hot unless **all four** pass:

1. **chunk_lint** — no section-shape violations (recall-granularity guard).
2. **gate report** — a sibling `.gate.json` exists.
3. **no-loss** — coverage ≥ floor with zero unexplained drops (near-lossless) **or**
   faithfulness ≥ floor with a non-empty Stripping Ledger (aggressive).
4. **link-back** — a `sources[]` entry carries a sha256.

A failed gate raises a per-artifact error that is reported, never fatal to the run.

## Baseline

Before the first real cadence, run a baseline to mark the existing corpus as seen
without curating it, so future runs only act on *new* arrivals:

```bash
context-engine baseline --config ./context-engine.yml --apply
```

## Idempotence & reversibility

* Re-running cadence on an unchanged corpus is a no-op: the seen-set (index ∪ hot
  link-backs ∪ cadence-seen ledger) suppresses re-processing.
* Every mutation is logged with `reversible: true` and the reason; the move/delete
  history in the manifests is the audit trail.
* Dry-run (and the read-only `observe`/`delta`) performs **no** mutation of any
  configured path — the provenance index is built into a throwaway database, so
  the configured `index_db` is never touched, and the plan plus the planned
  reindex commands are reported without changing the corpus.
