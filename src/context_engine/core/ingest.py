"""Phase B feed sink: ingest external feed records as advisory cold evidence.

The orchestration plane (the substrate control-plane) emits durable outputs —
acceptances, decisions, handoffs, overrules, outcomes — and *feeds* them to the
engine so the memory loop closes: the engine remembers what it was told, not only
what it curated. This module is that sink.

What :func:`ingest` guarantees:

* **Engine-native boundary (DP1).** Fed records cross into the engine as plain
  data — a :class:`FeedEvidence`, or any mapping carrying its fields. This module
  imports **nothing** from the substrate control-plane package; the two cores meet
  only in the bridge (Phase C). The cross-repo link is carried by *hash string*,
  never by importing a substrate type.
* **Cold evidence, append-only.** Each record is written once as an immutable JSON
  evidence document under a cold root and logged with exactly one
  :func:`context_engine.utils.manifests.append` row (``op="ingest"``,
  ``reversible=True``). Manifests are the truth; the action is reversible and
  auditable from the row, exactly like every other mutation the engine logs.
* **sha256 link-back.** The evidence document carries a ``sources[]`` entry whose
  ``sha256`` is the substrate authoritative record's content hash — the same
  hot->cold link-back idiom used elsewhere (see :mod:`context_engine.core.seed`).
  The manifest row's own ``sha256`` is the hash of the *stored bytes*, so the
  provenance index never lies about what it points at.
* **Advisory, never truth.** Every document is flagged ``advisory: true`` /
  ``is_truth_source: false``. Ingested memory is recallable, but it is a
  provenance-bearing *copy* of an authoritative record that lives elsewhere — it
  can inform, it can never certify. (Acceptance / proof-blocking is the substrate's
  and bridge's job, not this sink's.)
* **Idempotent.** The evidence document is a pure function of the record and is
  named by its own content hash; re-ingesting an identical record is a no-op.

An *optional* ungated **hot candidate** may be emitted to a dedicated advisory
staging area (``IngestProvenance.hot_candidate_root``) — never a trusted
``hot/<domain>`` folder, never auto-promoted. It is off by default.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from typing import Any, Optional

from ..utils import hashing, manifests

# Schema tag stamped into every stored evidence document so a future reader can
# detect and migrate the shape.
EVIDENCE_SCHEMA = "context-engine/feed-evidence@1"
STAGE = "ingest"

# Stated in-band so a reader of the cold file alone still knows what it is.
DEFAULT_CUSTODY_NOTE = (
    "advisory copy of a substrate-authoritative record; recallable for context, "
    "never a truth source"
)

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

# Required identity/link fields a record must carry to be storable.
_REQUIRED = ("kind", "work_unit_id", "source_ref", "sha256")


class IngestError(ValueError):
    """Raised when a fed record cannot be stored as a valid cold-evidence link."""


@dataclass(frozen=True)
class FeedEvidence:
    """An engine-native fed record (mirrors the substrate feed payload).

    Deliberately a context-engine-local type: the engine never imports the
    substrate control-plane package to name what it ingests. The bridge (Phase C)
    converts the substrate's feed-record into one of these — or into a plain
    mapping — before handing it across, keeping the two cores decoupled (DP1).
    """

    kind: str
    work_unit_id: str
    source_ref: str
    summary: str
    sha256: str
    produced_at: str = ""
    emitted_by: str = ""
    freshness: str = ""
    custody_note: str = ""

    @classmethod
    def from_mapping(cls, data: "FeedEvidence | Mapping[str, Any]") -> "FeedEvidence":
        """Build from a :class:`FeedEvidence` or any mapping with its fields.

        Unknown keys are ignored, so the bridge may pass a plain ``dict`` (e.g. a
        model dump that carries extra keys) across the boundary without the engine
        importing the substrate's record type.
        """
        if isinstance(data, FeedEvidence):
            return data
        if not isinstance(data, Mapping):
            raise IngestError(
                f"feed record must be a FeedEvidence or mapping, got "
                f"{type(data).__name__}")
        known = {f.name for f in fields(cls)}
        kwargs = {k: data[k] for k in known if k in data}
        try:
            return cls(**kwargs)
        except TypeError as exc:  # missing a required positional field
            raise IngestError(f"feed record is missing required field(s): {exc}") from exc


@dataclass
class IngestProvenance:
    """Where an ingest is recorded and the custody metadata of the feed act.

    Bundling the destinations here keeps the public signature exactly
    ``ingest(records, *, provenance)`` while still reusing the engine's existing
    append-only manifest model.

    Fields:

    * ``cold_root`` — directory the immutable cold-evidence documents are written to.
    * ``manifest_path`` — the append-only provenance manifest every write is logged to.
    * ``hot_candidate_root`` — OPTIONAL advisory staging directory for an ungated hot
      *candidate*. It MUST NOT be a trusted ``hot/<domain>`` folder and the candidate
      is never auto-promoted. ``None`` (default) means cold-only.
    * ``received_from`` / ``received_at`` — custody metadata for the feed act, recorded
      on the manifest row and receipt only (kept OUT of the hashed cold document so
      ingest stays idempotent — there is no implicit clock in the stored evidence).
    * ``path_style`` — manifest path formatting, passed straight through to the
      manifest writer. There is deliberately NO ``reversible`` knob here: every row
      this sink writes is logged ``reversible=True`` as a structural invariant of an
      append-only advisory sink (see :func:`ingest`), so a caller cannot emit a
      non-reversible ``op="ingest"`` row.
    """

    cold_root: str
    manifest_path: str
    hot_candidate_root: Optional[str] = None
    received_from: str = ""
    received_at: str = ""
    path_style: str = "native"


@dataclass
class IngestReceipt:
    """The result of ingesting one record (echoed back, never an acceptance)."""

    kind: str
    work_unit_id: str
    cold_path: str
    link_sha256: str       # the substrate authoritative record's hash (the link)
    evidence_sha256: str   # the stored cold document's own content hash
    advisory: bool = True
    duplicate: bool = False
    hot_candidate_path: Optional[str] = None


def ingest(
    records: Iterable["FeedEvidence | Mapping[str, Any]"],
    *,
    provenance: IngestProvenance,
) -> list[IngestReceipt]:
    """Store each fed record as advisory cold evidence; return one receipt apiece.

    Each record is written once as an immutable JSON document under
    ``provenance.cold_root`` and logged with a single append-only manifest row
    (``op="ingest"``, ``reversible=True``). The document carries a ``sources[]``
    sha256 link-back to the substrate authoritative record and is flagged advisory
    (never a truth source). Re-ingesting an identical record is a no-op.
    """
    receipts: list[IngestReceipt] = []
    for raw in records:
        rec = FeedEvidence.from_mapping(raw)
        receipts.append(_ingest_one(rec, provenance))
    return receipts


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #

def _ingest_one(rec: FeedEvidence, provenance: IngestProvenance) -> IngestReceipt:
    link_sha = _require_link_sha(rec)
    for name in _REQUIRED:
        if not str(getattr(rec, name)).strip():
            raise IngestError(
                f"feed record for work_unit {rec.work_unit_id!r} is missing "
                f"required field {name!r}")

    body = _evidence_bytes(rec, link_sha)
    evidence_sha = hashing.sha256_bytes(body)
    cold_path = os.path.join(provenance.cold_root, _filename(rec, evidence_sha, "json"))

    # Idempotent: identical content already on disk -> no rewrite, no new row.
    duplicate = (os.path.exists(cold_path)
                 and hashing.sha256_file(cold_path) == evidence_sha)
    if not duplicate:
        os.makedirs(provenance.cold_root, exist_ok=True)
        with open(cold_path, "wb") as fh:   # binary: stored bytes == hashed bytes
            fh.write(body)
        manifests.append(
            provenance.manifest_path, op="ingest",
            src_abs=None, dst_abs=cold_path,
            sha256=evidence_sha, size_bytes=len(body),
            reason=_reason(rec, link_sha, provenance),
            stage=STAGE, reversible=True,  # structural invariant, not caller-overridable
            path_style=provenance.path_style)

    hot_path: Optional[str] = None
    if provenance.hot_candidate_root:
        hot_path = _emit_hot_candidate(rec, link_sha, provenance)

    return IngestReceipt(
        kind=rec.kind, work_unit_id=rec.work_unit_id,
        cold_path=cold_path, link_sha256=link_sha, evidence_sha256=evidence_sha,
        advisory=True, duplicate=duplicate, hot_candidate_path=hot_path)


def _require_link_sha(rec: FeedEvidence) -> str:
    """Return the UPPERCASE substrate link hash, or raise if it is absent/invalid.

    This hash is the load-bearing cross-repo provenance join, so it must be a *real*
    sha256: exactly 64 hex characters. A short or otherwise non-sha256 value (which a
    looser ``^[0-9a-fA-F]+$`` would have waved through) is rejected.
    """
    sha = (rec.sha256 or "").strip()
    if not sha or not _SHA256_RE.match(sha):
        raise IngestError(
            f"feed record for work_unit {rec.work_unit_id!r} lacks a valid sha256 "
            f"link to its substrate authoritative record: a full 64-char hex sha256 "
            f"is required (got {rec.sha256!r})")
    return sha.upper()


def _evidence_document(rec: FeedEvidence, link_sha: str) -> dict[str, Any]:
    """A pure function of the record (no clock) so identical records are idempotent.

    ``freshness`` is stored exactly as fed — the engine emits a faithful *copy* and
    never 'corrects' an authoritative record it does not own.
    """
    return {
        "schema": EVIDENCE_SCHEMA,
        "advisory": True,
        "is_truth_source": False,
        "kind": rec.kind,
        "work_unit_id": rec.work_unit_id,
        "source_ref": rec.source_ref,
        "summary": rec.summary,
        "produced_at": rec.produced_at,
        "emitted_by": rec.emitted_by,
        "freshness": rec.freshness,
        "custody_note": rec.custody_note or DEFAULT_CUSTODY_NOTE,
        "sources": [
            {
                "sha256": link_sha,
                "ref": rec.source_ref,
                "role": "substrate-authoritative-record",
            }
        ],
    }


def _evidence_bytes(rec: FeedEvidence, link_sha: str) -> bytes:
    text = json.dumps(_evidence_document(rec, link_sha),
                      ensure_ascii=False, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def _filename(rec: FeedEvidence, content_sha: str, ext: str) -> str:
    kind = _safe(rec.kind) or "feed"
    work_unit = _safe(rec.work_unit_id) or "wu"
    return f"{kind}.{work_unit}.{content_sha[:16]}.{ext}"


def _safe(value: str, limit: int = 64) -> str:
    return _UNSAFE_RE.sub("_", str(value)).strip("._-")[:limit]


def _reason(rec: FeedEvidence, link_sha: str, provenance: IngestProvenance) -> str:
    bits = [f"advisory ingested feed evidence: kind={rec.kind}",
            f"work_unit={rec.work_unit_id}", f"link={link_sha}"]
    for label, value in (("emitted_by", rec.emitted_by),
                         ("received_from", provenance.received_from),
                         ("received_at", provenance.received_at),
                         ("freshness", rec.freshness)):
        if value:
            bits.append(f"{label}={value}")
    return "; ".join(bits)


def _emit_hot_candidate(rec: FeedEvidence, link_sha: str,
                        provenance: IngestProvenance) -> str:
    """Write an UNGATED, advisory hot *candidate* to the staging root and log it.

    Reuses :func:`context_engine.core.seed.build_artifact` for the frontmatter +
    ``sources[]`` sha link-back. ``status='draft'`` and the candidate never passes
    the promotion gate, so it can never become trusted operational memory here.
    """
    from . import seed  # lazy: keep `import context_engine` light and seed-free

    body = f"# {rec.kind}: {rec.work_unit_id}\n\n{rec.summary}\n"
    artifact = seed.build_artifact(
        body=body, sha256=link_sha, title=f"{rec.kind} {rec.work_unit_id}",
        src_path=rec.source_ref, artifact_type="reference-note",
        artifact_id=_safe(f"FEED-{rec.kind}-{rec.work_unit_id}").lower(),
        default_status="draft")
    data = (artifact if artifact.endswith("\n") else artifact + "\n").encode("utf-8")
    hot_sha = hashing.sha256_bytes(data)
    hot_path = os.path.join(provenance.hot_candidate_root or "",
                            _filename(rec, hot_sha, "md"))

    if not (os.path.exists(hot_path) and hashing.sha256_file(hot_path) == hot_sha):
        os.makedirs(provenance.hot_candidate_root or "", exist_ok=True)
        with open(hot_path, "wb") as fh:
            fh.write(data)
        manifests.append(
            provenance.manifest_path, op="ingest-hot-candidate",
            src_abs=None, dst_abs=hot_path, sha256=hot_sha, size_bytes=len(data),
            reason=(f"advisory UNGATED hot candidate: kind={rec.kind}; "
                    f"work_unit={rec.work_unit_id}; link={link_sha}; "
                    f"not promoted (never a truth source)"),
            stage=STAGE, reversible=True,  # structural invariant, not caller-overridable
            path_style=provenance.path_style)
    return hot_path
