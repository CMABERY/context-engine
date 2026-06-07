"""Read-only governance audits over the hot surface.

Audits never mutate the corpus. They report structural and schema health
(frontmatter validity, required provenance fields, chunk shape, titles, size,
near-duplication) so the operational authority stays the live repo/tests, with
the engine acting only as an admissibility and compilation layer.
"""
