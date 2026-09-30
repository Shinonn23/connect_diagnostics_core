# Slice plan: TSK-523 Generic Asset Movement approval

Status: browser acceptance blocked; implementation and focused automated evidence complete

## Goal and approved boundary

Require review and final approval before native ERPNext `Asset Movement` submit changes an Asset's
location or custodian. Native ERPNext remains the only owner of Asset state, Asset Activity, submit,
cancel, and reversal effects. Generic Asset Movement does not require a Material Request; an
intentionally linked Material Request continues to obey the existing allocation and QA validations.

This slice implements WF-06 only. WF-08 Equipment Assignment/Installation remains disabled. Borrow,
Demo, exact-location state engines, and Asset Disposal are excluded.

The approved route uses Maker (`Stock User`), Reviewer (`Stock Manager`), and Final Approver
(`C-Level Approver`) as the smallest role split consistent with the generic route and the existing
workflow baseline. The route decision is `D-ASSET-2026-09-26` in `../decisions.md`. Review and Approve
require TSK-600 signed-action snapshots and TSK-601 actor separation. Return and Reject preserve the
draft without native Asset effects. The route does not add receiver acknowledgement; the approved
business source did not require one for this baseline.

## Acceptance criteria

- Exactly one active intended Workflow covers `Asset Movement`.
- Maker can send and resubmit; Reviewer can review or return; Final Approver can approve or reject.
- Maker, Reviewer, and Approver are distinct server-resolved users, including for multi-role users.
- Review and Approve fail closed without a linked Employee and approval signature.
- Direct submit, state spoof, RPC/import/background bypass, stale approval, and permission revocation fail.
- Asset, purpose, company, transaction date, reference fields, and ordered child-row custody/location
  values are approval-critical; changing any after review or approval requires re-approval.
- Generic movements without a Material Request can complete the approved route.
- Linked-Material-Request movements continue to enforce submitted/same-company/allocation/QA rules.
- Return and Reject do not change Asset location, custodian, or Asset Activity.
- Approved submit invokes native ERPNext effects once; retry/concurrency cannot duplicate movement.
- Native cancel/reversal recomputes Asset state and preserves auditable movement/activity history.
- Multi-Asset movement follows native ERPNext behavior without a second custody ledger.
- Migration and repeated migrate are collision-aware, deterministic, recoverable, and preserve existing
  Workflow Action, Version, Timeline, and disabled Equipment history.

## Exact owned files

Task register and route configuration:

- `.github/tasks/workflow-baseline-implementation/decisions.md`
- `.github/tasks/workflow-baseline-implementation/README.md`
- `.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json`
- `.github/tasks/workflow-baseline-implementation/slices/tsk-523-asset-movement.md`
- `connect_diagnostics_core/fixtures/workflow.json`
- `connect_diagnostics_core/fixtures/workflow_state.json`
- `connect_diagnostics_core/fixtures/workflow_action_master.json`
- `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py`
- `connect_diagnostics_core/setup/tests/test_workflow_reset.py`

Asset Movement adapter and configuration:

- `connect_diagnostics_core/api/erpnext/asset_movement_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_asset_movement_workflow.py`
- `connect_diagnostics_core/setup/workflow_fields.py`
- `connect_diagnostics_core/setup/tests/test_workflow_fields.py`
- `connect_diagnostics_core/hooks.py` (serialized shared integration surface)

`asset_movement_workflow.py` also owns the narrow `Asset` DocType extension used only to scope an
opaque server capability around ERPNext's existing `make_asset_movement()` and
`cancel_movement_entries()` calls. No installed ERPNext source is edited.

Shared TSK-600/601 integration, only after its current owner lands the shared contract:

- `connect_diagnostics_core/setup/print_action_fields.py`
- `connect_diagnostics_core/setup/tests/test_print_action_fields.py`
- `connect_diagnostics_core/api/erpnext/print_actions.py`
- `connect_diagnostics_core/api/erpnext/tests/test_print_actions.py`

Migration and recovery:

