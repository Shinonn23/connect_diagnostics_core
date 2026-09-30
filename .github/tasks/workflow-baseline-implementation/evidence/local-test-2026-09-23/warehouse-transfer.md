# Warehouse Transfer approval evidence — local.test — 2026-09-23

## Delivered implementation

- One active Stock Entry Workflow scopes approval to direct Material Transfer and supplies native
  pass-through transitions for every other Stock Entry purpose and transit leg.
- The route is Stock User Send/Resubmit, Stock Manager Review, C-Level Approver Approve/Reject,
  and Stock Manager native Submit/Cancel.
- Review and Approve use the shared Employee-backed signed snapshot writer and shared distinct-actor
  guard. Return clears the current approval evidence.
- The server-side submit guard locks and rechecks the persisted approved state, current submit
  permission, distinct actors, required signatures, and a posting-critical digest immediately before
  ERPNext native posting. The cancel guard requires the native Workflow cancel transition.
- Fixture migration is additive, collision-aware, and preserves historical Workflow Actions. Its
  rollback helper is intentionally non-destructive; recovery uses the pre-migration site backup and
  native cancel/reversal for posted transactions.

## Migration and recovery evidence

- Preflight found one active owned workflow, `Connect Stock Transfer Approval`, and no open Stock Entry
  Workflow Actions. No unrelated active Stock Entry workflow collision was present.
- Backup completed before migration:
  `/home/user_2/frappe/connect_diagnostics/sites/local.test/private/backups/20260923_153126-local_test-database.sql.gz`.
- Repeated `bench --site local.test migrate` runs completed successfully and reused the same workflow,
  state/action masters, Custom Fields, and transition tasks without duplicates.
- The patch stops on an unexpected active workflow, unowned state, open Emergency action, conflicting
  transition task, or incompatible pre-existing Custom Field definition.
- Migrate repeatedly reports deletion of orphan Workspace Sidebar `Stock Counting`; this is an existing
  workspace cleanup outside this slice and no related source was changed here.

## Passing automated evidence

- Focused shared controls, print actions, workflow guard, fixture, setup, reset, and migration tests:
  55 tests passed before the final migration-safety regression; the patch suite then passed 6/6.
- Stock Entry workflow integration: 5/5 passed on `local.test`, covering distinct actors, direct-submit
  denial, stale mutation denial, retry without duplicate SLE, Return/Resubmit/Reject with no SLE,
  unauthorized and maker Review denial, native Submit/Cancel balances, native Batch Bundle movement and
  reversal, and non-Material-Transfer pass-through.
- Independent reviewer re-review: READY, no P0/P1 findings.
- `uvx pre-commit run --all-files`: passed all hooks after installing the locked npm development
  dependencies locally. Ruff, type checking, Semgrep, JSON/YAML checks, Prettier, and pip-audit passed.

## Blocking final gate

The required full command was executed:

`bench --site local.test run-tests --app connect_diagnostics_core`

All 687 unit tests passed. The new Warehouse Transfer integration tests passed 5/5. The integration run
initially reported 14 errors because legacy Stock Count tests assumed absent `_Test Item`, `_Test UOM`,
and `_Test Warehouse` masters. Those test-only prerequisites were created on `local.test`; the affected
Stock Count selection and variance suites then passed.

The remaining focused Stock Count adjustment suite has four unrelated baseline failures:

- one legacy assertion still expects an exact-location holding Material Transfer to auto-submit, while
  the existing implementation deliberately creates a draft for Workflow;
- three tests write `Stock Reconciliation` into `Stock Count Adjustment.entry_type`, whose current
  DocType options allow only Material Transfer, Material Receipt, and Material Issue.

These files and behaviors predate this change and belong to the explicitly excluded superseded Stock
Count/exact-location scope. They were not altered or revived. Because the Agent-Ready Plan requires the
full automated gate to pass before Computer Use, no Computer Use acceptance was run and no UI pass is
claimed. Final canonical documentation was also not written because repository policy places it after
runtime acceptance.
