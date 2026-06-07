"""Core engine stages: classify, delta, gate, promote, dedup, normalize, cadence.

Every module here is corpus-agnostic and config-driven. None of them embed
absolute paths, drive letters, client names, or other corpus-specific
identifiers; those arrive via :class:`context_engine.models.EngineConfig`.
"""
