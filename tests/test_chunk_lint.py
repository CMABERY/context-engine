from context_engine.core import chunk_lint


def test_clean_document_no_flags():
    text = "---\nid: KB-x\n---\n\n# Title\n\n## Section A\nshort body\n\n## Section B\nmore\n"
    assert chunk_lint.lint_text(text) == []


def test_missing_leading_heading():
    text = "# Title\n\nprose with no H2 before content that is real\n"
    flags = chunk_lint.lint_text(text)
    assert any(f["rule"] == "missing_leading_heading" for f in flags)


def test_oversized_section_flags_chars_and_tokens():
    big = "## Big\n" + ("x" * 4000) + "\n"
    flags = chunk_lint.lint_text(big)
    rules = {f["rule"] for f in flags}
    assert "over_chars" in rules
    assert "over_est_tokens" in rules


def test_custom_limits():
    text = "## S\n" + ("y" * 200) + "\n"
    assert chunk_lint.lint_text(text) == []
    flags = chunk_lint.lint_text(text, max_chars=50)
    assert any(f["rule"] == "over_chars" for f in flags)
