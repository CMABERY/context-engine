"""Deterministic archetype classifier keyed on mechanical signals.

An ordered, first-match-wins cascade over structural markers in the text.
Governance/code signals are checked BEFORE chat markers so ambiguous cases bias
toward verbatim-preserve — over-distilling governance or code is the costliest
failure mode, so the classifier is conservative there.

Archetypes drive downstream routing: aggressive archetypes (chat) go to the
distill queue and gate on *faithfulness*; near-lossless archetypes are seeded
and gate on *source-coverage*.
"""
from __future__ import annotations

import re
from enum import Enum


class Archetype(Enum):
    EXPLORATORY_CHAT = "exploratory_chat"
    WRAPPED_DELIVERABLE = "wrapped_deliverable"
    REFERENCE_NOTE = "reference_note"
    GOVERNANCE_PROMPT = "governance_prompt"
    CODE_SPEC = "code_spec"
    DECISION_LOG = "decision_log"
    FINISHED_REPORT = "finished_report"
    EVAL_BUNDLE = "eval_bundle"


_RESPONSE_RE = re.compile(r"^##\s*Response", re.MULTILINE)
_PROMPT_RE = re.compile(r"^##\s*Prompt", re.MULTILINE)
_XML_TURN_RE = re.compile(r"<turn\b", re.IGNORECASE)
_TOC_RE = re.compile(r"^#{1,3}\s+(table of contents|contents)\b",
                     re.IGNORECASE | re.MULTILINE)
_READING_ORDER_RE = re.compile(r"^#{1,3}\s*reading order\b",
                               re.IGNORECASE | re.MULTILINE)
_AUDIT_RE = re.compile(r"\baudit trail\b", re.IGNORECASE)
_DECISION_HDR_RE = re.compile(r"^#{1,3}\s*decision\s+\d+",
                              re.IGNORECASE | re.MULTILINE)
_EVAL_RE = re.compile(
    r"\b(eval(uation)? (harness|bundle)|runbook bundle|test matrix)\b",
    re.IGNORECASE)

# Magic token marking a verbatim-preserve system/governance prompt. Configurable
# via classify_text(governance_token=...) for corpora using a different sentinel.
DEFAULT_GOVERNANCE_TOKEN = "SYSTEM_PROMPT"


def classify_text(text: str, *, governance_token: str = DEFAULT_GOVERNANCE_TOKEN) -> Archetype:
    """Classify markdown ``text`` into an :class:`Archetype`."""
    # 1. Governance / system-prompt — VERBATIM-PRESERVE. Checked first.
    if governance_token and governance_token in text:
        return Archetype.GOVERNANCE_PROMPT

    # 2. Code-heavy / decision-algebra spec — VERBATIM-PRESERVE. XML <turn>.
    if _XML_TURN_RE.search(text):
        return Archetype.CODE_SPEC

    # 3. Decision log — reading-order + audit, or numbered Decision headers.
    if (_READING_ORDER_RE.search(text) and _AUDIT_RE.search(text)) \
            or _DECISION_HDR_RE.search(text):
        return Archetype.DECISION_LOG

    # 4. Evaluation / runbook bundle — keep whole.
    if _EVAL_RE.search(text):
        return Archetype.EVAL_BUNDLE

    # 5. Chat transcript — disambiguate EXPLORATORY vs WRAPPED.
    n_resp = len(_RESPONSE_RE.findall(text))
    n_prompt = len(_PROMPT_RE.findall(text))
    if n_resp >= 1:
        if n_resp == 1 and n_prompt <= 1:
            return Archetype.WRAPPED_DELIVERABLE
        return Archetype.EXPLORATORY_CHAT

    # 6. No chat markers: clean TOC => FINISHED_REPORT, else REFERENCE_NOTE.
    if _TOC_RE.search(text):
        return Archetype.FINISHED_REPORT
    return Archetype.REFERENCE_NOTE


def classify(path: str, *, governance_token: str = DEFAULT_GOVERNANCE_TOKEN) -> Archetype:
    """Classify the markdown file at ``path``."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return classify_text(text, governance_token=governance_token)
