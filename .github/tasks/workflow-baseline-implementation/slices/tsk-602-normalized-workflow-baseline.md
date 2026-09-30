# TSK-602 — Normalize the workflow baseline

Status: automated gates passed; Computer Use acceptance blocked by unavailable desktop capability

2026-09-26 local.test result: the normalization patch and second migrate converged to ten active canonical Workflows. The first full suite exposed four stale Stock Count adjustment checks, which prompted the user-approved addendum below. After the additive option sync and test correction, pinned pre-commit and the full app suite pass (821 unit and 91 integration tests). The exact rehearsal and recovery evidence is in `evidence/local-test-2026-09-26/normalized-baseline-after.md`. Browser acceptance and final docs remain gated.

## User-approved Stock Count compatibility addendum — 2026-09-26

The user approved a narrow expansion to clear the four legacy integration failures without reviving a Stock Count Workflow or changing native posting ownership. This addendum supersedes only the earlier exclusion of Stock Count schema/test compatibility work.

Additional owned files and purpose:

- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_count_adjustment/stock_count_adjustment.json`: add the `Stock Reconciliation` value already written by `generate_stock_adjustment()` to the existing Select options; update its top-level `modified` timestamp in the verified Frappe system timezone. No field rename, removal, required-field change, or data rewrite.
- `connect_diagnostics_core/api/erpnext/tests/test_stock_count_adjustments.py`: replace immediate-posting assertions with assertions for draft Stock Entry and one draft native Stock Reconciliation, including row/warehouse mapping, Stock Count linkage, and duplicate-generation guard.
- This slice and `evidence/local-test-2026-09-26/normalized-baseline-after.md`: record the approved scope and final test/migration results.

`stock_count.py`, Workflow fixtures, posting controllers, other DocTypes, and accepted `docs/` do not change in this addendum. Clean/current migrate must sync the additive Select option; no backfill patch is required because the field is not required and no existing value is converted. Rollback is restoring the prior JSON option list and migrating, but only after checking for stored `Stock Reconciliation` rows; if such rows exist, removal is unsafe and must stop for owner disposition. Focused tests, full app tests, pinned pre-commit, an independent schema/code review, and then Computer Use acceptance remain the gates.

Operator rollback check for this Select option: in the approved site's Bench console, run `frappe.db.count("Stock Count Adjustment", {"entry_type": "Stock Reconciliation"})` and record the integer result. A query failure or any count above zero **stops** the JSON-option rollback; do not change or erase child rows to make it pass. With zero rows, restore the prior JSON options from Git, run the normal site migration, and verify the Select options after migration. This check concerns only the additive Stock Count Adjustment option; the separate Workflow rollback retains its own fingerprint/document guards.

## Goal

Converge the active app-owned Workflow fixture baseline on exactly ten standard ERPNext/HRMS
document routes: Stock Entry Material Transfer, Stock Reconciliation, Asset Movement, Journal
Entry, Sales Order, Sales Invoice Return/Credit Note, Purchase Order, Purchase Invoice, Payment
Entry, and Payroll Entry. Retire obsolete active ownership without deleting or fabricating
Workflow Action, Version, Comment, or document history.

TSK-600 Approval Snapshot and TSK-601 segregation-of-duties controls remain shared helpers and
are not business Workflow records.

## Starting evidence

- Integration base: `feat/workflow-baseline-checkpoint-20260919` at
  `e4abbc7e7de665ccbb4809196eb0af3af8c4f165`.
- Route implementations exist primarily as uncommitted changes in isolated `wf-tsk-*` worktrees;
  whole-worktree merges are prohibited because the fixture, hook, setup, patch-order, and task
  files overlap.
- `local.test` currently has eleven active Workflows: the ten desired DocType routes plus the
  obsolete Asset Disposal route. The desired normalized count is ten total Workflows. Material
  Request is present but inactive.
  Journal Entry is active on the site but absent from the integration-base fixture and manifest.
- The historical 2026-09-17 `local` audit recorded seven open Workflow Actions: two Material
  Request, three Purchase Order, and two retired Stock Count actions. The fresh 2026-09-26
  `local.test` query returned zero open actions. These are different sites/datasets, not a resolved
  contradiction. The seven historical actions remain unresolved production-migration evidence and
  receive the explicit policy below; zero rows on `local.test` authorizes no deletion elsewhere.
- Workflow fields already exist on all ten target DocTypes on `local.test`; source ownership and
  clean-install behavior must still be normalized.

## Route source decisions

| Canonical route | Source decision |
| --- | --- |
| Stock Entry — Material Transfer | Port only the direct-transfer adapter, tests, and guarded setup from TSK-521; remove Emergency Movement state/action behavior. |
| Stock Reconciliation | Retain one native Stock Reconciliation Workflow. Use TSK-77 only as freeze/native-boundary evidence; implement the normalized approval route without reviving Stock Count or a recount engine. |
| Asset Movement | Port the native Asset Movement adapter/tests/migration from TSK-523; exclude Equipment Assignment/Installation. |
| Journal Entry | Port the manual Journal Entry Workflow, minimum setup, shared-control adapter, tests, and guarded migration from TSK-603. Exclude unrelated generated-document expansion unless a focused test proves it is required for safe bypass. |
| Sales Order | Use the reviewed TSK-525 demo as test evidence only; remove its site flag/demo values and implement the normalized no-threshold route. |
| Sales Invoice — Return/Credit Note | Port the return/credit-note adapter/tests from TSK-526; do not invent write-off thresholds. |
| Purchase Order | Port the native Purchase Order adapter/tests/migration from TSK-527; exclude Material Request and unrelated stock-count changes. |
| Purchase Invoice | Use the TSK-528 trial as evidence; remove trial-only scope and implement the normalized native route. |
| Payment Entry | Use the TSK-529 POC as evidence only and implement `payment_entry_workflow.py`; no POC site flag, Timeline token scheme, voucher restriction, or parallel posting behavior may enter the baseline. |
| Payroll Entry | Port the Payroll Entry adapter/tests from TSK-530 only after the Journal Entry dependency is reconciled; never add a Salary Slip Workflow. |
| Shared TSK-600/601 | Use the TSK-531 lineage as the canonical source, reconcile later route-specific refinements once, and drop duplicate copies from other worktrees. |

Demo/trial/POC code for TSK-594, TSK-597, and TSK-598 is evidence, not a production source. Those
adapters must be redesigned under the normalized route decision or remain route-blocked; the
canonical fixture and history-safe migration may proceed without promoting their provisional
site flags, tokens, thresholds, or restricted voucher policy.

Empty legacy branch tips are not implementation sources. Patch-equivalent shared-control commits
from TSK-523/526/530/531 must be represented once only.

## Exact owned files

### Task, manifest, and evidence

- `.github/tasks/workflow-baseline-implementation/README.md`
- `.github/tasks/workflow-baseline-implementation/branches.md`
- `.github/tasks/workflow-baseline-implementation/decisions.md`
- `.github/tasks/workflow-baseline-implementation/verification.md`
- `.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json`
- `.github/tasks/workflow-baseline-implementation/slices/tsk-602-normalized-workflow-baseline.md`
- `.github/tasks/workflow-baseline-implementation/evidence/local-test-2026-09-26/normalized-baseline-before.md`
- `.github/tasks/workflow-baseline-implementation/evidence/local-test-2026-09-26/normalized-baseline-after.md`

Existing route slice/evidence files may be copied without changing their historical claims. They
are not promoted to accepted status by this integration task.

### Canonical configuration and setup

- `connect_diagnostics_core/fixtures/workflow.json`
- `connect_diagnostics_core/fixtures/workflow_state.json`
- `connect_diagnostics_core/fixtures/workflow_action_master.json`
- `connect_diagnostics_core/hooks.py`
- `connect_diagnostics_core/setup/workflow_fields.py`
- `connect_diagnostics_core/setup/tests/test_workflow_fields.py`
- `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py`
- `connect_diagnostics_core/setup/tests/test_workflow_reset.py`

### Shared controls

- `connect_diagnostics_core/api/frappe/approval_controls.py`
- `connect_diagnostics_core/api/frappe/approval_routes.py`
- `connect_diagnostics_core/api/frappe/tests/test_approval_controls.py`
- `connect_diagnostics_core/api/frappe/tests/test_approval_routes.py`

### Canonical route adapters and focused tests

- `connect_diagnostics_core/api/erpnext/stock_entry_workflow.py`
- `connect_diagnostics_core/api/erpnext/stock_reconciliation_freeze.py`
- `connect_diagnostics_core/api/erpnext/asset_movement_workflow.py`
- `connect_diagnostics_core/api/erpnext/journal_entry_workflow.py`
- `connect_diagnostics_core/api/erpnext/sales_order_workflow.py`
- `connect_diagnostics_core/api/erpnext/sales_invoice_credit_workflow.py`
- `connect_diagnostics_core/api/erpnext/purchase_order_workflow.py`
- `connect_diagnostics_core/api/erpnext/purchase_invoice_workflow.py`
- `connect_diagnostics_core/api/erpnext/payment_entry_workflow.py`
- `connect_diagnostics_core/api/hrms/payroll_entry_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_stock_entry_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_stock_entry_workflow_integration.py`
- `connect_diagnostics_core/api/erpnext/tests/test_stock_count_freeze.py`
- `connect_diagnostics_core/api/erpnext/tests/test_asset_movement_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_journal_entry_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_journal_entry_workflow_integration.py`
- `connect_diagnostics_core/api/erpnext/tests/test_sales_order_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_sales_order_workflow_integration.py`
- `connect_diagnostics_core/api/erpnext/tests/test_sales_invoice_credit_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_order_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_order_workflow_integration.py`
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_invoice_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_invoice_workflow_integration.py`
- `connect_diagnostics_core/api/erpnext/tests/test_payment_entry_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_payment_entry_workflow_integration.py`
- `connect_diagnostics_core/api/hrms/tests/test_payroll_entry_workflow.py`

