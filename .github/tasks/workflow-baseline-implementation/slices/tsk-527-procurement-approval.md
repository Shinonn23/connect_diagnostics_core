# Slice plan: TSK-527 Purchase Order approval

Status: automated gates and code review passed; Computer Use acceptance blocked by host capability

Independent plan review passed on 2026-09-26 after the server entrypoint/order, versioned digest-map
contract, and WF-11/TSK-602 handoff were made explicit. The owner approved
`D-PROCURE-PO-2026-09-26` on 2026-09-26. Implementation, automated tests, and migration rehearsal are
authorized on `local.test`; Computer Use is authorized on `dev.erp.connectdiagnostics.test`.
Shared-DEV mutation remains blocked while affected open Workflow Actions lack record-level disposition.

## Goal and boundary

Require independent review and final approval before a standard ERPNext `Purchase Order` can be
submitted and create a supplier commitment. Keep Request for Quotation and Supplier Quotation as
native upstream documents and preserve native Purchase Receipt, Purchase Invoice, pending-quantity,
cancel, and amend behavior.

The approval boundary is Purchase Order. This slice must not create a custom RFQ, supplier-selection,
receipt, invoice, payment, or posting engine, and it must not reintroduce a Material Request Workflow.

## Source priority and approved decision

The task request dated 2026-09-21 and the TSK-602 migration contract take precedence over the main
workflow task where they conflict. Native ERPNext behavior is the fallback after repository policy.

`D-PROCURE-PO-2026-09-26` approves direct PO and native RFQ/Supplier Quotation reference paths. RFQ and
Supplier Quotation are optional and no category-specific sourcing prerequisite is introduced. Every PO,
regardless of value or transaction currency, requires Purchase User Maker, Purchase Manager Reviewer,
and C-Level Approver Final Approver, with three distinct users. Multi-role users cannot collapse or skip
a protected step. Threshold/currency bypasses, delegation, named-user exceptions, and a Material Request
Workflow are disabled.

The accepted TSK-600 snapshot and TSK-601 segregation-of-duties contracts remain implementation
dependencies rather than policy gaps. `CONFIG-PENDING` remains open only for record-level disposition
of the three PO and two MR actions recorded on shared DEV. TSK-602 must stop before configuration writes
when any such unresolved action exists; it may proceed on an authorized target with none.

## Acceptance criteria

- Exactly one intended active Workflow protects Purchase Order submission.
- Maker, Reviewer, and Final Approver are independently authorized, and protected actors are distinct.
- Direct `submit()`, REST/API, RPC, import/bulk, background, and workflow-state spoof paths fail before
  any native PO submit effect unless current approval evidence is valid.
- Review and final approval snapshots are bound to the current PO revision and commitment-critical
  values. Material changes after review or approval require the configured return/re-approval path.
- The approved, versioned commitment-field map covers supplier/company identity, currency and pricing,
  route/type flags, addresses and delivery terms, item identity/source/quantity/rate/schedule/warehouse,
  taxes/discounts/totals, payment schedules/terms/advances, accounting dimensions, subcontracting and
  supplied-item commitments. No unreviewed catch-all or client-selected field list is permitted.
- Return and Reject leave the PO unsubmitted and create no native downstream commitment effects.
- Approved submission calls the native ERPNext Purchase Order controller exactly once; retry and
  concurrency cannot duplicate the submission.
- Native cancel/amend, Purchase Receipt, Purchase Invoice, references, statuses, and pending quantities
  remain correct.
- RFQ and Supplier Quotation remain native upstream documents; no custom comparison or posting engine
  is introduced.
- Material Request Workflow configuration is removed only through TSK-602. Historical Workflow Action,
  Version, Workflow Timeline, and source-document evidence are never deleted or fabricated.

## Exact implementation ownership after the decision gates pass

The accepted TSK-600/601 implementation exists only as reviewed, uncommitted work on the TSK-521
worktree. To avoid blocking or modifying that worktree, TSK-527 carries the same shared API contract and
focused tests in this branch, then adds only PO-specific composition. Conflicts at parent integration
must resolve to the reviewed shared implementation rather than retaining duplicate behavior.

