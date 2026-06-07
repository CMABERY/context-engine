# Agent integration

This guide shows how agentic systems — Claude Code, Codex/other coding agents, and
multi-agent orchestrators — consume context packs instead of the raw corpus.

## The contract

1. The orchestrator (or a tool) compiles a **context pack** for a role + task.
2. The pack is injected into the agent's context (system/developer message, an
   attached file, or a tool result).
3. The agent acts **only** on the pack, honoring its exclusions and verification
   requirements.
4. If the pack is insufficient, the agent reports the gap; it does **not** read
   the raw corpus or fabricate.

This keeps the corpus out of agent contexts by default and makes every agent's
information diet auditable.

## Generating a pack

CLI (simplest — pipe or attach the markdown):

```bash
context-engine pack --project billing-service --role execution \
    --task "Implement the proration helper" --out pack.md
```

Library (inside an orchestrator):

```python
from context_engine.config import load_config
from context_engine.models import PackRequest
from context_engine.packs.compiler import compile_pack

cfg = load_config("context-engine.yml")
pack = compile_pack(PackRequest(
    project="billing-service", role="execution",
    task="Implement the proration helper"), config=cfg)
# inject `pack` into the agent's context
```

## Per-agent patterns

### Claude Code

* **As context:** write the pack to a file and reference it, or paste it into the
  task prompt. Use the `execution` role for a scoped coding task; the pack's
  *Exclusions* tell Claude not to wander into the wider repo/corpus.
* **As a tool:** expose `context-engine pack ...` (or `compile_pack`) as a tool so
  Claude can request a fresh pack mid-session when it hits a knowledge gap — using
  `research` (cold-admissible) when it needs origins, `execution` otherwise.
* **Verification step:** before Claude claims done, compile a `verification` pack
  for the same task; its cold evidence + sha256 link-backs let Claude check its
  output against sources.

### Codex / other coding agents

* Prepend the `execution` pack to the agent's instructions. The *Verification
  requirements* section becomes the agent's self-check list; the *Next action*
  becomes its objective.
* For agents that only accept a single prompt, the pack markdown *is* the prompt
  preamble — it is designed to be self-contained.

### Orchestration / multi-agent

* The **orchestrator** uses an `orchestration` pack (hot only) to plan and
  delegate. For each sub-task it spawns a worker with an `execution` pack scoped to
  that sub-task.
* A dedicated **verifier** agent gets a `verification` pack (hot + cold) and
  returns pass/fail with source hashes.
* On context handoff between sessions/agents, compile a `handoff` pack so the
  receiver resumes from durable, curated state rather than re-deriving it.

```
orchestrator (orchestration pack)
   ├─► worker A (execution pack, sub-task A)
   ├─► worker B (execution pack, sub-task B)
   └─► verifier (verification pack)  ──► pass/fail + sha256 citations
```

## Roles → when to use

| Situation | Role |
|---|---|
| Plan / break down work | `orchestration` |
| Do one well-scoped task | `execution` |
| Check claims against evidence | `verification` |
| Investigate an open question | `research` |
| Resume across a session boundary | `handoff` |

## Rules of engagement (give these to your agents)

* The pack is your world. Don't open the raw corpus unless the pack directs you to.
* Cite included hot artifacts; follow **sha256** (not paths) to reach sources.
* Respect *Exclusions*; satisfy *Verification requirements* before declaring done.
* On a missing fact: **stop and request a better pack**, don't guess.
* Secrets, credentials, and PII are never admissible — if you see them, stop and
  report.
