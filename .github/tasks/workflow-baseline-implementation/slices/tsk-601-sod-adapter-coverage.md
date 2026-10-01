# Slice plan: TSK-601 Self-Approval/SoD adapter coverage

Status: shared phase accepted; domain adapter coverage active

## Goal and approved decision

Apply the shared TSK-600/601 approval contract to the ten approved protected routes without creating
a second workflow or posting engine. The approved identity and role contract is
`D-IDENTITY-2026-09-26` in `../decisions.md`.

Maker Send/Resubmit remains available. Protected Review and Approve actions require distinct enabled
Users, current role/permission, current native Workflow state, and server-captured signed snapshots.
Each adapter rechecks approval-bound critical data immediately before the native submit effect.
Administrator, service users, direct RPC, state spoofing, import, queue, and direct submit receive no
business-approval bypass.

## Route ownership and exact files

### Shared declaration and setup — `feat/wf-tsk-531-approval-controls`

- `.github/tasks/workflow-baseline-implementation/decisions.md`
- `.github/tasks/workflow-baseline-implementation/slices/tsk-601-sod-adapter-coverage.md`
- `connect_diagnostics_core/api/frappe/approval_controls.py`
- `connect_diagnostics_core/api/frappe/tests/test_approval_controls.py`
- `connect_diagnostics_core/api/frappe/approval_routes.py`
- `connect_diagnostics_core/api/frappe/tests/test_approval_routes.py`
- `connect_diagnostics_core/setup/workflow_fields.py`
- `connect_diagnostics_core/setup/tests/test_workflow_fields.py`
- `connect_diagnostics_core/setup/print_action_fields.py`
- `connect_diagnostics_core/setup/tests/test_print_action_fields.py`

This phase declares route names, protected actions, expected states and actor roles; adds the shared
interactive-role guard and one-use opaque approval-field write grant; supplies hidden,
read-only, no-copy User/digest fields; and supplies signed Review/Approve snapshot fields. Existing
`setup/workflow_fields.py` is extended, not replaced, and is already called by
`setup.__init__.apply_all()` on install/migrate. Existing `setup/print_action_fields.py` is extended,
not replaced, and is already registered directly in `hooks.py` for install/migrate. Therefore neither
`setup/__init__.py` nor `hooks.py` changes in this shared phase. Focused tests assert both existing
configuration entry points remain effective. This phase does not register domain hooks, edit Workflow
fixtures, mutate a site, or implement a domain submit guard.

### Stock Entry Material Transfer — `feat/wf-tsk-521-transfer`

- existing owned Stock Entry adapter, tests, Workflow fixtures, setup fields, migration/recovery,
  `hooks.py`, `patches.txt`, route manifest and TSK-590 record listed in
  `slices/tsk-590-warehouse-transfer.md`

The current dirty work is preserved and reconciled with the accepted shared commit; this plan does
not overwrite or duplicate it.

### Stock Reconciliation — `feat/wf-tsk-77-stock-count`

- `connect_diagnostics_core/api/erpnext/stock_reconciliation_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_stock_reconciliation_workflow.py`
- `connect_diagnostics_core/fixtures/workflow.json`
- `connect_diagnostics_core/fixtures/workflow_state.json`
- `connect_diagnostics_core/fixtures/workflow_action_master.json`
- `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py`
- `connect_diagnostics_core/hooks.py`
- one forward collision-aware route migration, matching rollback, focused migration tests, and
  `connect_diagnostics_core/patches.txt`
- route manifest/task evidence and final `docs/stock/` documentation after acceptance

### Asset Movement — `feat/wf-tsk-523-asset-movement`

- the exact adapter, test, fixture, setup, hook, migration/recovery and documentation files already
  recorded in `slices/tsk-523-asset-movement.md`

The existing uncommitted Asset work remains exclusively owned by that route and is not edited from
the shared branch.

### Manual Journal Entry — `feat/wf-tsk-603-journal-entry`

- `connect_diagnostics_core/api/erpnext/journal_entry_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_journal_entry_workflow.py`
- `connect_diagnostics_core/fixtures/workflow.json`
- `connect_diagnostics_core/fixtures/workflow_state.json`
- `connect_diagnostics_core/fixtures/workflow_action_master.json`
- `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py`
- `connect_diagnostics_core/hooks.py`
- one forward collision-aware route migration, matching rollback, focused migration tests, and
  `connect_diagnostics_core/patches.txt`
- route manifest/task evidence and final `docs/accounting/` documentation after acceptance