No separate TSK-602 branch or accepted patch exists. For this WF-11 slice, TSK-527 owns the bounded,
guarded TSK-602 migration that removes only the Material Request Workflow from active canonical
configuration after the approved no-open-action gate. This ownership exception does not extend to other
routes or authorize record-level disposition on shared DEV.

TSK-527 owns these exact implementation files:

- `connect_diagnostics_core/api/frappe/approval_controls.py` (accepted shared API snapshot)
- `connect_diagnostics_core/api/frappe/tests/test_approval_controls.py` (accepted shared tests)
- `connect_diagnostics_core/api/erpnext/purchase_order_workflow.py` (new)
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_order_workflow.py` (new)
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_order_workflow_integration.py` (new if
  site/metadata/native downstream behavior cannot be covered in the focused test module)
- `connect_diagnostics_core/api/erpnext/print_actions.py`
- `connect_diagnostics_core/api/erpnext/tests/test_print_actions.py`
- `connect_diagnostics_core/setup/print_action_fields.py`
- `connect_diagnostics_core/setup/tests/test_print_action_fields.py`
- `connect_diagnostics_core/setup/workflow_fields.py`
- `connect_diagnostics_core/setup/tests/test_workflow_fields.py`
- `connect_diagnostics_core/setup/procure_to_pay.py`
- `connect_diagnostics_core/setup/tests/test_procure_to_pay.py`
- `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py`
- `connect_diagnostics_core/setup/tests/test_workflow_reset.py`
- `connect_diagnostics_core/fixtures/workflow.json`
- `connect_diagnostics_core/fixtures/workflow_state.json`
- `connect_diagnostics_core/fixtures/workflow_action_master.json`
- `connect_diagnostics_core/hooks.py`
- `connect_diagnostics_core/patches/v1_0/configure_purchase_order_approval_boundary.py` (new)
- `connect_diagnostics_core/patches/v1_0/rollback_purchase_order_approval_boundary.py` (new recovery helper)
- `connect_diagnostics_core/patches/v1_0/tests/test_configure_purchase_order_approval_boundary.py` (new)
- `connect_diagnostics_core/patches.txt`
- `.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json`
- `.github/tasks/workflow-baseline-implementation/decisions.md`
- `.github/tasks/workflow-baseline-implementation/slices/tsk-527-procurement-approval.md`
- this slice record and TSK-527 runtime evidence under the workflow-baseline task directory
- final accepted procurement behavior documentation after Computer Use acceptance

The primary agent serializes all shared fixture, setup, hook, patch-order, manifest, and task-record
edits. A worker may own only the new PO adapter and its two focused test modules. No other worktree may
write these files during this slice.

## Explicit exclusions

- Installed Frappe, ERPNext, ERPNext Thailand, and HRMS source.
- Custom RFQ, Supplier Quotation, supplier-selection, receipt, invoice, payment, or posting engines.
- Purchase Invoice/payment approval policy and runtime behavior.
- New Material Request approval states, actions, guards, or Workflow.
- Authority thresholds, currency conversions, mandatory source evidence, named users, and delegation
  until explicitly approved.
- Ad hoc console writes or direct database changes to resolve legacy Workflow Actions.

## Design constraints

- Native Frappe Workflow owns transitions and Workflow Action owns pending actions.
- Native ERPNext Purchase Order `on_submit`, cancel/amend, ordered quantities, and downstream document
  mapping remain the only owners of procurement effects.
- TSK-527 registers `purchase_order_workflow.validate_before_submit` as the first callback in the
  existing `doc_events["Purchase Order"]["before_submit"]` list. The existing
  `regulatory_transactions.capture_transaction_snapshot` callback remains second. The guard performs
  the last permission, actor, state, snapshot, digest, and persisted-row recheck under the approved
  locking contract before the regulatory snapshot and before native `PurchaseOrder.on_submit` effects.
- No whitelisted-method override, controller override, recursive `submit()`, or duplicate call to the
  native controller is allowed. All UI, Workflow, REST/API, RPC, import, bulk, and background paths
  converge on the same Frappe document lifecycle and therefore the same first `before_submit` guard.
