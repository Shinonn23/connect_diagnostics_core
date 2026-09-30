# Slice plan: TSK-600 signed approval snapshots

Status: blocked at combined automated gate

## Goal and approved boundary

Extend the existing print-action snapshot mechanism so every approved baseline `Approve` action
fails closed unless the session user resolves server-side to an active Employee with an approval
signature. `Review` remains signed only for the approved direct Stock Entry transfer route.

The approved decision is `D-SIGNED-APPROVAL-2026-09-26` in `../decisions.md`. Existing
`*_by`, `*_at`, and `*_signature` fields remain the compatibility contract; no parallel
`*_action_*` field family or duplicate Employee signature field is introduced.

## Acceptance criteria

- One typed declaration maps DocType/action keys to existing or newly required snapshot fields and
  the protected/required-signature policy.
- The session user is resolved to an active Employee server-side; client-supplied Employee or
  signature values are ignored.
- Missing Employee or signature blocks every declared protected action in the same transaction as
  its synchronous Workflow Transition Task.
- Existing nonprotected print events retain their warning/nonblocking behavior.
- Replacing an Employee signature later does not rewrite an existing document snapshot.
- Re-approval replaces the current document snapshot while native Workflow Action, Version, and
  Timeline history remains authoritative.
- Existing field names and print behavior remain compatible; setup/migrate is idempotent.
- Stock Entry Review/Approve remain wired through their approved route-specific synchronous tasks.
- Existing baseline Approve transitions for Stock Reconciliation, Asset Movement, Sales Order,
  Sales Invoice Credit, Material Request, Purchase Order, Purchase Invoice, Payment Entry, and
  Payroll Entry use one shared synchronous approval snapshot task.
- Journal Entry receives only its approved declaration/fields because no Journal Entry baseline
  Workflow exists in the current manifest; no Workflow is invented in this slice.

## Exact owned files

Implementation is serialized after the current TSK-590 edits. No TSK-590 worker may write shared
files while TSK-600 is active. TSK-600 owns the final integrated diff in shared declaration/helper
files and the non-Stock-Entry Workflow rows; TSK-590 retains ownership of every Stock Entry row,
route-specific task record, adapter, field, migration, and test. The primary agent integrates and
reviews the combined result before either slice advances.

Task records:

- `.github/tasks/workflow-baseline-implementation/README.md`
- `.github/tasks/workflow-baseline-implementation/decisions.md`
- `.github/tasks/workflow-baseline-implementation/slices/tsk-600-signed-approval-snapshots.md`

Implementation and configuration:

- `connect_diagnostics_core/setup/print_action_fields.py`
- `connect_diagnostics_core/api/erpnext/print_actions.py`
- `connect_diagnostics_core/fixtures/workflow.json`
- one additive transition-task migration under `connect_diagnostics_core/patches/v1_0/`
- its matching recovery helper under `connect_diagnostics_core/patches/v1_0/`
- `connect_diagnostics_core/patches.txt`

Focused tests:

- `connect_diagnostics_core/setup/tests/test_print_action_fields.py`
- `connect_diagnostics_core/api/erpnext/tests/test_print_actions.py`
- `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py`
- focused migration tests under `connect_diagnostics_core/patches/v1_0/tests/`
- declaration-driven coverage for every mapped action and integration coverage for at least two
  existing canonical workflows

The fixture edit is limited to these existing Approve transitions and does not change their state,
role, condition, action label, or next state:

- `Connect Asset Movement Approval` / `Approve Asset Movement` (both existing role rows)
- `Connect Stock Reconciliation Blueprint` / `Approve Stock Reconciliation`
- `Connect Sales Order Blueprint` / `Approve Sales Order`
- `Connect Sales Invoice Credit Blueprint` / `Approve Sales Invoice Credit`
- `Connect Material Request Blueprint` / `Approve Material Request`
- `Connect Purchase Order Blueprint` / `Approve Purchase Order`
- `Connect Purchase Invoice Blueprint` / `Approve Purchase Invoice`
- `Connect Payment Entry Approval` / `Approve Payment Entry`
- `Connect Payroll Entry Blueprint` / `Approve Payroll Entry`

Every Stock Entry fixture row and every `Connect Stock Transfer *` transition-task record remains
owned and unchanged by TSK-600.

Final documentation after runtime acceptance:

- `docs/print/behavior.md`
- affected module behavior/workflow documentation only where runtime acceptance proves a change

## Explicit exclusions