### Forward migration and recovery

- `connect_diagnostics_core/patches/v1_0/normalize_workflow_baseline.py`
- `connect_diagnostics_core/patches/v1_0/rollback_normalize_workflow_baseline.py`
- `connect_diagnostics_core/patches/v1_0/tests/test_normalize_workflow_baseline.py`
- `connect_diagnostics_core/patches.txt`

Route-specific patch candidates were reviewed but not ported. The normalization patch owns the
additive compatibility fields, task-container normalization, activation, and retirement preflight
as one atomic migration boundary. No additional patch may enter TSK-602 without a revised file
list and a new plan review. The rollback module is an operator-run recovery tool and does not
appear in `patches.txt`.

## Explicit exclusions

- No Material Request, Asset Disposal, Salary Slip, Stock Count, Equipment, Emergency Freeze,
  Role/Scope Assignment, Delegation, self-approval-only, or baseline-freeze business Workflow.
- No deletion or rewrite of Workflow Action, Version, Comment, or document history.
- No ad hoc console writes and no shared DEV/UAT mutation.
- No stock-count DocType/schema revival, unrelated print-format changes, petty-cash UI changes,
  or new generated-Journal-Entry business routes.
- No threshold, amount, currency, or authority rule inferred from old planning documents.
- No manual edits to generated `setup/__init__.py` content.