- `connect_diagnostics_core/patches/v1_0/add_asset_movement_approval_controls.py`
- `connect_diagnostics_core/patches/v1_0/rollback_add_asset_movement_approval_controls.py`
- `connect_diagnostics_core/patches/v1_0/tests/test_add_asset_movement_approval_controls.py`
- `connect_diagnostics_core/patches.txt` (serialized migration ordering surface)

Final documentation after runtime acceptance:

- `docs/stock/behavior.md`
- `docs/stock/asset-movement/README.md`

The linked-Material-Request validator and its tests change only if focused regression evidence exposes
a defect. Installed Frappe/ERPNext/HRMS source is read-only.

## Design and decision rationale

- Keep Frappe Workflow authoritative for transitions and Workflow Action for pending actions.
- Use the shared `checked_*` snapshot for Review and `authorized_*` snapshot for Approve. Store
  server-resolved reviewer/approver users and revision digests in hidden setup-managed fields.
- Build one canonical digest from server-read top-level and ordered child-row values. Never trust a
  client-provided digest or workflow state.
- On submit, lock every involved Asset row in sorted Asset-name order before ERPNext validation, then
  acquire/reuse the current Asset Movement row lock, re-read persisted state and snapshots, recheck
  permission and distinct actors, and compare the current digest before ERPNext `on_submit` performs
  native Asset changes. Revalidate source location/custodian/status while those locks are held.
- Implement the Asset locks in an `Asset Movement.before_validate` hook when `_action == "submit"`,
  using duplicate-free `sorted({row.asset})` order and
  `frappe.db.get_value("Asset", asset, fields, for_update=True)`. Frappe runs `before_validate` before
  the ERPNext controller `validate`, so all source state checks and the later `before_submit` guard run
  under the same transaction locks until commit/rollback. `before_cancel` obtains the same ordered
  locks before native history recomputation. Focused concurrency tests use overlapping multi-Asset
  sets in opposite row order to prove deterministic acquisition and stale-state denial.
- Do not write Asset location/custodian or Asset Activity in the adapter. Native ERPNext
  `AssetMovement.on_submit/on_cancel` remains the only effect owner.
- Keep `material_request.validate_asset_movement` unchanged: it already passes generic movements and
  adds allocation/QA constraints only when a reference is intentionally present.
- Cancellation stays native. The adapter may validate the approved route/cancel permission but must
  not invent reversal data or update Asset directly.
- ERPNext `Asset.on_submit()` creates and immediately submits a `Receipt` Asset Movement, and
  `Asset.on_cancel()` cancels its submitted movements. Preserve this lifecycle with an `Asset`
  `extend_doctype_class` mixin that calls `super()` inside a private context manager. The context
  manager places an object-identity capability in request-local `frappe.local`; it is never a field,
  cache value, string nonce, request argument, or persisted configuration. The submit capability is
  bound to one Asset name and consumed once by the matching one-row Receipt movement. The cancel
  capability is bound to one Asset name and is valid only during ERPNext's synchronous native cancel
  loop. References/purpose/workflow state remain validation facts, never authorization facts.
- The native internal submit exception must match the exact ERPNext-generated shape: one row, matching
  Asset/company/location/custodian, Receipt purpose, and the Asset's Purchase Receipt/Invoice
  reference. Capability absence, wrong Asset, shape mismatch, replay, or client-supplied lookalike
  fails closed. No broad purpose/reference bypass exists.
- Match ERPNext's reference construction exactly: `Purchase Receipt` when `asset.purchase_receipt` is
  set; otherwise `Purchase Invoice`, whose `reference_name` may be null when the Asset has neither
  purchase reference. Tests cover Purchase Receipt, Purchase Invoice, and the native null-name
  Purchase Invoice shape; none authorizes a bypass without the object capability.
