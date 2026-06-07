"""Retrieval/storage adapters.

An adapter bridges the engine to a concrete recall or indexing backend. The
reference adapter targets ``qmd`` (typed vector recall for hot, BM25/FTS for
cold), but every adapter exposes the same injectable ``runner`` seam so unit
tests never require the backend to be installed.
"""
