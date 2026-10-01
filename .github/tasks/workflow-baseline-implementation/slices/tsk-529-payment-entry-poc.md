# TSK-529 — Payment Entry approval proof of concept

## Status

POC review gate accepted on 2026-09-26. The focused unit suite passed 7/7, the real Workflow/native
posting integration suite passed 2/2 twice sequentially, and the selected-file pre-commit gate
passed. A fresh post-run inspection confirmed that the test Workflow, states, actions, tasks,
users, Employees, Payment Entries, token Comments, and GL Entries were absent, while
`Connect Payment Entry Approval` was restored as the active baseline Workflow.

This disposable spike proves the technical boundary on `local.test`; it is not an approved Finance
policy and must not be promoted to DEV, UAT, or production until the open decisions below are signed
off. Full-suite, Computer Use, final documentation, and promotion gates are deliberately deferred
because the provisional policy and adapter are not a shippable implementation.

Computer Use acceptance was attempted on 2026-09-26 and blocked before login because the execution
host exposed no browser-control, screenshot, or recording capability. The HTTP Desk endpoint was
independently confirmed to return the Frappe login page, while its HTTPS endpoint was not listening.
No UI acceptance pass is claimed; no records were mutated by the blocked attempt.

Activation is fail-closed. Runtime behavior is enabled only when both conditions are true:

- `frappe.local.site == "local.test"`; and
- the site-scoped `connect_diagnostics_payment_entry_poc_enabled` configuration key is exactly `1`.

Every other site retains current behavior even if this branch is accidentally installed. The
activation boundary is covered by tests. Approved implementation must delete the POC module and
replace the flag with the reviewed shared-core/domain-adapter contract; the flag must never become
a production setting.

## Goal

Prove that standard ERPNext Payment Entry can remain the sole posting boundary while the app
enforces a draft-only Maker → Checker → Approver route and blocks every unapproved submit path.
Native ERPNext remains responsible for allocation, GL, AP/AR outstanding, cancellation, and
reversal.

## Provisional POC policy

- Accounts User is Maker.
- Accounts Manager is Checker and the user permitted to invoke the final native submit transition.
- C-Level Approver is Approver.
- Pay is the only enabled POC route. Receive and Internal Transfer are rejected while the POC flag
  is active and tested as deferred. This is not business authorization for Pay.
- Maker, Checker, and Approver must resolve to three different active Employees linked to the
  acting users. Checker and Approver signatures are required and snapshotted at action time.
- No amount threshold is implemented.
- Bank API execution and proof of external bank settlement are outside scope.

## Acceptance criteria

1. Draft and returned/rejected Pay Payment Entries cannot submit through UI, REST/RPC, direct
   `submit()`, import, or background execution.
2. Only the provisional role may perform each state transition; changing `workflow_state`
   directly does not weaken the same server-side checks.
3. Checker and Approver cannot be the Maker or each other, including users carrying multiple
   roles.
4. The server snapshots the linked Employee, action time, and Employee approval signature for
   Maker, Checker, and Approver.
5. Approval stores a deterministic digest of posting-critical fields. A material edit reopens the
   document and clears stale check/approval evidence.
6. The `before_submit` boundary locks and re-reads the Payment Entry row, requires an approved
   prior database state, verifies the digest, and then returns normally so the same native
   `Document.submit()` call continues into ERPNext posting. The POC never invokes `submit()` itself.
7. Return/Reject has no ledger or allocation effect. Native cancel/reversal behavior remains
   unchanged.
8. A repeated sequential submit cannot create a second posting effect for the same Payment Entry.
   The POC does not claim concurrent-submit or application-operation idempotency; those remain
   explicit final-implementation requirements.
9. On unconfigured sites all POC handlers return without mutation, and Receive/Internal Transfer
   are rejected explicitly on an enabled POC site.

## Lifecycle boundary

- `validate`: when the POC is enabled, enforce the permitted transition matrix against the
  authoritative database state, roles, Employee identity and SoD; capture action snapshots; and
  invalidate stale evidence on a critical-field mutation.
- `before_submit`: acquire `Payment Entry` with `for_update=True`, require database state
  `Payment Entry Approved`, require the workflow-driven in-memory submitted state, verify actor
  snapshots and digest, then return to native ERPNext submission.
- `on_submit`: no POC handler. ERPNext exclusively owns GL, allocation, outstanding and linked
  document updates.
- Native Frappe `apply_workflow()` remains the UI/RPC transition entry point. No whitelisted POC
  method or API response is added. Import, background execution and direct `submit()` converge on
  the same document hooks.

## Owned files

- `.github/tasks/workflow-baseline-implementation/slices/tsk-529-payment-entry-poc.md`
- `connect_diagnostics_core/api/erpnext/payment_entry_approval_poc.py`
- `connect_diagnostics_core/api/erpnext/tests/test_payment_entry_approval_poc.py`
- `connect_diagnostics_core/api/erpnext/tests/test_payment_entry_approval_poc_integration.py`
- `connect_diagnostics_core/hooks.py`

