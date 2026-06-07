"""context-engine — a governed agentic memory / context-control system.

The engine implements the governed memory loop::

    observe -> classify -> retrieve -> distill/extract/preserve -> gate
            -> promote -> reindex -> compile context packs -> audit

Two memory tiers underpin it:

* **Hot layer**  — curated, distilled operational memory; the high-signal recall
  surface agents read from by default.
* **Cold layer** — preserved evidentiary memory (originals, transcripts); the
  no-loss net, reached only with a stated reason.

``sha256`` is the primary source-link authority; filesystem paths are only hints.

The public surface is intentionally small and stable; see the submodules for the
implementation of each loop stage.
"""

__version__ = "0.5.0"

__all__ = ["__version__"]
