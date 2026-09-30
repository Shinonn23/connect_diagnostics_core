# TSK-528 — Purchase Invoice approval and payment boundary

Status: browser acceptance blocked — local.test implementation and automated gates complete

## Goal

Protect native ERPNext `Purchase Invoice` submission with receipt/source verification and
independent Accounting review/approval. A successful final Workflow transition may call native
submit and create ERPNext AP/GL effects; it must never create, submit, or approve a payment.

## Approved source contract

- The Purchase Invoice route ends at native PI submission. Payment approval/execution belongs to
  the separate Payment Entry route.
- ERPNext remains authoritative for PO/Purchase Receipt linkage, previous-document comparison,
  partial billing, advance allocation, update-stock behavior, duplicate supplier invoice checks,
  AP/GL posting, cancellation, and amendment.
- Custom code may add only approval-state, snapshot, separation-of-duties, stale-approval, and
  bypass guards, plus a source-policy check that has an approved D-AP decision.
- No matching tolerance, direct-expense category, invoice-before-receipt exception, approval
  authority, or duplicate identity rule is inferred by this task.

## Dependencies and current blockers

- `D-AP-TRIAL-2026-09-23` authorizes a temporary `local.test` route only. Permanent D-AP remains
  open and this implementation is prohibited from UAT/production promotion.
- Route-scoped D-TARGET is `local.test` / `dev.erp.connectdiagnostics.test` only. Shared DEV, UAT,
  and production are excluded.
- Route-scoped D-CORE/D-IDENTITY uses the reviewed technical defaults: current authenticated User,
  current document permission/role recheck, native Workflow/Workflow Action, server-built digest,
  database row lock at submit, request-scoped final-transition provenance, and distinct
  Maker/Verifier/Final Approver. Delegation and service identities are disabled for the trial.
- The clean branch lacks the shared TSK-600/601 helper. This slice will add the same bounded
  `approval_controls.py` contract already under review in TSK-521, with its own tests, as a bridge.
  The parent integration owner must reconcile the identical file and retain one canonical copy.
- Route-scoped TSK-602 disposition is authorized only for the inventoried `local.test` baseline:
  replace the active PI blueprint only when its exact fingerprint matches, PI/action counts remain
  zero, metadata remains synchronous, and every required role exists. Any mismatch stops migration.

The baseline manifest currently says `dev-enabled`, `enabled-on-dev`, and `records_are_inert: false`,
but the baseline README says no runtime slice is ready and the target/configuration decisions remain
open. For this slice the stricter evidence wins: the existing manifest flags are contested input
rather than sync authorization. Before any fixture or migration operation, the integration owner
must revise the WF-12 manifest entry with the approved temporary route
revision, target, executable permission contract, collision/pending-action disposition, rerun and
recovery validation, and independent configuration review.

Implementation may start only after independent review accepts this revised ownership and
local.test-only disposition. No runtime sync/migration occurs before code review and focused tests.

## Temporary local.test policy

- `Accounts User`: Maker; creates and corrects the draft.
- `Purchase Manager`: Receipt/Source Verifier.
- `Accounts Manager`: Final Accounting Approver and native Submit actor.
- All three protected actors must be distinct current users with current document permissions.
- Every trial PI must reference both a submitted Purchase Order and submitted Purchase Receipt.
  Direct-expense/no-PO and invoice-before-receipt routes are disabled.
- ERPNext native reference comparison, partial billing, advance allocation, update-stock,
  duplicate Supplier Invoice, AP/GL, cancel, and amend behavior remains authoritative. No custom
  matching tolerance or duplicate identity is introduced.
- `is_paid` is not enabled by this route. Payment Entry approval/execution remains separate.
- A visible read-only PI warning must say that this is test policy and must be reviewed before UAT
  or production. Manifest/configuration evidence must also mark the route production-ineligible.

## Approved temporary route

```text
Draft
  -> Receipt / Source Verification
  -> Accounting Review
  -> Approved
  -> Submitted (native docstatus 1 and native AP/GL)

Receipt / Source Verification -> Returned or Rejected
Accounting Review             -> Returned or Rejected
Approved                      -> Returned or Submitted
Returned                      -> Receipt / Source Verification
Submitted                     -> Cancelled through the native Workflow transition
```

