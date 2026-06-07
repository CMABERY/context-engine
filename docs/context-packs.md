# Context packs

A **context pack** is a role-specific, read-only projection of governed memory:
the minimal, admissible slice an agent needs for one task. Packs — not the raw
corpus — are the engine's primary output. Agents consume packs.

```bash
context-engine pack --project billing-service --role execution \
    --task "Implement the proration helper" --out pack.md
```

See [examples/](../examples/) for three real compiled packs.

## Why packs exist

Handing an agent the whole corpus is unsafe and ineffective: it leaks irrelevant
or sensitive material and drowns the signal. A pack instead:

* projects only what the **role** is allowed to see,
* states the **reason** cold evidence is or isn't included,
* records **exclusions, assumptions, risks, and verification requirements** up
  front, and
* ends with a concrete **next-action** prompt.

## Anatomy

Every pack has the same sections, in order:

| Section | Purpose |
|---|---|
| **Objective** | the goal the pack serves |
| **Role** | how this role should treat the memory |
| **Task** | the specific task |
| **Included hot artifacts** | curated hits (path, score, sha256 hint) |
| **Cold evidence** | originals — included only for roles with a reason |
| **Exclusions** | what is deliberately out of scope / inadmissible |
| **Assumptions** | standing assumptions recorded for the agent |
| **Risks** | known risks (e.g. weak recall) |
| **Verification requirements** | how the agent must check its work |
| **Next action** | the concrete prompt to act on |

## Roles

Roles encode the engine's governance principles as data (`packs/templates.py`):

| Role | Cold included? | Reason | Use it for |
|---|---|---|---|
| **orchestration** | no | plans from curated hot memory | planning, delegation |
| **execution** | no | works from the curated hot slice | doing one task |
| **verification** | **yes** | verification is a valid reason for cold | checking claims vs. evidence |
| **research** | **yes** | hot may be incomplete | open-ended investigation |
| **handoff** | no | carries curated state | resuming work |

The rule: **execution / orchestration / handoff get hot only; verification /
research get hot + cold.** This directly implements "agents don't read raw corpus
by default" and "cold access requires a reason."

## Compiling a pack

`compile_pack` (in `packs/compiler.py`) is a thin orchestration:

1. run recall for the task (hot always; cold for cold-admissible roles),
2. apply the role's caps (`max_hot`, `max_cold`) and admissibility,
3. render markdown via the pure `render_pack`.

```python
from context_engine.models import PackRequest
from context_engine.packs.compiler import compile_pack

req = PackRequest(project="billing-service", role="execution",
                  task="Implement the proration helper", max_hot=6)
markdown = compile_pack(req, config=cfg)            # runs live recall
```

### Testing packs without a backend

`render_pack` is pure and `compile_pack` accepts pre-fetched results, so packs are
fully testable offline:

```python
md = compile_pack(req, recall_results={
    "hot":  [{"path": "hot/reference/proration-spec.md", "score": 0.86,
              "sha256": "9911AA22"}],
    "cold": [],
    "weak_hot": False,
})
```

If the recall backend is unavailable at compile time, the CLI still renders a pack
(empty hot/cold) and records the gap as an explicit **risk** — never a silent
empty result.

## Reading a pack as an agent

* Treat **Included hot artifacts** as your working set; cite them.
* Honor **Exclusions** — they mark inadmissible material.
* Satisfy every **Verification requirement** before claiming done.
* If a required fact is missing, **stop and request it** rather than reading the
  raw corpus or guessing.
* Follow sha256 link-backs (not paths) when you need to reach a source.