- Approval evidence is revision-bound supporting evidence; native Version and Workflow Timeline are
  audit history, not an immutable approval ledger by themselves.
- The adapter builds its digest from server-side values. Client-supplied state, actor, digest, or
  approval fields are never trusted as authorization.
- The adapter owns an immutable-in-code commitment map and digest schema version approved with
  `D-PROCURE`. Header fields and each child-table field are enumerated explicitly; child rows retain
  document order and include stable row identity plus the selected business values. Decimal, date,
  datetime, boolean, null, empty-string, and link values use one documented canonical normalization
  before hashing. Derived totals are included together with their business inputs so a stale or
  manipulated calculation fails closed.
- Adding, removing, or reclassifying a mapped field requires a digest-schema revision, focused tests,
  and independent review. Contract tests assert the complete approved field tuples for Purchase Order,
  Purchase Order Item, Purchase Taxes and Charges, Payment Schedule, and any enabled subcontracting or
  supplied-item child table; a required field omitted from the map is a blocking test failure.

## WF-11 configuration handoff

Under the approved ownership exception above, the bounded TSK-602 patch in this slice supplies the
PO-only result and legacy-action gate. TSK-527 updates only the WF-11 Purchase Order route entry in
`.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json` and the allowlisted PO
Workflow/state/action fixture records assigned by the serialized integration owner. Material Request
is omitted from canonical fixtures; a reviewed legacy route is retained in place as inactive on a
populated upgrade and is absent on a clean install.

The post-migration verifier asserts exactly one intended active Purchase Order Workflow, no active
Material Request Workflow owned by this baseline, the accepted PO transition fingerprint, and preserved
historical Workflow Action/Version/Timeline rows. Any unrelated active PO Workflow, changed owned
fingerprint, or unresolved affected action stops the route without mutating configuration.

## Migration and recovery contract

Before configuration writes, TSK-602 inventories active PO/MR Workflows, referenced states/actions,
pending Workflow Actions, affected source documents, custom fields, and the expected configuration
fingerprint on the authorized target.

If any open PO or MR Workflow Action lacks an approved record-level disposition, migration stops before
changing either Workflow. It must not auto-complete, reject, cancel, close, delete, or recreate the
action. On a target with no open affected actions and no unrelated collision, repeated migration may
converge to PO-only Workflow ownership while retaining historical records. Recovery restores only the
captured prior configuration when the expected post-migration fingerprint still matches; submitted PO
effects are recovered only through native cancel/amend behavior.

For a populated baseline, the patch validates all Workflow Transition Tasks collisions before any
write, then saves one private, site-bound recovery file containing every persisted configuration field
of the reviewed PO/MR Workflows and the exact prior state of all five transition-task documents. The
recovery helper accepts only that complete snapshot schema and restores it only while the target
fingerprints still match. A clean install creates the transition tasks and PO fixture without creating
or requiring a legacy MR route or recovery snapshot.

The last bounded read-only inspection of `local.test` on 2026-09-26 found both
`Connect Material Request Blueprint` and `Connect Purchase Order Blueprint` active and no open PO/MR
Workflow Actions. This does not resolve the separately recorded shared-DEV inventory of three PO and two
MR actions because their identifiers and source documents are unavailable on this host.

## Automated evidence on `local.test`

Execution evidence on 2026-09-26:

- A files-inclusive site backup completed before migration at
  `sites/local.test/private/backups/20260926_153619-local_test-*`.
- The populated baseline fingerprints matched, the guarded patch completed, fixtures synchronized,
  and the `after_migrate` validator accepted PO target fingerprint
  `55478e4137b7fc0e3fdb550c2a889aaf12a5d6ca6afe333f3b4c2de59fb666db` plus the exact inactive
  legacy MR fingerprint.
- Focused approval controls (6), migration/recovery (10), PO adapter (13), print actions (9), setup and
  fixture/reset suites (28), and real-site PO lifecycle integration (3) passed.
- `uvx pre-commit run --all-files` passed every configured hook.
- Independent final code review found no remaining P0, P1, or P2 findings after Maker identity was
  added to the revision digest and both unit and persisted-owner-mutation integration regressions passed.