The implementation uses explicit states for Draft, Pending Source Verification, Pending Accounting
Approval, Returned, Rejected, Approved, Submitted, and Cancelled. The roles above are approved only
for the temporary trial and replace the existing one-stage Accounts Manager blueprint.

## Acceptance criteria

1. A PI can reach `docstatus = 1` only from the approved final Workflow transition with a current,
   server-built critical-field digest and accepted signed review/approval snapshots.
2. Direct `submit()`, REST/RPC, import/bulk, queue/background submission, and workflow-state spoofing
   fail closed; current state and authorization are locked/rechecked at the submit boundary. The
   registered PI `before_submit` hook requires and consumes request-scoped provenance created only
   by the reviewed final synchronous Workflow Transition Task, while also locking and verifying the
   persisted pre-transition Approved state and current snapshots.
3. Maker, source verifier/reviewer, and final approver obey the accepted distinct-actor contract,
   including multi-role users and revoked permissions.
4. Changes to AP/GL-critical values after protected review are rejected until the PI is returned for
   correction; resubmission produces a new digest and approval evidence without rewriting history.
5. Native PO/PR matching, partial invoice, advance allocation, duplicate supplier invoice,
   update-stock, AP/GL, cancel/amend, and retry behavior remains authoritative and is regression
   tested.
6. Returned/rejected drafts create no AP, GL, stock, Payment Entry, payment Workflow Action, or
   payment approval state. PI submission itself creates no payment outcome.
7. Migration is collision-safe, idempotent on repeated migrate, preserves Workflow Action/Version/
   Timeline history, and has an evidence-backed recovery path.

## Planned file ownership

Exclusive implementation files for this slice:

- `connect_diagnostics_core/api/frappe/approval_controls.py` — temporary bridge for canonical actor,
  stable digest, distinct-actor, and current-permission helpers; it must remain identical to the
  TSK-521 shared implementation and is reconciled to one canonical file at parent integration.
- `connect_diagnostics_core/api/frappe/tests/test_approval_controls.py` — bridge contract tests.
- `connect_diagnostics_core/api/erpnext/purchase_invoice_workflow.py` — PI-specific critical payload,
  review/approval transition tasks, stale-approval guard, submit/cancel boundary, and payment-boundary
  assertions. Its final-transition task sets a request-scoped, document-bound submit marker; the
  `before_submit` guard consumes that marker and rejects every other entry point.
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_invoice_workflow.py` — isolated guard,
  digest, permission, SoD, mutation, spoof, and no-payment tests.
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_invoice_workflow_integration.py` — native
  PO/PR/PI, partial/advance/duplicate, ledger, cancel/amend, retry/concurrency coverage on `local.test`.
- `connect_diagnostics_core/patches/v1_0/add_purchase_invoice_approval_controls.py` — collision
  preflight and additive configuration required by the reviewed route.
- `connect_diagnostics_core/patches/v1_0/rollback_add_purchase_invoice_approval_controls.py` —
  non-destructive recovery entry point.
- `connect_diagnostics_core/patches/v1_0/tests/test_add_purchase_invoice_approval_controls.py` —
  preflight, collision, idempotency, history-preservation, and recovery tests.

Serialized shared files owned by this slice for the reviewed local.test revision; parent integration
must reconcile concurrent workflow branches before merge:

- `connect_diagnostics_core/setup/workflow_fields.py` and
  `connect_diagnostics_core/setup/tests/test_workflow_fields.py` — PI workflow/digest/actor fields
  and a visible production-ineligible trial-policy warning.
- `connect_diagnostics_core/setup/print_action_fields.py` and its focused tests only if the accepted
  TSK-600 contract has not already registered PI review/approval snapshots; the exact test file is
  `connect_diagnostics_core/setup/tests/test_print_action_fields.py`.
- `connect_diagnostics_core/hooks.py` — append PI validators and named synchronous Workflow methods
  while preserving the existing TDS and stock-freeze handlers and their order. The PI
  `before_submit` list must include the fail-closed approval guard before native effects.
