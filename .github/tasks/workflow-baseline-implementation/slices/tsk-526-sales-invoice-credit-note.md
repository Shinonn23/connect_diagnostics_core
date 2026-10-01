# Slice plan: TSK-526 Sales Invoice Credit Note approval

Status: browser acceptance blocked — automated gates and independent code review passed

Worker evidence (2026-09-26): Added the bounded Sales Invoice Credit Note adapter and focused
unit/integration test files. The adapter scopes only persisted returns against submitted original
invoices, computes a server-built critical digest, consumes central one-use field-write grants,
captures/reset actors at native transitions, rejects evidence tampering, and blocks stale/direct
submission before native effects. Integration hooks, fixtures, migration, and runtime site tests
remain owned by the serialized integration owner.

Primary-agent evidence (2026-09-26): The upstream actor contract was retained unchanged. Eighty-five
focused tests passed on `local.test`; the installed fixture and migration fingerprint still matched
after the full test run; Ruff, formatting, JSON, compile and diff checks passed; and independent code
review found no remaining P0/P1/P2 finding. The repository's full pinned `pre-commit` command was not
available in this environment and was not claimed as passed.
Computer Use acceptance is blocked because the current desktop session exposes no browser-control or
recording capability. No Desk actions, site mutations, screenshots, or video were claimed. Resume at
the browser acceptance gate on `dev.erp.connectdiagnostics.test`; final documentation remains gated
until that runtime acceptance succeeds.

## Goal and boundary

Apply the accepted Self-Approval/SoD contract to an unsubmitted native ERPNext `Sales Invoice` Credit
Note whose persisted `is_return == 1` and `return_against` names a submitted original invoice. Native
effects occur only at the final Credit Note submit. Ordinary Sales Invoices remain on their native
path. Physical return, price-only/retained credit, write-off, refund, period and evidence semantics
are governed by `D-CREDIT-2026-09-26`: physical return and price-only credit are included; AR
write-off and refund execution are excluded.

The actors are Maker (`Sales User`), Reviewer (`Sales Manager`), Final Approver
(`C-Level Approver`), and native Post/Cancel executor (`Sales Manager`). Maker, Reviewer, and Final
Approver are distinct authenticated Users even when one User has multiple roles.

## Acceptance criteria

- Maker can Send and Resubmit; Reviewer can Review or Return; Final Approver can Approve or Reject.
- Protected Review/Approve require the shared interactive actor guard and signed Employee snapshot.
- Direct submit, state/field spoof, RPC/import/background action, Administrator action, permission
  revocation, actor reuse, stale data, repeated action and grant replay fail closed.
- Approval is bound to the original invoice plus current credit-note accounting, tax and item facts.
- Ordinary Sales Invoices are not trapped by this route.
- Native Sales Invoice submit/cancel owns GL, Stock Ledger, tax, outstanding and return effects.
- Return/Reject create no native posting effect; correction requires Resubmit and fresh approval.

## Exact worker-owned files

- `.github/tasks/workflow-baseline-implementation/slices/tsk-526-sales-invoice-credit-note.md`
- `connect_diagnostics_core/api/erpnext/sales_invoice_credit_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_sales_invoice_credit_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_sales_invoice_credit_workflow_integration.py`

The route worker does not edit shared integration surfaces. After adapter review, the primary
serialized integration owner exclusively owns, in this order:

- `.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json`
- `connect_diagnostics_core/fixtures/workflow.json`
- `connect_diagnostics_core/fixtures/workflow_state.json`
- `connect_diagnostics_core/fixtures/workflow_action_master.json`
- `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py`
- `connect_diagnostics_core/setup/tests/test_workflow_reset.py`
- `connect_diagnostics_core/hooks.py` (serialized integration surface)
- `connect_diagnostics_core/patches/v1_0/add_sales_invoice_credit_approval_controls.py`
- `connect_diagnostics_core/patches/v1_0/rollback_add_sales_invoice_credit_approval_controls.py`
- `connect_diagnostics_core/patches/v1_0/tests/test_add_sales_invoice_credit_approval_controls.py`
- `connect_diagnostics_core/patches.txt` (serialized migration ordering surface)
- final `docs/accounts-receivable/` behavior/workflow documentation after runtime acceptance

Installed Frappe/ERPNext source, ordinary Sales Invoice behavior, payment/refund execution, named-user
mapping, delegation and amount thresholds are excluded.

## Design

- Consume `approval_routes.get_route("sales_invoice_credit_note")`; do not restate roles/actions.
- Native Workflow owns transitions. Synchronous transition tasks capture Maker at Send/Resubmit,
  Reviewer at Review, Final Approver at Approve, and clear stale evidence on Return.
- Every approval-field write uses the shared one-use exact-document/route/action grant. Adapter
  validation rejects inserted or changed approval fields without consuming that grant.
- At Review and Approve, lock and reread the Credit Note. At Post, lock the source invoice before
  the Credit Note row, reread persisted state/evidence and reject
  stale state or actor reuse. At Post, require approved persisted state, current submit permission,
  complete signed snapshots and matching critical digest before native controller effects.
- Build the digest from server-read `is_return`, `return_against`, company, customer, currency,
  posting date/time, due date, credit-note reason, conversion rates, discounts, taxes/charges,
  totals and ordered item accounting/stock facts including item, quantity, UOM, rate, amount,
  warehouse, income account, cost center, project, serial/batch references and original-invoice links.
  Bind settlement inputs including advance allocation, POS payment rows, write-off, change account,
  loyalty and discount fields while excluding auto-derived base totals that ERPNext normalizes.
  Also bind immutable server-read original invoice identity/company/customer/currency/docstatus facts.
- The route predicate is checked from persisted values at every boundary. A forged return flag without
  a submitted `return_against` cannot enter or post through the route.

## Workflow and migration

Replace the stale two-actor blueprint with Draft → Pending Review → Reviewed → Approved → Submitted,
plus Returned/Rejected correction and native Cancel paths, using the exact central actions/states.
Maker Send and Resubmit allow self action; Review, Approve, Post and Cancel set
`allow_self_approval=0`. Cancel remains the native ERPNext action, with a Sales Manager transition
authorization and server-side cancellation guard. Ordinary invoices use explicit Accounts User/Accounts Manager passthrough
transitions and never enter a Credit state.

The integration migration fingerprints the named Workflow, states/actions/tasks, approval fields,
pending Workflow Actions and affected draft documents. Any open legacy Workflow Action or affected
pending document stops migration for owner disposition; migration never completes, remaps or deletes
an action and never fabricates history. It accepts only the reviewed legacy or exact desired shape,
stops on another active/site-owned collision, preserves history, and converges on rerun. Rollback
stops if a post-migration Workflow Action or document has used the new route; otherwise it restores
the captured prior route only while the post-migration fingerprint still matches. Posted credit notes
recover through native cancel/reversal.

## Tests and acceptance

Focused unit/integration tests on `local.test` cover the Sales User Maker; three distinct actors; multi-role
self approval; Return/Reject/Resubmit; critical-field mutation; original-invoice mismatch; ordinary
invoice bypass; direct submit/RPC/import/background/Admin denial; permission revoke; retry/concurrency;
native GL/outstanding/stock effects; and native cancel/reversal. Fixture and migration tests cover
collision, rerun and rollback.

After full automated gates and code review, Computer Use must use distinct Maker, Reviewer, Final
Approver, unauthorized and multi-role sessions on `dev.erp.connectdiagnostics.test`, including an
ordinary invoice control. That gate is currently blocked because this host has no Computer Use or
recording tool. Final documentation follows successful runtime acceptance and independent review.
