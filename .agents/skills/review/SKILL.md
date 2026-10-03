---
name: review
description: Independently review a plan, local change set, pull request, or final documentation for correctness, security, regressions, lifecycle risks, and missing evidence.
---

# Independent Review Skill

Review against the original requirement and the repository policy. Do not approve work you implemented yourself.

## Plan review

Verify:

- bounded goal and acceptance criteria;
- file ownership and dependencies;
- real Frappe/ERPNext execution path;
- tests and final automated gates;
- migration/rollback impact;
- Computer Use coverage when user-visible behavior changes;
- final documentation impact.

Require decomposition when the scope cannot be owned or verified independently.

## Implementation review

Prioritize real defects over style:

- correctness and regression risk;
- permissions and security;
- Frappe document lifecycle and transaction semantics;
- data integrity, locking, idempotency, and concurrency;
- migration/backward-compatibility behavior;
- missing or weak tests.

## Documentation review

Compare final docs with accepted code, automated evidence, and Computer Use results. Reject stale, duplicate, speculative, future, task-status, or implementation-history content from `docs/`.

## Finding severity

- **P0** — catastrophic security, data-loss, or integrity defect.
- **P1** — must fix before acceptance/merge.
- **P2** — significant correctness or maintainability issue that needs explicit disposition.
- **P3** — minor issue.

For each finding include location, evidence, impact, and expected behavior. State explicitly when no meaningful findings remain.