- `connect_diagnostics_core/fixtures/workflow.json`, `workflow_state.json`, and
  `workflow_action_master.json` — the single reviewed PI route only.
- `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py` — route integrity and
  payment-boundary assertions.
- `connect_diagnostics_core/patches.txt` — additive patch ordering only.
- `.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json` — approved revision,
  owner, route scope, shared controls, collision/rerun/recovery contract.
- `.github/tasks/workflow-baseline-implementation/decisions.md` — D-AP decision only when supplied by
  the named business owners; D-AP-TRIAL is now recorded.

Final documentation files, written only after automated and Computer Use acceptance:

- `docs/accounting/behavior.md`
- `docs/accounting/purchase-invoice/README.md`

## Explicit non-changes

- No Payment Entry workflow, payment execution, bank integration, or duplicate-payment control.
- No custom AP/GL/stock posting engine and no override of ERPNext Purchase Invoice controllers.
- No invented tolerance, threshold, source category, or permanent approval role; only the explicit
  temporary local.test roles and source policy above are allowed.
- No weakening or replacement of native duplicate supplier-invoice validation.
- No direct edit of site data, open Workflow Actions, Version, or Timeline history.
- No migration/install/update/fixture sync on `local` or shared DEV/UAT.

## Verified local.test inventory — 2026-09-23

Read-only inspection found:

- one active `Connect Purchase Invoice Blueprint` with fingerprint
  `f1ff2f961f021ba1cc7a3d042c38a21ff28c4760c4c6e0dafd93d3d95207f031`;
- the existing six-state/five-transition Accounts User/Accounts Manager route, with no transition
  tasks;
- no Purchase Invoice records and no open Purchase Invoice Workflow Actions on `local.test`;
- Purchase Invoice metadata is submittable and tracked, with `queue_in_background = 0`.
- all three required Roles exist and are enabled, but only Administrator currently holds them; test
  users must be created as isolated fixtures for automated/Computer Use acceptance.

This empty local test inventory authorizes only guarded replacement of the exact fingerprint on
`local.test`. The patch must stop on any mismatch, unrelated active PI Workflow, open action,
existing PI, missing role, or pending document requiring owner disposition. Tests must prove
Workflow Action, Version, and Timeline rows are preserved. No other target is authorized.

The selected implementation relies on synchronous final-transition provenance. Migration preflight
must fail closed if `Purchase Invoice.queue_in_background` is nonzero. Supporting durable
authorization across queued workers would require a separately reviewed persistence/idempotency
design and is outside this slice.

## Shared-control integration contract

The temporary bridge exposes contract revision `approval-controls-trial.1` for:

- canonical actor resolution and current permission/role recheck;
- maker/reviewer/approver distinctness, including multi-role precedence;
- server-built critical digest and revision binding;
- immutable Employee/signature snapshot fields and synchronous transition-task writers;
- snapshot clearing on Return without deleting historical Version/Workflow evidence.

The concrete helper API is `critical_digest`, `resolve_user`, `require_distinct_actors`, and
`require_permission` in `connect_diagnostics_core.api.frappe.approval_controls`. PI adapter tests
must import and exercise it. The bridge does not create separate persistence and must be reconciled
with TSK-600/601 before the parent branch is accepted.

## Test plan

Focused automated tests on `local.test` cover:

- PO + Purchase Receipt + PI happy path and native ledger effects;
- native partial receipt/invoice and update-stock double-post prevention;
- native duplicate supplier invoice behavior with the configured Accounts Settings policy;
- direct submit, REST/RPC/import/state spoof, request-marker reuse, missing final-transition marker,
  stale persisted state, and verified rejection if background submission is enabled;
- wrong role, maker/reviewer/approver identity collisions, multi-role user, permission revocation;
- stale digest, critical mutation, transaction lock, retry/concurrency, and idempotent final action;
- return/reject no-ledger behavior, submitted cancel/amend, and preserved audit evidence;
- no Payment Entry, payment Workflow Action, or payment approval side effect.

