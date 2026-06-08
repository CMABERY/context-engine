"""Tests for the Phase B feed sink (``context_engine.core.ingest``).

Every test uses ``tmp_path`` and tiny synthetic records — never a real corpus,
host path, or secret. The DP1 test asserts the *source* of the new module imports
nothing from ``controlplane``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_engine.core import ingest as ingest_mod
from context_engine.core import provenance
from context_engine.utils import hashing


def _manifest_rows(manifest_path: str) -> list[dict]:
    with open(manifest_path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _read_doc(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _record(**over):
    """A synthetic fed record. ``sha256`` is a real hash of synthetic 'authoritative'
    bytes so the link is well-formed; no host path or secret appears anywhere."""
    base = dict(
        kind="ACCEPTANCE",
        work_unit_id="wu-2026-06-07-demo",
        source_ref="substrate://state/acceptance-ledger#wu-2026-06-07-demo",
        summary="O accepted batch 1; gate green.",
        sha256=hashing.sha256_text("authoritative-record-bytes-v1"),
        produced_at="2026-06-07T12:00:00Z",
        emitted_by="orchestration",
        freshness="FRESH",
        custody_note="emitted after a successful commit",
    )
    base.update(over)
    return base


def _provenance(tmp_path, **over):
    kwargs = dict(
        cold_root=str(tmp_path / "_cold" / "ingested"),
        manifest_path=str(tmp_path / "_provenance" / "m.jsonl"),
        received_from="bridge.BridgeContextPort",
        received_at="2026-06-07T12:00:01Z",
    )
    kwargs.update(over)
    return ingest_mod.IngestProvenance(**kwargs)


# --------------------------------------------------------------------------- #
# round-trip: stored cold + manifest row appended + sha256 link present
# --------------------------------------------------------------------------- #

def test_roundtrip_cold_evidence_and_manifest(tmp_path):
    prov = _provenance(tmp_path)
    rec = _record()

    receipts = ingest_mod.ingest([rec], provenance=prov)
    assert len(receipts) == 1
    r = receipts[0]

    # cold evidence file exists and round-trips
    assert Path(r.cold_path).is_file()
    doc = _read_doc(r.cold_path)
    assert doc["kind"] == "ACCEPTANCE"
    assert doc["work_unit_id"] == "wu-2026-06-07-demo"
    assert doc["summary"] == rec["summary"]

    # exactly one append-only manifest row, op="ingest", reversible
    rows = _manifest_rows(prov.manifest_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["op"] == "ingest"
    assert row["stage"] == "ingest"
    assert row["reversible"] is True
    assert row["dst_abs"] == r.cold_path

    # sha256 LINK to the substrate authoritative record is present, in sources[]
    assert doc["sources"][0]["sha256"] == rec["sha256"].upper()
    assert doc["sources"][0]["role"] == "substrate-authoritative-record"
    assert r.link_sha256 == rec["sha256"].upper()


def test_manifest_sha_is_stored_bytes_not_the_substrate_link(tmp_path):
    """Pins the design choice: the manifest row's sha256 is the hash of the bytes it
    points at (so the index never lies); the cross-repo link lives in sources[]."""
    prov = _provenance(tmp_path)
    rec = _record()

    r = ingest_mod.ingest([rec], provenance=prov)[0]
    row = _manifest_rows(prov.manifest_path)[0]

    # manifest sha == the cold file's OWN content hash
    assert row["sha256"] == hashing.sha256_file(r.cold_path)
    assert row["sha256"] == r.evidence_sha256
    # ... and is NOT the substrate link hash (they are different bytes)
    assert row["sha256"] != r.link_sha256
    assert row["size_bytes"] == Path(r.cold_path).stat().st_size


# --------------------------------------------------------------------------- #
# recallable but advisory (recall via the existing provenance index)
# --------------------------------------------------------------------------- #

def test_recall_via_provenance_index_is_cold_and_advisory(tmp_path):
    prov = _provenance(tmp_path)
    r = ingest_mod.ingest([_record()], provenance=prov)[0]

    # build the disposable index over the manifest dir; classify the cold root cold
    manifests_dir = str(Path(prov.manifest_path).parent)
    db = str(tmp_path / "INDEX.sqlite")
    provenance.build(manifests_dir, db, [(prov.cold_root, "cold")])

    resolved = provenance.resolve(db, r.evidence_sha256)
    assert resolved["current"] is True
    assert resolved["tier"] == "cold"
    assert resolved["path"] == r.cold_path

    # advisory marker travels with the recalled evidence; it is never a truth source
    doc = _read_doc(resolved["path"])
    assert doc["advisory"] is True
    assert doc["is_truth_source"] is False


def test_advisory_not_truth(tmp_path):
    prov = _provenance(tmp_path)
    r = ingest_mod.ingest([_record()], provenance=prov)[0]
    doc = _read_doc(r.cold_path)
    assert doc["advisory"] is True
    assert doc["is_truth_source"] is False
    assert r.advisory is True
    # default custody note states the advisory contract in-band when none is fed
    bare = ingest_mod.ingest([_record(custody_note="")], provenance=_provenance(tmp_path))[0]
    assert "never a truth source" in _read_doc(bare.cold_path)["custody_note"]


# --------------------------------------------------------------------------- #
# append-only + idempotency semantics
# --------------------------------------------------------------------------- #

def test_append_distinct_records_then_idempotent_replay(tmp_path):
    prov = _provenance(tmp_path)
    rec_a = _record(work_unit_id="wu-a")
    rec_b = _record(work_unit_id="wu-b", summary="a different decision")

    # two distinct records -> two files, two appended rows
    ra, rb = ingest_mod.ingest([rec_a, rec_b], provenance=prov)
    assert ra.duplicate is False and rb.duplicate is False
    assert ra.cold_path != rb.cold_path
    assert len(_manifest_rows(prov.manifest_path)) == 2

    # re-ingesting an identical record is a no-op: no new file, no new row
    again = ingest_mod.ingest([rec_a], provenance=prov)[0]
    assert again.duplicate is True
    assert again.cold_path == ra.cold_path
    assert len(_manifest_rows(prov.manifest_path)) == 2  # unchanged
    assert len(list(Path(prov.cold_root).glob("*.json"))) == 2


def test_freshness_stored_as_fed_not_coerced(tmp_path):
    # The engine emits a faithful copy: even an empty produced_at with FRESH is
    # stored verbatim (invariant #5 enforcement is the substrate's job, not here).
    prov = _provenance(tmp_path)
    r = ingest_mod.ingest(
        [_record(produced_at="", freshness="FRESH")], provenance=prov)[0]
    assert _read_doc(r.cold_path)["freshness"] == "FRESH"


# --------------------------------------------------------------------------- #
# reversibility (demonstrated from the manifest row alone)
# --------------------------------------------------------------------------- #

def test_reversible_from_manifest_row(tmp_path):
    prov = _provenance(tmp_path)
    r = ingest_mod.ingest([_record()], provenance=prov)[0]

    row = _manifest_rows(prov.manifest_path)[0]
    assert row["reversible"] is True
    # the row alone carries enough to reverse: the dst path + the content hash
    assert row["dst_abs"] == r.cold_path
    assert row["sha256"] == hashing.sha256_file(r.cold_path)

    # reverse using only the row's data; the append-only history is retained
    Path(row["dst_abs"]).unlink()
    assert not Path(r.cold_path).exists()
    assert len(_manifest_rows(prov.manifest_path)) == 1  # log is append-only truth

    # the index now reflects the reversal (no current copy for that hash)
    db = str(tmp_path / "INDEX.sqlite")
    provenance.build(str(Path(prov.manifest_path).parent), db)
    assert provenance.resolve(db, r.evidence_sha256)["current"] is False


def test_ingest_rows_always_reversible_and_no_caller_knob(tmp_path):
    """AC5(c): reversibility is a STRUCTURAL invariant, not a caller-settable option.

    Both row types an ingest can emit -- op="ingest" (cold) and "ingest-hot-candidate"
    -- are always logged reversible:true, and IngestProvenance exposes no ``reversible``
    field a caller could flip to emit a non-reversible op="ingest" row.
    """
    from dataclasses import fields

    # no public knob: the field is gone, so the invariant cannot be overridden ...
    assert "reversible" not in {f.name for f in fields(ingest_mod.IngestProvenance)}
    # ... and constructing IngestProvenance with reversible=... is a hard TypeError
    with pytest.raises(TypeError):
        ingest_mod.IngestProvenance(
            cold_root=str(tmp_path / "_cold"),
            manifest_path=str(tmp_path / "_provenance" / "m.jsonl"),
            reversible=False)

    # exercise BOTH sinks: cold row + the optional ungated hot-candidate row
    prov = _provenance(tmp_path, hot_candidate_root=str(tmp_path / "_hot_candidates"))
    ingest_mod.ingest([_record()], provenance=prov)
    rows = _manifest_rows(prov.manifest_path)
    ops = {row["op"] for row in rows}
    assert {"ingest", "ingest-hot-candidate"} <= ops
    for row in rows:
        if row["op"] in ("ingest", "ingest-hot-candidate"):
            assert row["reversible"] is True


# --------------------------------------------------------------------------- #
# DP1: the new module imports nothing from controlplane
# --------------------------------------------------------------------------- #

def test_dp1_no_controlplane_import_in_module_source():
    src = Path(ingest_mod.__file__).read_text(encoding="utf-8")
    assert "controlplane" not in src
    # records cross the boundary as an engine-native type
    assert ingest_mod.FeedEvidence.__module__.startswith("context_engine")


def test_from_mapping_accepts_plain_dict_ignoring_unknown_keys():
    # The DP1-safe ingress: a plain dict (e.g. a model dump with extra keys) becomes
    # an engine-native record without importing any substrate type.
    rec = ingest_mod.FeedEvidence.from_mapping(
        {**_record(), "extra_substrate_only_key": "ignored", "_meta": 1})
    assert isinstance(rec, ingest_mod.FeedEvidence)
    assert rec.kind == "ACCEPTANCE"


def test_missing_or_invalid_link_sha_raises(tmp_path):
    prov = _provenance(tmp_path)
    # absent or non-hex link: rejected (the old ^[0-9a-fA-F]+$ caught these too)
    with pytest.raises(ingest_mod.IngestError):
        ingest_mod.ingest([_record(sha256="")], provenance=prov)
    with pytest.raises(ingest_mod.IngestError):
        ingest_mod.ingest([_record(sha256="not-hex!!")], provenance=prov)
    # AC5(d): hex-but-not-a-real-sha256 must be rejected. These are valid hex and so
    # PASSED the old loose regex, but the load-bearing cross-repo link must be a full
    # 64-char sha256 — too-short (and off-by-one-length) values are now rejected.
    for bad in ("abc123", "ABC123", "a" * 63, "f" * 65):
        with pytest.raises(ingest_mod.IngestError):
            ingest_mod.ingest([_record(sha256=bad)], provenance=prov)


# --------------------------------------------------------------------------- #
# public import surface (the path Phase C imports)
# --------------------------------------------------------------------------- #

def test_public_import_surface():
    import context_engine

    assert callable(context_engine.ingest)
    for name in ("FeedEvidence", "IngestProvenance", "IngestReceipt", "IngestError"):
        assert hasattr(context_engine, name)


# --------------------------------------------------------------------------- #
# optional hot candidate (ungated, advisory staging — never a trusted domain)
# --------------------------------------------------------------------------- #

def test_no_hot_candidate_by_default(tmp_path):
    r = ingest_mod.ingest([_record()], provenance=_provenance(tmp_path))[0]
    assert r.hot_candidate_path is None


def test_optional_hot_candidate_is_ungated_and_advisory(tmp_path):
    import yaml

    candidates = tmp_path / "_hot_candidates"   # NOT a trusted hot/<domain> folder
    prov = _provenance(tmp_path, hot_candidate_root=str(candidates))
    r = ingest_mod.ingest([_record()], provenance=prov)[0]

    assert r.hot_candidate_path is not None
    text = Path(r.hot_candidate_path).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fm = yaml.safe_load(text[4:text.find("\n---\n", 4)])
    # sha256 link-back to the substrate record is present in the candidate too
    assert fm["sources"][0]["sha256"] == r.link_sha256
    # an ungated candidate: status is draft (never 'seeded'/'stable'/promoted)
    assert fm["status"] == "draft"

    # it is logged separately and is NOT in any trusted domain folder
    ops = {row["op"] for row in _manifest_rows(prov.manifest_path)}
    assert "ingest-hot-candidate" in ops
    assert str(candidates) in r.hot_candidate_path
