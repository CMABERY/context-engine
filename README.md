# context-engine

**A governed agentic memory / context-control engine.**

`context-engine` turns a sprawling, untrusted pile of documents into *governed
memory* an agent can safely act on. It curates a small, high-signal **hot** layer
out of a large **cold** evidentiary layer, links every artifact back to its
source by **sha256**, and compiles **role-specific context packs** — the minimal,
admissible slice of memory a given agent needs for a given task.

It is an **admissibility and compilation layer, not a truth source.** The engine
decides *what an agent is allowed to see and why*; your repo, tests, and commands
remain the operational authority.

> This project was extracted and generalized from a working reference
> implementation. It contains **generic engine code, docs, examples, schemas,
> tests, and adapters only** — never any private corpus content. See
> [security-and-privacy](docs/security-and-privacy.md).

---

## The governed memory loop

```
            ┌──────────────────────────── audit (read-only) ───────────────────────────┐
            │                                                                            │
   observe → classify → retrieve → distill / extract / preserve → gate → promote → reindex → compile context packs
      │          │          │                  │                    │        │          │              │
   new files  archetype   hot+cold          near-loss vs         no-loss   inbox →    refresh        role-specific
   (delta)    (mechanical) recall           aggressive split     check     hot/<dom>  recall index   memory projection
```

* **observe** — detect new corpus files by sha256 (`delta`); nothing seen twice.
* **classify** — a deterministic archetype classifier routes each file.
* **retrieve** — hot (typed vector + rerank) and cold (BM25/FTS) recall, always both.
* **distill / extract / preserve** — aggressive chat is queued for faithful
  distillation; near-lossless content is seeded verbatim.
* **gate** — a no-loss check (coverage for near-lossless, faithfulness for
  aggressive) must pass before anything enters hot memory.
* **promote** — gated artifacts move into a hot domain folder; every move is
  logged to an append-only provenance manifest.
* **reindex** — the recall index is refreshed incrementally.
* **compile context packs** — role-scoped projections of memory for agents.
* **audit** — a read-only governance pass over the hot surface.

## Two tiers + one authority

| | **Hot layer** | **Cold layer** |
|---|---|---|
| Purpose | curated **operational** memory | preserved **evidentiary** memory |
| Contents | distilled, gated, chunk-clean artifacts | originals, transcripts, superseded revisions |
| Recall | typed vector + rerank (high signal) | BM25 / FTS (keyword fallback) |
| Who reads it | agents, by default | only with a stated **reason** |

**`sha256` is the primary source-link authority; paths are only hints.** A moved
or renamed file still resolves by hash. Agents should not read the raw corpus by
default; cold access requires a reason — *proof, exact source, verification, or
missing hot context*.

## Install

```bash
python -m pip install -e ".[dev]"   # from a clone, into a venv
```

Requires Python ≥ 3.10. The only runtime dependency is **PyYAML**. A recall
backend (`qmd`) is optional — packs and the full test suite work without it.

## Quickstart

```bash
# 1. Inspect the environment (works with no config).
context-engine doctor

# 2. Copy and edit the example config to point at YOUR corpus.
cp examples/context-engine.yml ./context-engine.yml
#    ...edit paths...

# 3. See what would be ingested (read-only).
context-engine observe --config ./context-engine.yml
context-engine delta   --config ./context-engine.yml

# 4. Establish a baseline, then run the curation cadence (dry-run first!).
context-engine baseline --config ./context-engine.yml --apply
context-engine cadence  --config ./context-engine.yml --dry-run
context-engine cadence  --config ./context-engine.yml --apply

# 5. Compile a context pack for an agent.
context-engine pack --project billing-service --role execution \
    --task "Implement the proration helper" --out pack.md

# 6. Audit the hot surface (read-only).
context-engine audit hot --config ./context-engine.yml
```

See [examples/](examples/) for a fully-commented config and three real compiled
packs (orchestration / execution / verification).

## CLI

| Command | What it does | Mutates? |
|---|---|---|
| `doctor` | report environment + backend availability | no |
| `observe` | new files + classification preview | no (builds index) |
| `delta` | unseen `*.md` by sha256 | no (builds index) |
| `baseline [--apply]` | record current corpus as seen | with `--apply` |
| `cadence [--dry-run\|--apply]` | run the curation pipeline | with `--apply` |
| `pack --project --role --task` | compile a context pack | no |
| `audit hot` | read-only governance audit | no |

**Fail-safe:** the engine ships no default config pointing at a real corpus.
`cadence --apply` and `baseline --apply` refuse to run until every required
corpus path is configured.

## Repository layout

```
src/context_engine/
  cli.py            # the `context-engine` entrypoint
  config.py         # YAML load + validation + fail-safe gate
  models.py         # EngineConfig + generic defaults + data models
  core/             # classify, delta, gatecalc, noloss, promote, dedup,
                    #   neardup, normalize, seed, layer0, reindex, cadence,
                    #   provenance, chunk_lint, distill_queue
  adapters/qmd.py   # recall + reindex adapter (injectable runner)
  packs/            # context-pack compiler + role templates
  audit/            # read-only hot-surface audit
  utils/            # hashing, manifests, path normalization
docs/               # architecture, hot/cold, provenance, cadence, packs,
                    #   agent-integration, security, roadmap
examples/           # config + example packs
tests/              # unit + integration tests (synthetic fixtures only)
```

## Documentation

* [Architecture](docs/architecture.md) — components and data flow.
* [Hot/cold model](docs/hot-cold-model.md) — the two tiers and when to use each.
* [Provenance](docs/provenance.md) — sha256 authority, manifests, the index.
* [Cadence](docs/cadence.md) — the curation pipeline, stage by stage.
* [Context packs](docs/context-packs.md) — role-specific memory projections.
* [Agent integration](docs/agent-integration.md) — using packs from Claude Code,
  Codex, and orchestration agents.
* [Security & privacy](docs/security-and-privacy.md) — what must never be committed.
* [Roadmap](docs/roadmap.md) — v0.1 → v0.5.

## License

MIT.
