# Context Pack — billing-service / verification

> Role-specific projection of governed memory. sha256 is the source authority; paths are hints. Do not read the raw corpus unless this pack directs you to.

## Objective

Verify the implementation's claims against cold evidence by sha256.

## Role

You are verifying claims against evidence. Cold originals are included BECAUSE verification is a valid reason to open the cold layer.

## Task

Verify the proration helper matches the figures in the billing decision record

## Included hot artifacts (1)

- `hot/reference/proration-spec.md` — score 0.840 — sha256 `9911AA22BB33CC44…`

## Cold evidence (2)

- `cold/held/billing-design-thread.md` — score 0.710 — sha256 `CC55DD66EE77FF88…`
- `cold/transcripts/pricing-review-2025.md` — score 0.630 — sha256 `1234ABCD5678EF90…`

## Exclusions

- Material outside the cited sources (out of verification scope).

## Assumptions

- The cold originals are the authoritative no-loss record.

## Risks

_(none)_

## Verification requirements

- Check each hot artifact's assertions against the cold evidence by sha256 link-back, not by filename.
- Report any unsupported or contradicted claim with its source hash.
- Treat the cold original as authoritative where hot and cold disagree.

## Next action

Verify: Verify the proration helper matches the figures in the billing decision record. For each claim, cite the cold source (sha256) that supports or refutes it, and give a pass/fail verdict.