System-generated Journal Entries from ERPNext/HRMS are excluded and must retain their native path.

### Sales Order credit approval — `feat/wf-tsk-525-sales-credit`

- `connect_diagnostics_core/api/erpnext/sales_order_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_sales_order_workflow.py`
- the three Workflow fixture files and fixture blueprint tests
- `connect_diagnostics_core/hooks.py`
- one route migration, rollback, focused migration tests and `patches.txt`
- route manifest/task evidence and final `docs/sales/` documentation after acceptance

### Sales Invoice Credit Note — `feat/wf-tsk-526-credit-writeoff`

- `connect_diagnostics_core/api/erpnext/sales_invoice_credit_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_sales_invoice_credit_workflow.py`
- the three Workflow fixture files and fixture blueprint tests
- `connect_diagnostics_core/hooks.py`
- one route migration, rollback, focused migration tests and `patches.txt`
- route manifest/task evidence and final `docs/accounts-receivable/` documentation after acceptance

Only return/credit-note Sales Invoices consume this route; ordinary Sales Invoices retain their
native path.

### Purchase Order — `feat/wf-tsk-527-procurement-approval`

- `connect_diagnostics_core/api/erpnext/purchase_order_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_order_workflow.py`
- the three Workflow fixture files and fixture blueprint tests
- `connect_diagnostics_core/hooks.py`
- one route migration, rollback, focused migration tests and `patches.txt`
- route manifest/task evidence and final `docs/procurement/` documentation after acceptance

Material Request is not a protected route in this slice. Native Purchase Order item links may supply
trusted requester provenance; a manual Purchase Order falls back to the server-captured maker.

### Purchase Invoice — `feat/wf-tsk-528-ap-payment-handoff`

- `connect_diagnostics_core/api/erpnext/purchase_invoice_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_purchase_invoice_workflow.py`
- the three Workflow fixture files and fixture blueprint tests
- `connect_diagnostics_core/hooks.py`
- one route migration, rollback, focused migration tests and `patches.txt`
- route manifest/task evidence and final `docs/accounts-payable/` documentation after acceptance

### Payment Entry — `feat/wf-tsk-529-payment-approval`

- `connect_diagnostics_core/api/erpnext/payment_entry_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_payment_entry_workflow.py`
- the three Workflow fixture files and fixture blueprint tests
- `connect_diagnostics_core/hooks.py`
- one route migration, rollback, focused migration tests and `patches.txt`
- route manifest/task evidence and final `docs/payments/` documentation after acceptance

The existing two-actor Workflow is replaced by Maker → Accounts Manager Review → C-Level Final
Approval → Accounts Manager native Post.

### Payroll Entry — `feat/wf-tsk-530-payroll-review`

- `connect_diagnostics_core/api/hrms/payroll_entry_workflow.py`
- `connect_diagnostics_core/api/hrms/tests/test_payroll_entry_workflow.py`
- the three Workflow fixture files and fixture blueprint tests
- `connect_diagnostics_core/hooks.py`
- one route migration, rollback, focused migration tests and `patches.txt`
- route manifest/task evidence and final `docs/payroll/` documentation after acceptance

Payroll Entry is Maker → HR Manager Review → Accounts Manager Final Approval → HR Manager native
Submit. Salary Slips remain submit-through-Payroll-Entry only; native payroll accrual Journal Entries
must not be trapped by the manual Journal Entry route.

## Shared route contract

Shared declaration/setup evidence (2026-09-26): `approval_routes.py` declares exactly the ten approved
routes, scopes, actor roles, native action/state names, exclusions and distinct-actor requirement.
`workflow_fields.py` adds hidden, read-only, allow-on-submit, no-copy User and digest evidence fields
using the existing TSK-521-compatible names. `print_action_fields.py` supplies checked/authorized
signed Employee scalar snapshots for every approved route; no unauthenticated serialized snapshot
blob is added. `approval_controls.py` provides the reviewed interactive actor guard and one-use,
exact-document/route/action field-write grant stored only in `frappe.local`; it owns no lock or native
effect. Focused `local.test` results are 22/22 approval-control tests, 4/4 approval-route tests, 2/2
workflow-field tests and 5/5 print-action-field tests passed with this worktree first on `PYTHONPATH`.
Ruff check/format, focused `ty` and `git diff --check` passed. No route is runtime-active from this
phase.

