# Preparatory slice: TSK-523A Native Asset Movement boundary

Status: completed; inactive pending full TSK-523 integration

## Goal

Implement and unit-test the non-activating, policy-independent primitives needed to preserve ERPNext's
native Asset submit/cancel lifecycle once WF-06 approval gating is enabled:

- an `Asset` extension mixin that delegates native movement creation/cancellation through `super()`;
- an opaque object-identity capability scoped on `frappe.local` with nested and exception-safe cleanup;
- exact validation of the one-row native Receipt shape, including nullable Purchase Invoice reference;
- deterministic duplicate-free Asset row locking helpers for submit/cancel transaction boundaries.

This slice does not register the mixin or hooks. It changes no current runtime behavior and must not be
deployed independently as the completed WF-06 route.

## Exact owned files

- `connect_diagnostics_core/api/erpnext/asset_movement_workflow.py` — new inactive primitives only.
- `connect_diagnostics_core/api/erpnext/tests/test_asset_movement_workflow.py` — isolated unit tests.
- `.github/tasks/workflow-baseline-implementation/slices/tsk-523a-native-asset-boundary.md` — this record.

No existing file changes are authorized. In particular, do not edit `hooks.py`, Workflow fixtures,
setup fields, shared TSK-600/601 modules, migrations, `patches.txt`, site configuration, or docs.

## Acceptance criteria

- The private capability is an object identity, never a document field, request argument, cache value,
  or persisted nonce.
- Capability stack state is request-local, supports nesting, is removed in `finally`, and cannot be
  replayed after consumption or leakage after an exception.
- Submit capability is bound to one Asset and one native Receipt; a second movement, wrong Asset,
  multi-row movement, wrong company/location/custodian/purpose/reference, or client lookalike fails.
- Exact native reference variants are accepted only with capability: Purchase Receipt, Purchase
  Invoice, and Purchase Invoice with null `reference_name`.
- Cancel capability is bound to one Asset and recognizes only movements containing that Asset while
  the synchronous native cancel context is active.
- The Asset mixin calls `super().make_asset_movement()` and `super().cancel_movement_entries()` inside
  the matching context and preserves return values/exceptions.
- Lock helper uses duplicate-free sorted Asset names and
  `frappe.db.get_value(..., for_update=True)` in deterministic order.
- Unit tests use `frappe.tests.UnitTestCase`, pass, and demonstrate no hooks/runtime registration.

## Dependencies and handoff

This preparatory code remains inactive until the full TSK-523 plan is ready. Later integration owns
hook registration, Workflow route/roles, persisted approval snapshots, SoD, submit/cancel guards,
migration, integration tests, Computer Use, and documentation. Before activation, the full slice must
resolve D-ASSET/D-CORE/D-IDENTITY and land the accepted TSK-600/601 contract.

## Completion evidence

- Independent plan review: READY; no P0/P1/P2 findings.
- Independent code re-review: previous mutable-capability P1 resolved; no P0/P1 findings remained.
- Focused `local.test` suite: 11/11 passed using the TSK-523 worktree on `PYTHONPATH`.
- Ruff check, Ruff format, Python compile, and `git diff --check`: passed.
- Runtime activation audit: no `hooks.py`, fixture, setup, migration, patch, site configuration, or
  documentation change is present in this preparatory slice.