- The original full-app run reached 703 unit tests and exposed four pre-existing Stock Count failures:
  `Stock Count Adjustment.entry_type` omitted `Stock Reconciliation`, and the holding-transfer/yearly
  tests still expected retired auto-posting behavior. The owner authorized the bounded remediation
  below; after implementation, focused Stock Count tests and the clean full-app rerun pass.

- PO from native RFQ/Supplier Quotation references and every approved direct-PO route.
- Native supplier validation plus approved missing/invalid source-evidence behavior.
- Maker/Reviewer/Final Approver happy path with signed snapshots and native submission.
- Wrong role, self-approval, prior-actor reuse, multi-role precedence, permission revocation, and missing
  Employee/signature cases required by the accepted shared controls.
- Direct submit, REST/API, RPC, import/bulk, background invocation, workflow-state spoof, client-supplied
  approval fields, and post-approval update attempts.
- Return/correction/resubmit and Reject with no submitted PO or downstream effects.
- Mutation coverage for every commitment-critical header, child-row, tax, schedule, term, advance, and
  warehouse value.
- Retry, concurrent submit, and failure rollback proving one native submitted PO and no duplicated
  ordered quantity.
- Native cancel/amend and submitted PO mapping to Purchase Receipt and Purchase Invoice, including
  references, statuses, and pending quantities.
- Clean configuration application, populated upgrade, repeated migration, collision stop, unresolved
  pending-action stop, and fingerprint-guarded recovery.
- Focused tests, full app tests, and the pinned pre-commit command.

## Computer Use and documentation gates

After final automated gates and independent code review, a `browser_tester` uses distinct Maker,
Reviewer, Final Approver, unauthorized, and multi-role users on
`dev.erp.connectdiagnostics.test`. Acceptance covers visible actions, denied actions, Return/Reject,
mutation and re-approval, native Workflow Timeline, one native submission, cancel/amend, and native
Purchase Receipt/Purchase Invoice references and pending quantities.

Only after runtime acceptance may a `doc_writer` update the canonical procurement behavior/workflow
documentation. An independent reviewer must verify those docs against accepted code and runtime
evidence before this slice is accepted.

The 2026-09-26 browser-tester attempt stopped at capability discovery: this Codex host exposes no
desktop Computer Use, browser interaction, screenshot capture, isolated browser-profile control, or
video recording tool. No login, site mutation, test record, or simulated acceptance occurred. Resume
this gate from Step 0 on a host with Computer Use and successful-run video capture; final procurement
documentation remains gated until then.

## Authorized Stock Count gate remediation (2026-09-26)

The owner explicitly authorized continuing with the Stock Count failures that block the full-app gate;
the bounded decision is recorded as `D-STOCK-COMPAT-2026-09-26`. Broad `D-STOCK` remains open.
Repository history confirms that workflow checkpoint `d4db188` deliberately changed monthly holding
transfers and yearly stock adjustments from immediate posting to Workflow-owned drafts, but did not
update the adjustment-row Select options or the pre-change integration expectations. This remediation
completes that already-approved native-document boundary; it does not revive Stock Count as a posting
engine or change runtime generation logic.

The remediation owns exactly these additional files:

- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_count_adjustment/stock_count_adjustment.json`
  — add `Stock Reconciliation` to the allowed `entry_type` values and refresh the schema timestamp.
- `connect_diagnostics_core/api/erpnext/tests/test_stock_count_adjustments.py` — assert that monthly
  holding transfers and yearly Stock Reconciliations remain drafts, retain their Stock Count links and
  per-line warehouse/quantity targets, create no posting effects, and reject duplicate generation.
- this task record — preserve authorization, scope, test evidence, review outcome, and rollback notes.

This is a one-time cross-task ownership exception, not a reassignment of WF-04/05 or `STOCK-01-02`.
TSK-77 remains the Stock Count route owner in `branches.md`. To unblock the already-running TSK-527
integration gate, the primary TSK-527 integration owner exclusively owns the two implementation files
above on `feat/wf-tsk-527-procurement-approval`, based on parent
`feat/workflow-baseline-checkpoint-20260919`, and merges the accepted correction back through that
parent. The repository owner is the Stock business sign-off recorded in the compatibility decision;
no backup owner is assigned. Any concurrent TSK-77 edit to either file is a collision and stops this
remediation for reconciliation by the parent integration owner.

`connect_diagnostics_core/api/erpnext/stock_count.py`, Workflow fixtures, hooks, permissions, native
ERPNext controllers, and canonical documentation do not change in this remediation. Any runtime change
or additional file requires a renewed complete scope proposal before editing.

Acceptance treats this only as compatibility metadata/tests for an existing generator that terminates
at native documents; it does not activate retired Stock Count Workflow or posting behavior. The focused
test must prove a generated yearly document is the native `Stock Reconciliation`, remains `docstatus=0`
in `Stock Reconciliation Draft`, is linked from the adjustment row, and creates no Stock Ledger Entry
or GL Entry before native Workflow approval/submission. The monthly Stock Entry must likewise remain a
linked draft with no ledger/GL effects. Accepted target quantities, per-line warehouses, duplicate
generation, count-type and source-docstatus guards remain covered. The focused module and full app
suite must pass on `local.test`, the pinned pre-commit command must remain green, and independent code
review must have no open P0/P1/P2 finding.

The schema change is additive and requires no data backfill or patch. Before migration, the integration
owner records the site's current Select options and distinct adjustment value/link combinations and
takes a files-inclusive backup. Frappe's normal app-owned DocType JSON synchronization during
`bench --site local.test migrate` is the only authorized migration; the JSON `modified` value comes
from the site's configured timezone. After the first and repeated migrate, metadata must contain the
additive option while pre-existing row counts/values/links remain unchanged. A focused metadata
assertion covers the reviewed JSON contract used by clean installs. Any unexpected value, missing
native link, metadata-source collision, or concurrent file owner stops before further mutation.

Rollback is the Git revert of the Select-option and test changes before release. If yearly adjustment
rows using `Stock Reconciliation` have been created after deployment, removing that option is not a
valid live rollback: the TSK-527 integration owner must inventory distinct values plus every linked
native document and obtain a new Stock-owner recovery decision; the harmless additive option remains
until then. No rollback rewrites or deletes existing adjustment rows, Stock Reconciliations, Stock
Entries, Stock Ledger Entries, or GL Entries. Native drafts remain governed by their own Workflow and
later native submit/cancel lifecycle.

### Remediation evidence

- Files-inclusive pre-change backup:
  `sites/local.test/private/backups/20260926_160333-local_test-*`; recovery also used the earlier
  known-good pre-PO-migration backup `20260926_153619-local_test-*` while correcting an isolated
  worktree-path mismatch. The installed editable app mapping was restored to its original path and
  `Asset` existence was verified after recovery.
- Pre-migration metadata allowed only Material Transfer/Receipt/Issue and contained zero persisted
  Stock Count Adjustment rows. The app-owned JSON adds only `Stock Reconciliation`; no patch or
  backfill was introduced.
- Because this isolated worktree is not the Bench-installed app path, the first rehearsal proved the
  migration guard by stopping on the mismatched installed source. The site was restored from backup;
  the worktree migration plus targeted standard DocType reload was then repeated. Two consecutive
  worktree migrations passed, with Material Request inactive, Purchase Order active, `Asset` present,
  the additive Select option retained, and the zero-row inventory unchanged.
- Focused Stock Count adjustment integration tests pass 11/11. They prove native Stock Entry and Stock
  Reconciliation drafts, native Stock Reconciliation Draft state, Stock Count links, target quantities
  and per-row warehouses, duplicate/type/docstatus guards, and zero Stock Ledger Entry/GL Entry effects.
- The first full-app retry encountered transient Employee deadlocks and one order-sensitive PO assertion;
  the affected Employee tests passed 7/7 and PO integration passed 3/3 in isolation. The clean full-app
  rerun then passed 704 unit tests and 81 integration tests, including all 11 Stock Count tests.
- `uvx pre-commit run --all-files` passes every hook after the final test-only typing adjustment.
- Independent remediation review found no P0, P1, or P2 findings and marked the change READY.