Independent code review accepted the shared phase with no remaining P0/P1 findings. Asset Movement
uses `Stock User` as the executable Maker role; that User may also be the custodian, but custodian
status alone grants no Workflow role or document permission.

The central declaration contains, for each route:

- document type and approved route scope;
- Maker, Reviewer, Final Approver and execution roles;
- Maker Send/Resubmit, protected Review, protected Approve and execution action names;
- expected source and next states for protected actions;
- whether three distinct actors are required;
- explicit treatment of Administrator/service actors and generated-document exclusions.

Adapters consume this declaration but own document-specific critical payloads, trusted source
provenance, row locking and native-effect boundaries. Native Workflow remains authoritative for
transition exposure and Workflow Action remains authoritative for pending actions.

## Snapshot persistence and tamper boundary

The setup-managed fields are storage and UI hardening, not authority by themselves. The shared helper
mints an opaque request-local object capability only while a declared synchronous transition task
captures Maker, Reviewer, Final Approver, digest and signed Employee snapshot values. Each adapter's
validate hook rejects inserted or changed approval fields without that exact object-identity
capability. Direct Desk/API/import/state-field writes cannot mint it.

At protected Review/Approve, the adapter locks and rereads the source row, checks expected persisted
state, current declared role and permission, then captures the snapshot in the same transaction as
the native transition save. At native Post/Submit, the adapter locks and rereads persisted state,
actor fields, signed snapshots and digest, recomputes its server payload, and only then lets the native
controller execute. The execution role may equal the Reviewer, but Reviewer, Final Approver and Maker
remain distinct and the Final Approval is rechecked after the execution transition begins.

Protected Review/Approve rejects Guest, Administrator, missing HTTP request, background/import/service
execution, missing or ambiguous Employee identity and missing signature. Tests cover direct field
mutation and capability forgery in addition to workflow RPC and state spoofing. Privileged database or
server-console mutation is operational access outside the application actor model and is never
recognized as approval evidence.

## Sequencing and shared-file integration

1. Accept the shared declaration/setup slice and commit it atomically on TSK-531.
2. Each route branch stacks that exact dependency commit and implements only its declared adapter.
3. `hooks.py`, Workflow fixtures, fixture tests, route manifest and `patches.txt` are shared integration
   surfaces. Route branches edit them independently but merge into the parent integration branch one
   at a time, rerunning fixture, migration and full-app gates after every merge.
4. Existing dirty TSK-521 and TSK-523 work is reviewed and integrated by its current owner; no other
   worker writes those worktrees.
5. Computer Use begins only after the integrated automated gates pass. Final documentation follows
   runtime acceptance and receives independent review.

## Automated acceptance matrix

Every route covers maker Send/Resubmit, distinct Reviewer, distinct Final Approver, wrong role,
multi-role self approval, reviewer/final reuse, direct `apply_workflow` RPC, direct submit/state spoof,
permission revocation, critical-field staleness, repeated action, Return/Reject and native side-effect
ownership. It also covers Administrator, Guest, no-request/background protected action, direct
approval-field mutation, capability forgery and transaction rollback. Tests run on `local.test` only.

Computer Use uses separate Maker, Reviewer, Final Approver, unauthorized and multi-role sessions for
each user-visible route. It verifies visible/hidden actions, Send, Review, Approve, Return/Reject,
changed-data invalidation, direct-action denial surfaced to the user, final native effect and Timeline
evidence. Manual Journal Entry generated-entry exclusions and Payroll internal side effects receive
automated coverage because they are not safely reproducible as business UI actors.

Manual Journal Entry additionally proves generated ERPNext/HRMS entries are unaffected. Sales Invoice
proves ordinary invoices are unaffected. Purchase Order proves linked Material Request provenance and
manual fallback. Payroll proves Salary Slip and accrual Journal Entry internals remain native.

## Migration, rollback and exclusions

Each route migration captures its active Workflow, referenced states/actions/tasks, approval fields,
pending Workflow Actions and affected pending documents. It accepts only the reviewed legacy or exact
desired fingerprint, stops on unrelated collisions, preserves Workflow Action/Version/Timeline history,
and converges on repeated migrate. Rollback restores prior configuration only while the expected
post-migration fingerprint matches. Posted effects recover through native cancel/reversal.

Excluded: Delegation, Backup Approver, Role/Scope Assignment, named users, amount thresholds, new
posting engines, broad System Manager bypass, Salary Slip Workflow, Material Request approval, Asset
Disposal, and changes to installed Frappe/ERPNext/HRMS source.
