from context_engine.core import noloss


def test_gate_full_coverage():
    source = "We DECIDED to spend $500 on 12/31/2024."
    artifact = "Summary: we DECIDED to spend $500 on 12/31/2024."
    r = noloss.gate(source, artifact)
    assert r["coverage"] == 1.0
    assert r["missing"] == []


def test_gate_reports_missing():
    source = "Budget is $500 and the codename is PROJECTX."
    artifact = "We discussed the budget briefly."
    r = noloss.gate(source, artifact)
    assert r["coverage"] < 1.0
    assert any("$500" in m or "PROJECTX" in m for m in r["missing"])


def test_gate_empty_source_is_full():
    assert noloss.gate("", "anything")["coverage"] == 1.0


def test_faithfulness_catches_fabrication():
    source = "We spent $500."
    artifact = "We spent $500 and also $999."
    r = noloss.faithfulness(source, artifact)
    assert "$999" in r["unsupported"]
    assert r["score"] < 1.0


def test_faithfulness_clean():
    source = "We spent $500 on PROJECTX."
    artifact = "Spent $500 on PROJECTX."
    assert noloss.faithfulness(source, artifact)["score"] == 1.0