No Workflow fixture, setup field, Custom Field, patch, schema, shared approval core, or whitelisted
API is added. Maker, Checker, and Approver snapshots persist in the existing `submit_*`, `checked_*`,
and `authorized_*` fields. The checker also stores a visibly prefixed, HMAC-signed check token in a
native `Comment` inside the same workflow transaction. That token is bound to the Payment Entry
name, critical-field digest, and complete Maker + Checker Employee/user/time/signature snapshots.
The Approver verifies the check token, captures the Approver snapshot, and stores a separately
prefixed HMAC-signed approval token bound to the same digest and the complete Maker + Checker +
Approver chain. The site encryption key signs both tokens without being logged or persisted.

Submit requires exactly one valid approval token matching every current snapshot field and the
posting digest. Missing, stale, mismatched, malformed, duplicate-current, edited, deleted, wrongly
owned, or invalid-signature evidence fails closed. The actor User is recovered from the snapshotted
Employee and must match the User encoded in the token. Other Timeline content is ignored. This
disposable choice avoids schema mutation and is not the final immutable evidence design.

Field ownership is existing app configuration, not a POC assumption:
`connect_diagnostics_core/setup/print_action_fields.py` registers Payment Entry actions for
`submit_*`, `checked_*`, and `authorized_*`; `hooks.py` applies that setup after install/migrate.
A read-only `local.test` metadata inspection on 2026-09-26 confirmed all nine Employee/time/signature
fields exist and `poc_posting_digest` does not. Integration setup must assert the nine fields are
present and writable before it changes any Workflow record, otherwise it aborts without mutation.

The isolated integration test creates only Workflow configuration under unique test names,
snapshots the prior active-workflow state, and relies on one IntegrationTestCase database connection
and class transaction rollback to restore records it created. `hooks.py` is owned exclusively by
this slice in its dedicated worktree. The separate Stock Transfer worktree is not modified.

## Tests

- Isolated tests for critical-field canonicalization, digest behavior, transition matrix, roles,
  Employee/signature resolution, SoD, state spoofing, stale approval, and submit locking.
- Integration tests on `local.test` for Pay; explicit rejection of Receive and Internal Transfer;
  invoice allocation/outstanding recheck; repeated sequential submit; native posting-failure
  rollback; and cancel/reversal. Concurrent submit is deferred and must not be reported as passed.
- Token tests cover missing/stale/mismatched Maker, Checker, and Approver snapshots; forged content
  or signature; wrong owner/document/actor/time; deleted evidence; and duplicate-current ambiguity.
- Tests with the flag absent, false, and on a non-`local.test` site prove the POC is inert.
- Full app suite and pinned pre-commit command after focused tests.
- Computer Use on `dev.erp.connectdiagnostics.test` only after automated gates pass.

## Migration and rollback

The POC may mutate only `local.test`, and only from the isolated integration-test setup. There is no
fixture or migration application. Test setup records the current active Payment Entry Workflow and
pending Workflow Action identifiers, and aborts on a collision with an intended test-only Workflow,
Action, State, or Transition Task name. The single IntegrationTestCase database connection and
class transaction contain every test-created configuration record, Payment Entry, POC Comment and
accounting effect; class teardown rolls it back and verifies the prior active Workflow and
pending-action identifiers are unchanged. The POC does not open a secondary connection or claim
concurrency evidence.
It never deletes Workflow Action, Version, Timeline, submitted accounting records, or any record it
did not create.

Operational rollback is disabling/removing the site flag, which makes all POC handlers inert.
Failed test setup runs the same teardown from captured evidence. Any submitted test Payment Entry
is cancelled through native ERPNext before test-owned configuration cleanup; cancellation failure
stops cleanup and preserves evidence for investigation.

## Disposable adapter boundary

All provisional identity, SoD, signature, digest, and lock behavior lives only in
`payment_entry_approval_poc.py`. It does not import from, export to, or claim ownership of
SHARED-529/531. The module and hook registrations are deleted when the POC is accepted or rejected.
No final adapter may copy its provisional role or identity constants without a new approved plan.

## Deferred owner requirements

- D-PAYMENT: enabled voucher matrix, thresholds, currencies, accounts, beneficiaries, bank
  evidence, and settlement semantics.
- D-IDENTITY/D-CORE: canonical business identity, service users, delegation, operation identity,
  and immutable-evidence requirements.
- CONFIG-PAYMENT: retain/replace/retire decision, pending-record disposition, collision ownership,
  and promotion sign-off.
- Final role names, permission scopes, report/print/email exposure, and external-bank semantics.

Promotion is prohibited until these decisions replace every provisional policy above and the plan
is reviewed again.
