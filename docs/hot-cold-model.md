# The hot / cold model

The engine splits memory into two tiers with different jobs. Keeping them
distinct is what makes recall both *high-signal* and *lossless*.

## Hot layer — curated operational memory

The hot layer is the small, distilled, gated surface agents read from by default.

* **Contents:** distilled artifacts that passed the promotion gate — decision
  records, governance prompts, protocols, reference notes.
* **Shape:** chunk-clean. Each H2/H3 section is one embed/rerank unit, kept under
  configurable size limits (default 850 est-tokens / 3600 chars per section).
* **Schema:** YAML frontmatter with an `id`, a `status`, a `type` that routes to a
  domain folder, and a `sources[]` array carrying at least one `sha256` link-back.
* **Recall:** typed vector search + rerank — high precision.
* **Organization:** `hot/<domain>/` where domain comes from the config
  `domain_map` (e.g. `decisions`, `governance`, `orchestration`, `reference`).

The hot layer is **operational**: it is what the system *believes and uses now*.

## Cold layer — preserved evidentiary memory

The cold layer is the large, untouched record that backs every hot claim.

* **Contents:** original documents, raw transcripts, superseded revisions,
  near-duplicate losers — moved here, never deleted (supersede-not-erase).
* **Recall:** BM25 / FTS keyword search — broad recall, lower precision.
* **Role:** the no-loss net. Aggressive distillation is *allowed to drop detail*
  precisely because the sha256-linked cold original preserves everything.

The cold layer is **evidentiary**: it is what the system *can prove*.

## Recall: both tiers, every time

A recall call queries **both** tiers and returns two labeled sections:

```
recall("query")
  ├─ hot  : vector + rerank   (primary, high-signal)
  └─ cold : BM25 / FTS        (always surfaced, deduped against hot, capped)
```

The reranker floor only *flags* weak hot hits (`weak_hot: true`); it never
suppresses cold. Cold hits whose path matches a hot hit are de-duplicated, and the
cold section is capped (default 5) to stay tight.

## When may an agent touch cold?

By default, **agents read hot only.** Cold access requires one of four reasons:

1. **Proof** — you must cite the exact evidence behind a claim.
2. **Exact source** — you need verbatim text, not a distilled summary.
3. **Verification** — you are checking a hot claim against its origin.
4. **Missing hot context** — the hot surface is incomplete for the task.

This is enforced at the *pack* level: `execution`, `orchestration`, and `handoff`
packs exclude cold; `verification` and `research` packs include it, with the
reason stated in the pack. See [context-packs](context-packs.md).

## Lifecycle of a document

```
new file (live root)
   │  observe (delta by sha256)
   ▼
classify ── aggressive? ──► distill queue ──► (human/agent writes faithful artifact)
   │ near-lossless                                        │
   ▼                                                      ▼
seed into inbox ─────────────────► gate (.gate.json) ◄────┘
                                      │ pass
                                      ▼
                            promote → hot/<domain>/         original stays COLD,
                                      │                       linked by sha256
                                      ▼
                            reindex (recall sees it)
```

Promotion moves the *artifact* into hot; the *source* remains cold and is linked
by sha256. Hot and cold are never the same bytes — they are two views with
different fidelity, joined by hash.
