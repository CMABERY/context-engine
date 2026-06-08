# Provenance

Provenance is how the engine stays trustworthy: every artifact links back to its
origin, every mutation is logged, and the link survives moves and renames.

## sha256 is the authority; paths are hints

The engine identifies content by the **UPPERCASE hex sha256** of its bytes, never
by filename. A file that is moved, renamed, or copied keeps the same hash, so:

* the delta detector recognizes already-seen content even after reorganization;
* a hot artifact's `sources[].sha256` resolves to wherever the original now lives;
* duplicate and near-duplicate decisions are content-based, never name-based.

A stored path that no longer resolves is a stale *hint*, not a broken link — the
hash still identifies the content.

## Manifests are the truth

Every mutation appends exactly one JSON line to an append-only manifest. The
record schema:

```json
{
  "op": "promote",
  "src_abs": "/path/to/_hot/_inbox/note.md",
  "dst_abs": "/path/to/_hot/reference/note.md",
  "sha256": "3F9A1C77...",
  "size_bytes": 4096,
  "mtime_utc": "2026-06-07T12:00:00Z",
  "ts_utc": "2026-06-07T12:00:01Z",
  "stage": "promote",
  "reversible": true,
  "reason": "promoted REFERENCE_NOTE artifact (coverage=1.000>=0.95, 0 drops)"
}
```

Operations include `promote`, `move`, `delete`, `normalize`, `copy` (seed),
`cadence-seen` (the ledger that marks a source evaluated), and `ingest` (the feed
sink — see below). Because the log is append-only and every record is
`reversible`, the corpus history is fully auditable and any step can be undone.

### Ingested feed evidence (advisory)

`ingest` (`context_engine.ingest`) is the write-back sink: it stores records *fed*
to the engine by an upstream orchestrator as **advisory cold evidence** — a
provenance-bearing *copy* of an authoritative record that lives in another system,
never a truth source. Each ingest writes one immutable JSON document and appends
one `op="ingest"` manifest row (`reversible: true`), so it is append-only and
reversible exactly like any other mutation; re-ingesting an identical record is a
no-op. The document is flagged `advisory: true` / `is_truth_source: false` and
carries a `sources[].sha256` **link-back** to the upstream authoritative record —
the manifest row's own `sha256` is the hash of the stored bytes, so the index
never lies about what it points at, while the cross-system link travels in
`sources[]`. The fed records cross the boundary as engine-native data, so the
engine takes on **no dependency** on the upstream system.

### Path storage style

Paths are stored in a configurable convention (`path_style`):

* `native` (default) — the path as the current OS expresses it (best single-host);
* `posix` — `/mnt/<drive>/...` (portable to WSL/Linux readers);
* `windows` — `<DRIVE>:\...`.

The reader (`utils.paths.to_local`) translates a stored path to the current OS's
form for existence checks, so a manifest written under WSL is usable from Windows
and vice-versa.

## The provenance index

The sqlite index (`index_db`) is a **disposable projection** of the manifests,
rebuilt on demand by `provenance.build`:

```sql
files(sha256 TEXT, path TEXT, current INTEGER, tier TEXT)
```

* `sha256` — UPPERCASE, so old- and new-style records join.
* `current` — 1 if the stored path currently exists on disk.
* `tier` — assigned by config `tier_rules` (ordered `(substring, tier)` pairs;
  first match wins; default `live`). If no rules are given, tiers are derived from
  `hot_root`/`held_root`.

`provenance.resolve(db, sha)` returns every known path for a hash (current paths
first) plus its tier. `provenance.dangling_report` flags artifact sources that no
longer resolve and are not recoverable by basename.

**If the index is ever lost or corrupted, delete it and rebuild — the manifests
are authoritative.**

## Why this matters for agents

When a pack cites a hot artifact, the artifact in turn cites its cold source by
sha256. An agent that needs proof can follow the hash from pack → hot artifact →
cold original with certainty, even if files have moved since the pack was compiled.
