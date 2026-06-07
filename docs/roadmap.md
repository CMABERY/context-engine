# Roadmap

The engine is built in milestones, each adding one capability layer. The current
release is **v0.5.0**; the milestones below describe the intended arc and what
each delivers.

## v0.1 — local QMD-backed context engine ✅

The foundation: a corpus-agnostic engine with the full curation cadence.

* sha256 hashing, append-only manifests, rebuildable provenance index.
* Delta detection (seen-set), deterministic archetype classification.
* No-loss gates (coverage + faithfulness), four-gate promotion, chunk lint.
* Layer-0 exact dedup, near-duplicate clustering, frontmatter normalization.
* qmd recall adapter (hot vector + cold BM25) with an injectable runner.
* `doctor` / `observe` / `delta` / `baseline` / `cadence` CLI; fail-safe config.

## v0.2 — context-pack compiler ✅

Turn governed memory into role-scoped projections agents consume.

* `render_pack` (pure) + `compile_pack`; five roles (orchestration, execution,
  verification, research, handoff) with admissibility rules.
* `pack` CLI; offline rendering with explicit recall-unavailable risk.

> v0.1 and v0.2 are implemented in this release.

## v0.3 — project adapters

Make the engine multi-project and pluggable.

* A `project-config` layer (see `examples/project-config.example.yml`) that pins
  per-project pack defaults, preferred domains, and standing exclusions.
* A loader + resolution order (engine config ← project config ← CLI flags).
* Adapter interface beyond qmd (e.g. a local-embeddings or SQLite-FTS adapter)
  selected by config, all behind the existing runner seam.
* Per-project provenance namespacing.

## v0.4 — feedback / evaluation loop

Close the loop so the engine learns whether its packs were good.

* Capture pack-usage outcomes (was the included context sufficient? what was
  missing?) as structured feedback.
* Recall evaluation harness: measure hot precision / cold recall against a
  labeled query set; track `weak_hot` rates.
* Gate-tuning reports: surface archetypes whose floors are too strict/loose.
* Re-distillation queue driven by audit findings (oversized / stale artifacts).

## v0.5 — multi-agent substrate routing

The engine as a shared memory substrate for fleets of agents.

* A routing layer that compiles and serves packs to many agents/roles
  concurrently, with per-agent admissibility policies.
* Handoff/continuity packs as first-class substrate objects across sessions.
* Concurrency-safe cadence (locking around index rebuild + promote).
* Optional service surface (HTTP/MCP) exposing `recall`, `pack`, and `audit`.

## Cross-cutting, ongoing

* **Privacy:** keep the codebase free of corpus-specific identifiers; the grep
  sweep in [security-and-privacy](security-and-privacy.md) stays green.
* **Determinism & reversibility:** pure functions where possible; every mutation
  logged and reversible.
* **Test coverage:** synthetic fixtures only; never depend on a private corpus.
