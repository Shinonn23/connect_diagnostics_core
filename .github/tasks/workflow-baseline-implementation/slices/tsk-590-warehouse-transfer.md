# Slice plan: TSK-590 Warehouse Transfer approval

Status: blocked at final automated gate

Implementation, focused tests, repeat migration, independent code review, and pre-commit are complete.
Computer Use and final documentation have not started because the required full-app test gate exposes
pre-existing Stock Count baseline inconsistencies recorded in
`../evidence/local-test-2026-09-23/warehouse-transfer.md`.

## Goal and approved boundary

Implement the approved direct `Stock Entry` Material Transfer route using native Frappe Workflow
for transitions and native ERPNext submit/cancel for stock effects. The route is Maker (`Stock User`)
to Reviewer (`Stock Manager`) to Final Approver (`C-Level Approver`) to authorized native Submit.
Review and Approve use the shared signed-action snapshot control. Protected actors must be distinct.

The approved decision is `D-TRANSFER-2026-09-23` in `../decisions.md`. Native transit legs,
Emergency Freeze, Borrow/Demo, exact-location/WMS, and custom posting are excluded.

## Acceptance criteria

- Exactly one active intended workflow covers direct Material Transfer.
- Maker Send/Resubmit works; Maker cannot Review/Approve and Reviewer cannot Final Approve.
- Review and Approve fail closed without a server-resolved Employee and approval signature.
- Direct submit, state spoof, RPC/import/background bypass, stale approval, and permission revocation fail.
- Return allows correction and Resubmit; Reject/Return create no Stock Ledger Entry.
- Approved Submit executes native ERPNext posting once; retry/concurrency cannot duplicate movement.
- Native cancel/reversal restores source/target balances; Serial/Batch behavior remains native.
- Non-Material-Transfer and excluded transit documents retain a no-approval pass-through and are not trapped.
- Native Workflow Action, Version, and Timeline remain authoritative; snapshots are current-action evidence.
- Migration/re-run is collision-aware, idempotent, recoverable, and preserves historical records.

## Exact owned files

Primary task-register ownership:

- `.github/tasks/workflow-baseline-implementation/decisions.md`
- `.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json`
- `.github/tasks/workflow-baseline-implementation/slices/tsk-590-warehouse-transfer.md`

Shared TSK-600/601 implementation ownership for this integration sequence:

- `connect_diagnostics_core/setup/print_action_fields.py`
- `connect_diagnostics_core/api/erpnext/print_actions.py`
- one shared SoD module under `connect_diagnostics_core/api/frappe/`
- focused shared-control tests beside the existing setup/API tests
- the `workflow_methods` registration in `connect_diagnostics_core/hooks.py`

TSK-590 completes its existing Stock Entry edits first. TSK-600 then receives serialized ownership
of the shared declaration/helper files and only the non-Stock-Entry Workflow fixture rows. TSK-590
retains exclusive ownership of Stock Entry fixture rows, `Connect Stock Transfer *` transition-task
records, its adapter, migration/recovery files, and route tests. No workers write the shared files
concurrently; the primary agent owns the final integrated diff.

TSK-590 route ownership:

- `connect_diagnostics_core/fixtures/workflow.json`
- `connect_diagnostics_core/fixtures/workflow_state.json`
- `connect_diagnostics_core/fixtures/workflow_action_master.json`
- `connect_diagnostics_core/api/erpnext/stock_entry_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_stock_entry_workflow.py`
- focused fixture/setup tests that assert this route
- one new forward migration patch, matching rollback/recovery helper and focused patch tests
- `connect_diagnostics_core/patches.txt`

Final documentation ownership after runtime acceptance:

- `docs/stock/behavior.md`
- `docs/stock/warehouse-transfer/README.md`

## Explicit exclusions

- Installed Frappe/ERPNext/HRMS source.
- ERPNext Stock Entry submit/cancel controllers and Stock Ledger, Bin, GL, Serial, or Batch writers.
- Existing Emergency Freeze implementation except removal from active Workflow fixture ownership and
  non-destructive migration disposition owned by TSK-602.
- Stock Reconciliation, Borrow/Demo, exact-location/WMS, threshold, delegation, named users, or new dependencies.
- Existing already-executed patches; the implementation adds a new ordered patch instead of rewriting history.

## Design and decision rationale

- Use the existing `checked_*` fields for Review and `authorized_*` fields for Approve. Extend the
  central print-action declaration with protected/required-signature semantics rather than create a
  parallel field family.
- Use one shared server-side SoD declaration/helper. The Stock Entry adapter supplies trusted Maker,
  Reviewer, action, current workflow state, and critical-field digest; it does not implement another engine.
- Keep final submit on the native Workflow transition to a docstatus-1 state. `before_submit` rechecks
  approved state, actor separation, current permission, and the approval-bound critical-field digest.
- Because Frappe activates Workflow per DocType rather than per route, explicit pass-through transitions
  cover non-transfer and excluded transit documents without adding an approval step.
- Serialize transition/submit checks with the current Stock Entry row lock and rely on native document
  docstatus/SLE transaction behavior for idempotency; do not create a second stock-operation ledger.

## Migration and recovery

Before writes, capture the active Stock Entry Workflow, referenced states/actions/tasks, Custom Fields,
pending Stock Entry Workflow Actions, and affected pending documents on `local.test`. Stop this route on
an unrelated site-owned collision. The new patch validates the expected owned configuration and applies
only the approved fixture transition, preserving Workflow Action, Version, and Timeline history.

Repeat migrate must converge without duplicate masters, fields, transitions, or tasks. Rollback restores
the captured prior active route configuration only while the expected post-migration fingerprint matches.
Already-posted stock is recovered through native cancel/reversal, never by database edits.

## Automated evidence on local.test

- Shared snapshot and SoD unit/integration tests, including missing Employee/signature and multi-role users.
- Fixture/manifest exactness and migration repeat/rollback/collision tests.
- Maker -> Reviewer -> Approver -> Submit happy path with native SLE and warehouse balances.
- Return/correction/Resubmit, Reject, wrong role, self-approval, permission revoke, API/state spoof/direct submit.
- Critical-field mutation invalidation, retry, concurrent submit, failure rollback, cancel/reversal.
- Serial and Batch movement results and non-Material-Transfer/excluded-transit pass-through.
- Full `bench --site local.test run-tests --app connect_diagnostics_core`.
- `pre-commit run --all-files`.

## Computer Use and documentation gates

After final automated gates and independent code review, a `browser_tester` uses distinct Maker,
Reviewer, Approver, unauthorized, and multi-role users on `dev.erp.connectdiagnostics.test`. It verifies
visible actions, denied actions, Return/Reject, mutation-after-approval, native ledger/balances,
Serial/Batch, retry behavior, cancellation, Timeline, and a non-Material-Transfer document. A blocked or
unavailable browser is reported as blocked, never passed. Final documentation is written only after this
runtime acceptance and independently reviewed.