- During trusted native Asset cancellation, `before_cancel` requires the top capability to be the
  exact object minted around the synchronous `Asset.cancel_movement_entries()` call, requires at least
  one movement row to match the capability Asset, obtains sorted Asset locks, and changes only
  `workflow_state` from the submitted state to the cancelled state before Frappe persists docstatus 2.
  Frappe v16 skips `_validate()` for `_action == "cancel"`, so this explicit state assignment keeps
  workflow state/docstatus coherent without fabricating a Workflow action. ERPNext's existing query
  may cancel every submitted movement containing that Asset; the capability does not broaden the
  query and cannot authorize cancellation of a movement that does not contain the scoped Asset.
  Native `movement.cancel()` still owns permission checks, reversal, Asset recomputation, and history.
- The private context manager stores a stack of capability objects on `frappe.local` to support nested
  operations. Submit marks the matching capability consumed before allowing the boundary; a second
  movement or replay fails. Both submit and cancel remove the exact stack object in `finally`, on
  success and exception, and delete the request-local key when empty. Tests cover nesting, exception
  cleanup, wrong-stack order, replay, and a second Asset in the same request.
- Existing app-owned Dispatch and Borrow/Demo controllers also create Asset Movements. They receive no
  capability and no bypass: immediate programmatic submit is approval-gated, while generated drafts
  remain drafts. This preserves the explicit exclusion without weakening WF-06 authorization.
- Named generated entry points are ERPNext `Asset.make_asset_movement()` (immediate native Receipt),
  ERPNext whitelisted `transfer_asset()` (immediate generic submit and therefore gated),
  `api/erpnext/dispatch.py::_create_recovery_asset_movement()` (immediate submit and therefore gated),
  and `BorrowedAssetReturnInspection._create_release_movement/_create_repair_movement()` (draft-only,
  unchanged). `Dispatch` and `BorrowedItemResolution` validation paths consume submitted movements but
  do not receive a submit capability.

## Dependencies and sequencing

- `D-ASSET-2026-09-26` approves the WF-06 boundary, role authority, distinct-user identity rule, and
  trusted native-generated Receipt/Cancel exception. WF-08 remains disabled.
- TSK-600/601 currently exist only as uncommitted work on `feat/wf-tsk-521-transfer`. This slice must
  not copy or fork that shared logic. The shared contract must be accepted and made available to this
  branch before Asset integration and final automated gates.
- `hooks.py`, shared print-action modules, fixtures, setup configuration, and `patches.txt` are edited
  serially after dependency integration; no parallel writer owns them during implementation.

## Automated evidence on `local.test`

- Unit tests for canonical critical payload/digest, snapshot capture/clear, state spoof, actor
  separation, permission recheck, and hook registration.
- Unit tests for capability scoping, object identity, exact native Receipt shape, one-time submit
  consumption, cancellation scope, replay denial, and `Asset` extension `super()` delegation.
- Integration tests for generic no-MR happy path; linked-MR valid and invalid paths; Return/Reject;
  wrong-role, self-approval, direct submit/API, stale approval, retry/concurrency; multi-Asset native
  state and history; native cancel/reversal; and failed-submit rollback.
- Regression tests for Asset submit-generated Receipt and Asset cancellation-generated reversal,
  proving the internal path is authentic and cannot be reproduced by client-supplied references.
- Regression tests proving app-generated Dispatch/Borrow movements receive no hidden bypass: direct
  submit remains gated and generated draft behavior remains unchanged.
- Fixture/manifest exactness and migration repeat/rollback/collision tests.
- Full `bench --site local.test run-tests --app connect_diagnostics_core`.
- `pre-commit run --all-files`.

## Migration and recovery

Before mutation, capture the active Asset Movement Workflow, referenced states/actions/tasks, Custom
Fields, pending Workflow Actions, and affected pending documents on `local.test`. Stop only WF-06 on
an unrelated site-owned collision. Apply the reviewed fixture/configuration idempotently without
deleting or fabricating historical Workflow Action, Version, Timeline, Asset Movement, or Asset
Activity records.

The route fingerprint is an ordered canonical JSON value containing:

- Workflow name, document type, active flag, state field, action-confirmation/email settings;
- every ordered state tuple `(state, doc_status, allow_edit, update_field, update_value)`;
- every ordered transition tuple `(state, action, next_state, allowed, allow_self_approval, condition,
  transition_tasks)`;