## Migration and pending-document policy

1. Capture the ordered Workflow parent/state/transition snapshot, relevant Workflow State and
   Workflow Action Master vocabulary, open Workflow Actions, affected document state counts,
   workflow Custom Fields/Property Setters, source hashes, and manifest revision before mutation.
2. Route identity is the tuple `(document_type, workflow_name, normalized transition scope)`, where
   transition scope is the ordered `(state, action, next_state, role, condition)` allowlist. A
   canonical route may be applied only when no unrelated active Workflow or competing transition
   condition overlaps its DocType/scope. Because Frappe fixture synchronization is app-wide and
   unconditional after patches, any route collision stops the full migration before mutation;
   partial route activation would not be recoverable or deterministic.
3. Existing canonical app-owned Workflow rows may be updated only when their current fingerprint
   matches an allowlisted predecessor captured by this task.
4. Material Request and Asset Disposal are removed from active fixture ownership. The guarded
   patch may deactivate the exact app-owned Workflow only when there is no open Workflow Action
   and no non-terminal document requiring owner disposition. Otherwise the migration stops before
   mutation and leaves every route unchanged for owner disposition.
5. Legacy Emergency/Equipment/Freeze state and action masters are never deleted merely because
   they leave the fixture. Unreferenced vocabulary may remain as historical configuration.