Trial-policy tests must reject direct-expense/no-PO, invoice-before-receipt, and `is_paid`; they must
show that native partial billing and advance allocation remain unchanged and that no custom
matching tolerance or strengthened supplier-invoice identity exists. Permanent-policy variants
remain blocked until D-AP-TRIAL is replaced.

Final gates are focused tests, full app tests, pinned pre-commit, independent code review and
re-review, Computer Use with distinct actors at `dev.erp.connectdiagnostics.test`, final
documentation, and independent documentation review.

## Migration and recovery

Before mutation, capture the active PI Workflow fingerprint, all open PI Workflow Actions, relevant
states/actions/transition-task records, and the pending document states authorized by TSK-602. Stop
on any unrelated active Workflow or incompatible owned record. Repeated migrate must converge to the
same reviewed configuration without deleting or fabricating history.

Recovery is authorized only on `local.test`, only when the installed route matches the reviewed
trial fingerprint, and only while no PI or PI Workflow Action exists. It restores the inventoried
baseline Workflow definition while retaining additive fields/tasks and all Version/Timeline data.
Any mismatch stops recovery. Posted/tested invoices must use native cancel/amend/reversal behavior
and be resolved before configuration recovery; recovery never deletes or fabricates Workflow
Action, Version, Timeline, AP/GL, or stock history.

## Readiness decision

Implementation is not `ready` until an independent reviewer accepts this revision and exact file
ownership. D-AP-TRIAL and the fingerprint-bound disposition authorize only local.test. Before site
mutation, the manifest must identify the temporary revision as production-ineligible and code review
plus focused tests must pass. UAT/production remain prohibited.

Independent re-review on 2026-09-23 found no remaining P1/P2 plan defects and accepted this as a
blocked implementation plan. That acceptance does not satisfy or waive any runtime dependency.

## Implementation evidence — 2026-09-23

- Guarded `local.test` migration completed and converged on the reviewed trial fingerprint
  `3ea81f3361ed26a1cff28b4a3c4d759e44e142b8c6bf72a7bc26e14c3eb75956`.
- Focused unit suites passed: PI workflow (14), shared approval controls (1), print-action fields
  (5), workflow fields (1), fixture blueprints (4), and guarded patch/recovery (5).
- The integration route passed with distinct Maker, Source Verifier, and Accounting Approver:
  native PO and Purchase Receipt sources, direct-submit rejection, native Workflow submission,
  GL creation, no Payment Entry/payment Workflow Action, native cancellation, and GL reversal.
  Its first final rerun met a transient MariaDB deadlock while ERPNext wrote a Purchase Order status
  comment; the unchanged test passed on immediate retry in 6.793 seconds.
- `pre-commit run --all-files` passed all configured hooks: whitespace/EOF/conflict/syntax checks,
  Ruff, Prettier/ESLint, JSON formatting, `ty`, Frappe Semgrep rules, and dependency audit.
- The full app unit category passed 689 tests. The full integration category ran 71 tests with one
  failure and four errors in pre-existing Stock Count and ERPNext bootstrap coverage: three Stock
  Count adjustment cases use the retired `Stock Reconciliation` select value, one Stock Count
  setup imports an ERPNext customer fixture without this app's required Customer Code, and one
  holding-transfer test still expects immediate submission although the accepted stock workflow
  now creates a draft. None of those files or behaviors is changed by TSK-528; they remain
  separately owned baseline test debt and do not waive the focused PI gates.
- Automated fixtures rolled back their users and transactions. Post-test inspection found no
  Purchase Invoice, Purchase Invoice Workflow Action, or isolated trial user left behind.

The browser tester attempted Step 0 at `dev.erp.connectdiagnostics.test`, but this Codex host exposes
no Computer Use, Chrome profile/session control, screenshot, or video-recording capability. No UI
session was opened and no browser test data was created. Computer Use acceptance must restart from
Step 0 on a capable desktop host; final documentation and its independent review remain gated behind
that acceptance. A final read-only site inspection revalidated the exact installed configuration and
found zero Purchase Invoices, zero Purchase Invoice Workflow Actions, and zero isolated trial users.
The route remains explicitly prohibited from UAT or production promotion.