- referenced Workflow State names/styles and Workflow Action Master names;
- each referenced Workflow Transition Tasks parent and ordered child tuple
  `(task, link, asynchronous, enabled)`;
- every Asset Movement approval Custom Field's fieldname, type, options, hidden/read-only,
  allow-on-submit, no-copy, and system-generated settings.

Preflight accepts only the reviewed legacy fingerprint or the exact desired fingerprint. A same-name
Workflow with any third fingerprint, another active Asset Movement Workflow, incompatible referenced
master/task/Custom Field, or unresolved open Workflow Action stops WF-06 without mutation. `owner` and
`modified` metadata never establish application ownership. The migration records no document names or
user data outside local test evidence.

Rollback restores the captured prior WF-06 configuration only while the expected post-migration
fingerprint matches. Submitted movements recover through native cancel/reversal, never database edits.
Repeated migrate must converge without duplicate fields, transitions, tasks, or master records.

The maker-owned `Send Asset Movement for Review` and `Resubmit Asset Movement` transitions set
`allow_self_approval=1` because Frappe otherwise blocks the document owner from initiating review.
All reviewer, approver, submit, cancel, return, and reject transitions keep it disabled; the signed
three-actor checks remain authoritative for separation of duties.

## Computer Use and documentation gates

After final automated gates and code review, a `browser_tester` uses distinct Maker, Reviewer,
Approver, unauthorized, and multi-role users on `dev.erp.connectdiagnostics.test`. It verifies visible
and denied actions, Return/Reject, mutation-after-approval, generic no-MR flow, linked-MR rejection,
native Asset location/custodian and history, retry, cancellation, and multi-Asset behavior.

Only after browser acceptance does `doc_writer` update canonical shipped behavior. An independent
reviewer then checks the documentation against accepted code and runtime evidence.

## Current gate evidence (2026-09-26)

- Focused Asset Movement evidence passes: 36 unit tests and 2 real integration tests, including
  linked-Material-Request validation, two-Asset native Receipt creation, role separation,
  Return/Reject/Resubmit, forced submit rollback and retry, native submit/cancel effects, Asset
  Activity, and both native Receipt cancellations.
- Migration tests pass 9/9; fixture tests pass 6/6; field tests pass 2/2; workflow reset tests pass
  11/11. Ruff, production `ty`, Semgrep, and `git diff --check` pass. Repeated migration converged.
- The full app run completed all 734 unit tests, then exposed three unrelated existing Stock Count
  integration expectations in `test_stock_count_adjustments.py`: the tests still expect immediate
  submitted Stock Entries and `receipt_entry`, while the accepted implementation now returns draft
  workflow documents and native Stock Reconciliation. Those failures are recorded, not changed in
  this WF-06 slice.
- The all-files pre-commit command is not green on this host: `prettier-eslint` cannot resolve its
  npm executable, and the repository-wide `ty` hook reports existing test-typing diagnostics. The
  change-owned production files pass the pinned Ruff/type/security checks.
- Local Bench resolves fixture sync from `apps/connect_diagnostics_core` rather than this isolated
  worktree. A second generic migrate therefore re-imported that checkout's legacy WF-06 fixture; the
  reviewed patch was re-applied and committed on `local.test` before the final focused run. This is a
  worktree test-environment constraint, not a production migration behavior.
- Computer Use cannot start on the current host because no browser interaction or video-recording
  capability is available. No Desk acceptance pass is claimed. Canonical `docs/` updates remain
  intentionally deferred until a Computer Use-enabled host validates
  `dev.erp.connectdiagnostics.test`.

## Integrated shared dependency

The independently reviewed, domain-neutral TSK-600/601 contract was committed atomically as
`8397486` on `feat/wf-tsk-531-approval-controls` and stacked onto this branch as `143965e`. TSK-523
imports only that accepted API; it does not copy or edit TSK-521's Stock Entry adapter, print-action
coupling, fixtures, hooks, fields, or migration. Shared API ownership remains with TSK-531.

The complete route plan and dependency integration require one final readiness review before runtime
activation.