- A new Journal Entry Workflow or any change to workflow roles, thresholds, route scope, posting,
  ledgers, document controllers, or approval authority.
- Renaming/removing existing snapshot fields or changing `Employee.approval_signature` from its
  current `Signature` field type.
- Client-side identity/signature input, asynchronous required snapshot tasks, named users, or a
  parallel audit/history store.
- Asset Disposal and any action other than the explicitly approved Approve actions plus Stock
  Entry Review.

## Migration and recovery

Create exactly one collision-checked `Workflow Transition Tasks` record named
`Connect Signed Approval Snapshot`. Its exact child fingerprint is one enabled, synchronous row:
`task = Capture Print Action: Authorized`, `enabled = 1`, `asynchronous = 0`, with no link. The nine
allowlisted Workflow consumers above reference this record. Existing `Connect Stock Transfer *`
records are immutable inputs and are neither reused nor changed by TSK-600.

Frappe v16 `apply_workflow()` resolves the named Transition Tasks record, invokes the registered
hook method with the in-memory document, runs synchronous tasks before `save()`/`submit()`, and
documents that they run in the same transaction. The shared record therefore calls the existing
constant wrapper `capture_authorized_action(doc)`, which selects action key `authorized`; the
central DocType declaration deterministically selects that DocType's compatible field triplet and
protected policy. It never derives or accepts an action key from client input.

An existing record with any other child fingerprint stops migration without mutation. Repeated
setup/migrate reuses the exact record and converges without duplicate Custom Fields or tasks.
Recovery first requires the allowlisted Workflow fixture references to be reverted. The recovery
helper then deletes only `Connect Signed Approval Snapshot`, only when its exact fingerprint still
matches and no Workflow transition references it; otherwise it stops for owner disposition.
Historical document snapshots, route-specific Stock Entry tasks, and native Workflow Action,
Version, and Timeline history are never deleted or rewritten.

## Automated and runtime evidence

Run focused setup/API/fixture/migration tests and two Workflow integrations on `local.test`, then
the full app suite and pinned pre-commit command. Independent code review must clear blocking
findings. Computer Use then verifies one successful signed Approve and one missing-signature
rejection on `dev.erp.connectdiagnostics.test`. Final documentation follows runtime acceptance and
receives independent review.

### 2026-09-26 implementation evidence

- Implemented the shared fail-closed signed snapshot task, active-Employee lookup, protected
  action declarations/fields, collision-checked migration and recovery helper, and the nine
  allowlisted non-Stock-Entry Approve transition references.
- Independent code review found and then cleared the separation-of-duties scope regression:
  distinct-actor enforcement remains Stock Entry-only; no P0/P1/P2 TSK-600 findings remain.
- `bench --site local.test migrate` passed twice, including first application and idempotent
  re-run of the transition-task patch.
- Focused tests passed: setup declarations (6), print actions (11), Workflow blueprints (5),
  migration/recovery (3), and real Sales Order/Material Request Workflow integration (3).
- `uvx pre-commit run --all-files` passed every configured hook, including Ruff, type checking,
  Semgrep, and dependency audit.
- The full `local.test` app gate reached integration tests but failed with one failure and six
  errors in existing TSK-590/Stock Count integration surfaces. Three Stock Entry Workflow errors
  resolve a site transition task named `Connect Stock Transfer Review Snapshot`, while the hook
  registry exposes the accepted shared capture/reset task names. Three Stock Count errors persist
  `Stock Reconciliation` into `Stock Count Adjustment.entry_type`, whose current Select options
  exclude it; one Stock Count assertion still expects an immediate submitted holding transfer
  although the current implementation intentionally creates a draft for Workflow submission.
- Discovered: `connect_diagnostics_core/api/erpnext/tests/test_stock_entry_workflow_integration.py:314`
  — the TSK-590 site Workflow references a transition-task name absent from the hook registry.
  Not in scope — file a separate issue if needed.
- Discovered: `connect_diagnostics_core/api/erpnext/tests/test_stock_count_adjustments.py:116`
  — Stock Count integration expectations and `Stock Count Adjustment.entry_type` metadata do not
  match the current draft-first Stock Entry Workflow/Stock Reconciliation behavior. Not in scope
  — file a separate issue if needed.
- Per the repository gate order, Computer Use acceptance and final documentation did not run
  because the combined automated gate is not green. TSK-600 focused behavior is implemented and
  independently reviewed; combined release acceptance waits on the separately owned TSK-590 and
  Stock Count failures above.
