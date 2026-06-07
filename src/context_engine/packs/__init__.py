"""Context-pack compiler.

A context pack is a role-specific, read-only projection of memory: the minimal,
governed slice of hot (and optionally cold) memory an agent needs for one task.
Packs are the substrate's primary output — agents consume packs, not the raw
corpus.
"""