6. Existing workflow-state and legacy freeze fields remain in the database when historical
   documents may reference them; removing them from setup ownership does not drop stored data.
7. Rollback restores only the captured predecessor configuration on a matching post-migration
   fingerprint. It never fabricates pending actions or approval events.
8. Repeated migrate/apply performs no additional mutations after convergence.

Historical pending policy: the two Material Request actions and their documents stay under the
legacy route until an authorized owner resolves them; the three Purchase Order actions remain on
the retained Purchase Order route and are not rewritten; the two retired Stock Count actions stay
legacy until authorized closure. On any target where those rows remain open, TSK-602 neither
deletes them nor removes referenced state/action vocabulary. It stops atomically before fixture
synchronization. Closed records are historical-only and remain auditable.

## Manifest revision

- New revision: `2026-09-26.normalized-workflow-baseline.1`.
- Integration-base predecessor SHA-256:
  `61a876fa98dba63dba709b439199b275061d73f58ec4578de6cc79e31f90257e`.
- Current `local.test` ordered Workflow/state/transition evidence SHA-256 before mutation:
  `ca2393b719d2459db8b8b7606eaca9e2f5ee757824a65cb65879a94ccc290ee2`.
- The new manifest is `dev-enabled` for `local.test` only until all gates pass. Git history and the
  before-evidence file preserve the WF-01–18 predecessor; no history is rewritten.
- Implementation must replace the old schema/status/route list, validate exactly ten route objects,
  and record the resulting manifest SHA-256 in `normalized-baseline-after.md`.

## Decision dependencies

- D-TARGET is resolved for this slice: code integration and migration rehearsal may mutate
  `local.test`; Computer Use may use `dev.erp.connectdiagnostics.test`; `local` and shared DEV/UAT
  remain read-only/out of scope.
- D-CORE/D-IDENTITY use approved revisions `D-CORE-2026-09-26` and
  `D-IDENTITY-2026-09-26` from TSK-531.
- CONFIG-DIRTY is resolved by isolated worktree preservation and the file-by-file port decisions in
  this plan; no child worktree is reset or broad-merged.
- CONFIG-PENDING uses the historical pending policy above. Actual production/shared-target cleanup
  remains blocked until a fresh snapshot and authorized record disposition exist.
- CONFIG-PAYMENT is resolved by `D-NORMALIZED-ROUTES-2026-09-26`: the POC was evidence only and the
  normalized production adapter uses request-bound native submit/cancel guards without its site
  flag, Timeline tokens, voucher restriction, or parallel posting behavior.
- TSK-603 is a stable Journal Entry dependency recorded in the parent task graph. Only the named
  manual-Journal-Entry files are eligible; generated-document expansion is excluded.

## Focused suite mapping

