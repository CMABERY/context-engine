from context_engine.core.classify import Archetype, classify_text


def test_governance_prompt_first():
    assert classify_text("intro SYSTEM_PROMPT body") is Archetype.GOVERNANCE_PROMPT


def test_code_spec_xml_turn():
    assert classify_text("<turn id=1>code</turn>") is Archetype.CODE_SPEC


def test_decision_log_numbered_header():
    assert classify_text("## Decision 1\nwe chose X\n") is Archetype.DECISION_LOG


def test_eval_bundle():
    assert classify_text("This is an evaluation harness for the model.") \
        is Archetype.EVAL_BUNDLE


def test_exploratory_chat_multi_turn():
    text = "## Prompt\nq1\n## Response\na1\n## Prompt\nq2\n## Response\na2\n"
    assert classify_text(text) is Archetype.EXPLORATORY_CHAT


def test_wrapped_deliverable_single_response():
    text = "## Prompt\nmake X\n## Response\nhere is X\n"
    assert classify_text(text) is Archetype.WRAPPED_DELIVERABLE


def test_finished_report_with_toc():
    assert classify_text("# Title\n\n## Table of Contents\n- a\n") \
        is Archetype.FINISHED_REPORT


def test_reference_note_default():
    assert classify_text("# Note\n\nsome reference prose\n") \
        is Archetype.REFERENCE_NOTE


def test_custom_governance_token():
    assert classify_text("CONSTITUTION here",
                         governance_token="CONSTITUTION") is Archetype.GOVERNANCE_PROMPT
