# Connect Diagnostics Core — Final Documentation

This directory is the canonical reference for behavior that has been implemented, verified, and accepted.

Documentation is organized by business/module boundary:

- `docs/<module>/behavior.md` — module-wide invariants, ownership, shared semantics, and boundaries.
- `docs/<module>/<workflow>/README.md` — one accepted workflow or process.
- Large workflows may add `permissions.md`, `data-model.md`, `integration.md`, or `operations.md` when a separate stable reference is justified.

A workflow is documented here only after implementation, automated validation, independent review, and required Computer Use acceptance are complete. Working plans, blockers, review findings, test runs, screenshots, TODOs, branch status, and future design belong in `.github/tasks/`, not here.

## Modules

| Module | Canonical behavior |
| --- | --- |
| Accounting | [accounting/behavior.md](accounting/behavior.md) |
| Selling | [selling/behavior.md](selling/behavior.md) |
| Payroll | [payroll/behavior.md](payroll/behavior.md) |
| HR | [hr/behavior.md](hr/behavior.md) |
| Regulatory | [regulatory/behavior.md](regulatory/behavior.md) |
| DKSH | [dksh/behavior.md](dksh/behavior.md) |
| Print | [print/behavior.md](print/behavior.md) |
| Stock | [stock/behavior.md](stock/behavior.md) |

Active or paused implementation work remains under [`.github/tasks/`](../.github/tasks/).