| Task | Canonical route | Focused test ownership |
| --- | --- | --- |
| TSK-590 | Stock Entry — Material Transfer | `test_stock_entry_workflow.py`, `test_stock_entry_workflow_integration.py` |
| TSK-591 | Stock Reconciliation | `test_stock_count_freeze.py` plus normalized fixture/migration tests; no Stock Count engine |
| TSK-592 | Asset Movement | `test_asset_movement_workflow.py` |
| TSK-593 / 603 | Journal Entry | `test_journal_entry_workflow.py`, `test_journal_entry_workflow_integration.py` |
| TSK-594 | Sales Order | `test_sales_order_workflow.py`, `test_sales_order_workflow_integration.py` |
| TSK-595 | Sales Invoice Return/Credit Note | `test_sales_invoice_credit_workflow.py` |
| TSK-596 | Purchase Order | `test_purchase_order_workflow.py`, `test_purchase_order_workflow_integration.py` |
| TSK-597 | Purchase Invoice | `test_purchase_invoice_workflow.py`, `test_purchase_invoice_workflow_integration.py` |
| TSK-598 | Payment Entry | production replacements for the two `payment_entry_approval_poc` tests; POC names cannot ship |
| TSK-599 | Payroll Entry | `test_payroll_entry_workflow.py` |

## Documentation impact after runtime acceptance

The `doc_writer` owns final changes to `docs/stock/behavior.md`,
`docs/stock/stock-reconciliation/README.md`, `docs/accounting/behavior.md`,
`docs/accounting/payment-entry/README.md`, `docs/selling/behavior.md`,
`docs/payroll/behavior.md`, and new module-wide `docs/assets/behavior.md` and
`docs/buying/behavior.md` only if accepted behavior is not already covered. An independent reviewer
must verify those files against accepted code/runtime evidence.

## Acceptance criteria

- The manifest and Workflow fixture identify exactly ten canonical business routes and one Workflow
  per target DocType/route.
- Journal Entry is present and runnable through native Workflow; Material Request, Asset Disposal,
  Stock Count, Salary Slip, Equipment, and Emergency Freeze have no active baseline Workflow.
- Fixture Workflow States and Action Masters are the exact transitive allowlist referenced by the
  ten workflows, except deliberately retained historical vocabulary which is not fixture-owned.
- Every legacy pending record has an explicit keep/migrate/authorized-close/historical-only
  classification; no event is invented or removed to satisfy tests.
- TSK-600/601 are shared code controls, not Workflow rows.
- Focused TSK-590–599 unit/integration suites pass on `local.test`.
- Migration rehearsals cover clean-equivalent apply, populated upgrade, collision stop, unresolved
  pending-document stop, partial-failure recovery, rollback fingerprint guard, and second migrate.
- Full app tests and pinned pre-commit pass.
- Independent review finds no history fabrication, silent site-owned overwrite, parallel posting
  engine, or Salary Slip Workflow.
- Computer Use acceptance covers all ten routes on `dev.erp.connectdiagnostics.test`, or records a
  blocked gate without claiming success.
- Canonical `docs/` is updated only after runtime acceptance and independently reviewed.

## Risks and rollback

- Shared files have high merge conflict risk; integration is file-by-file and serialized.
- Local site configuration is ahead of the integration source. Database state is evidence, never a
  substitute for code ownership or a source to export blindly.
- A preflight failure blocks fixture synchronization atomically. Independent code/tests/evidence
  may continue, but no partial configuration is presented as a successful migration.
- Rollback is configuration-only and fingerprint-guarded. Posted business documents use native
  cancel/amend/reversal behavior; external effects are not undone by database rollback.

## Gate sequence

Plan review -> file-by-file integration -> focused tests -> code review/fix/re-review -> repeated
`local.test` migrate and recovery rehearsal -> full app/pre-commit -> Computer Use -> final docs ->
documentation review -> accepted.
