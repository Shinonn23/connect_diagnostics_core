# Slice plan: TSK-530 Payroll Entry review and approval

Status: automated gates and code review complete; Computer Use blocked

## Goal and boundary

Apply the accepted Self-Approval/SoD contract to native HRMS `Payroll Entry` without introducing a
Salary Slip Workflow or another payroll/accounting engine. Actors are Maker (`HR User`), Reviewer
(`HR Manager`), Final Approver (`Accounts Manager`), and native Submit executor (`HR Manager`). Maker,
Reviewer, and Final Approver are distinct authenticated Users.

Review and approval remain docstatus 0. Only the final HR Manager Submit transition reaches docstatus
1 and invokes native HRMS Salary Slip creation. Later Salary Slip submission and accrual Journal Entry
creation remain native Payroll Entry operations.

Payroll cutoff/grouping, regular and off-cycle scope, correction/recovery, privacy and bank-handoff
semantics are governed by `D-PAYROLL-2026-09-26`: regular and off-cycle runs are included and native
HRMS correction/recovery is retained. Payroll Entry approval does not itself grant bank authority,
but native `Make Bank Entry` remains the handoff and may create its standard Bank/Cash Journal Entry.
This route never substitutes or duplicates that handoff with Payment Entry; a separately initiated
Payment Entry remains governed by its own Workflow and D-PAYMENT policy.

## Acceptance criteria

- Maker Send/Resubmit, Reviewer Review/Return, Final Approver Approve/Reject and HR Manager Submit use
  the exact central route declaration.
- Direct Payroll Entry submit, state/field spoof, RPC/import/background action, Administrator action,
  permission revocation, actor reuse, stale data, repeated action and grant replay fail closed.
- Review/Approve require signed Employee snapshots and three distinct Users.
- Native small and queued payroll paths create/submit Salary Slips only through Payroll Entry.
- Native accrual Journal Entries retain HRMS ownership. If the separately accepted Journal Entry
  Workflow is installed, its narrow generated-entry adapter applies independently; Payroll Entry
  never supplies a bypass or duplicates accounting.
- Native `Make Bank Entry` retains its Journal Entry and Payroll Entry references, does not create a
  duplicate Payment Entry, and remains subject to independently applicable Journal Entry controls.
- Native payroll cancel/recovery remains controller-owned and preserves Salary Slip/JE history.

## Exact worker-owned files

- `.github/tasks/workflow-baseline-implementation/slices/tsk-530-payroll-entry-review.md`
- `connect_diagnostics_core/api/hrms/payroll_entry_workflow.py`
- `connect_diagnostics_core/api/hrms/tests/test_payroll_entry_workflow.py`
- `connect_diagnostics_core/api/hrms/tests/test_payroll_entry_workflow_integration.py`

The route worker does not edit shared integration surfaces. After adapter review, the primary
serialized integration owner exclusively owns, in order:

- `.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json`
- `connect_diagnostics_core/fixtures/workflow.json`
- `connect_diagnostics_core/fixtures/workflow_state.json`
- `connect_diagnostics_core/fixtures/workflow_action_master.json`
- `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py`
- `connect_diagnostics_core/setup/tests/test_workflow_reset.py`
- `connect_diagnostics_core/hooks.py` (serialized integration surface)
- `connect_diagnostics_core/patches/v1_0/add_payroll_entry_approval_controls.py`
- `connect_diagnostics_core/patches/v1_0/rollback_add_payroll_entry_approval_controls.py`
- `connect_diagnostics_core/patches/v1_0/tests/test_add_payroll_entry_approval_controls.py`
- `connect_diagnostics_core/patches.txt` (serialized migration ordering surface)
- final `docs/payroll/` behavior/workflow documentation after runtime acceptance

The primary integration owner also made a behavior-preserving final-gate repair in
`connect_diagnostics_core/api/frappe/approval_controls.py` and
`connect_diagnostics_core/api/frappe/tests/test_approval_controls.py`: non-finite float detection now
uses `math.isfinite`, and the tests use correctly typed Documents with narrow invalid-input/frozen
snapshot typing suppressions. No approval semantics changed.

Installed HRMS/ERPNext source, Salary Slip Workflow/direct submit, duplicate payroll posting, payment
voucher design, delegation, named users and amount thresholds are excluded.

## Verified HRMS v16 boundaries

Installed source under `hrms/payroll/doctype/payroll_entry/payroll_entry.py` establishes these native
boundaries, which the adapter and integration tests must preserve:

- `PayrollEntry.before_submit()` performs native pre-submit validation; `on_submit()` calls
  `create_salary_slips()` and is the earliest controller-owned batch side-effect boundary.
- `create_salary_slips()` and `create_salary_slips_for_employees()` create draft Salary Slips either
  synchronously or in a queued worker and then set `salary_slips_created`.
- `submit_salary_slips()` and `submit_salary_slips_for_employees()` submit the batch under
  `frappe.flags.via_payroll_entry`, tolerate per-slip validation failures, and call
  `make_accrual_jv_entry()` for the successfully submitted subset.
- `make_accrual_jv_entry()` and its shared `make_journal_entry()` helper create the native accrual
  Journal Entry and link it back to Salary Slips.
- `make_bank_entry()` creates the native Bank/Cash Journal Entry from submitted Salary Slips;
  `has_bank_entries()` detects the downstream reference. It does not require or create Payment Entry.
- The existing Salary Slip `before_submit` hook remains the universal direct-submit guard. Payroll
  Entry button visibility is not an authorization boundary.

The adapter guards native Payroll Entry submission after approved Workflow evidence is rechecked.
Once the document is submitted, later native Salary Slip/accrual/bank operations act on that approved,
immutable batch and retain their own controller permission and retry behavior. Payroll supplies no
Journal Entry bypass and trusts neither title, remarks, client flags nor `ignore_permissions` as
approval evidence. Any separately installed TSK-603 adapter composes independently and requires its
own accepted evidence.

## Design

- Consume `approval_routes.get_route("payroll_entry")`; do not restate roles/actions.
- Native Workflow owns transitions. Synchronous transition tasks capture Maker, Reviewer and Final
  Approver and clear stale evidence on Return.
- Approval-field writes require the shared one-use grant; adapter validation blocks API/import edits.
- At Review, Approve and Submit, lock and reread the Payroll Entry row. Submit requires approved
  persisted state, current submit permission, complete signed snapshots and matching digest before
  HRMS `before_submit`/`on_submit` runs.
- Bind digest to server-read company, payroll frequency, branch/department/designation/project,
  posting/start/end dates, payable/cost-center/accounting-dimension facts, currency/exchange rate,
  bank/account settings, employee selection filters and the deterministic selected-employee/slip
  revision facts required by the native Payroll Entry.
- Keep all review/approval states at docstatus 0. Final Submit alone moves to docstatus 1, allowing
  native synchronous or queued Salary Slip creation. Existing `Salary Slip.before_submit` continues
  to require `frappe.flags.via_payroll_entry`.
- Do not infer generated Journal Entries from `user_remark`, title or `ignore_permissions`. TSK-530
  neither overrides `PayrollEntry.make_journal_entry()` nor grants Journal Entry authority. Tests
  prove the native accrual and Bank/Cash JE calls remain owned by HRMS. If TSK-603 is installed later,
  its independently reviewed generated-entry adapter composes through Frappe's extension mechanism.

## Workflow and migration

Replace the stale two-actor blueprint with Draft → Pending Review → Reviewed → Approved → Submitted,
plus Returned and Rejected paths, using the exact central actions/states. Maker Send/Resubmit permits
self action; Review and Approve set `allow_self_approval=0`.

The integration migration fingerprints the named Workflow, states/actions/tasks, approval fields,
the exact HR User/Accounts Manager `Custom DocPerm` rows, pending Workflow Actions and pending Payroll
Entries. Any open legacy Workflow Action, pending
approval, or in-flight/queued Salary Slip creation/submission job stops migration for owner
disposition; migration never completes/remaps/deletes actions, rewrites job status or fabricates
history. It accepts only the reviewed legacy or desired shape, stops on another active/site-owned
collision, preserves history and converges on rerun. Permission creation is in the same migration
transaction as Workflow activation; recurring setup does not rewrite site-owned permission rows.
Rollback stops if the new route has created an action or launched payroll processing; otherwise it
requires and removes the exact migration-owned permission rows and restores the prior route only
while the expected post-migration fingerprint matches. Reusable Workflow State, Workflow Action
Master, transition-task and Custom Field companions intentionally remain inert after rollback.
Submitted or partially processed payroll recovers through native HRMS status/error/cancel/retry
procedures, never direct database edits.

## Checkpoint and integration sequencing

The adapter and serialized integration are implemented together in the dedicated TSK-530 worktree.
Hook, fixture, manifest, migration, recovery and patch-ordering changes received an independent code
review before Computer Use. Any future TSK-603 integration remains separately reviewed for
composition with this Payroll route.

## Tests and acceptance

Focused unit/integration tests on `local.test` cover distinct actors, self-approval denial,
Return/Reject/Resubmit, critical mutation, direct submit/RPC/import/background/Admin denial,
permission and evidence rechecks, native synchronous/queued boundaries, direct Salary Slip denial,
generated accrual JE, native Bank/Cash JE without Payment Entry duplication, and native
cancel/recovery. Fixture/migration tests cover collision, exact permissions, rerun and rollback.

After full automated gates and code review, Computer Use uses distinct HR User, HR Manager, Accounts
Manager, unauthorized and multi-role sessions on `dev.erp.connectdiagnostics.test`, verifying visible
actions, generated Salary Slips, payroll status and Timeline evidence. Queue/generated-JE internals
remain automated evidence. Final documentation follows runtime acceptance and independent review.

## Current implementation evidence

- Added the Payroll Entry adapter with a versioned, privacy-preserving critical digest, signed
  Employee checks, distinct Maker/Reviewer/Final Approver validation, one-use native submit
  provenance, row-lock/reread verification, and fail-closed stale/tampered/direct-submit checks.
- The critical digest includes set-based revision fingerprints for selected Employee records,
  applicable submitted Salary Structure Assignments, referenced Salary Structures, Income Tax Slabs,
  Salary Components and Payroll Settings. Only the deterministic digest is persisted; salary amounts
  and employee pay details are not copied into Workflow evidence.
- Installed the serialized route on `local.test`; migration rerun converged, permission collision and
  rollback tests passed, and the exact HR User/Accounts Manager grants are migration-owned rather
  than recurring setup mutations.
- Fifty-five focused tests passed on `local.test`: 51 unit/configuration/migration tests and four
  native integration tests. The end-to-end test rejected direct submit, completed the three-person
  route, created/submitted the Salary Slip, created the native accrual JE, created a native Bank/Cash
  JE without a Payment Entry, and exercised native cancellation cleanup.
- The shared approval-controls suite passed 24/24 after the behavior-preserving final-gate repair.
  The pinned repository-wide pre-commit command then passed every applicable hook, including Ruff,
  formatting, JSON validation, `ty`, Semgrep, and dependency audit.
- Independent final code review found no P0/P1/P2 findings. Its non-blocking observation is that the
  revision query conservatively includes historical submitted assignments through the batch end date;
  this fails closed by over-invalidating rather than permitting stale approval. Rollback intentionally
  retains inert companion configuration while revoking the active route permissions.
- After the final focused test, `local.test` still reported the exact desired Workflow and exact
  least-privilege grants: HR User read/write/create and Accounts Manager read/write, with every other
  permission flag disabled.
- A fresh Computer Use retry after the green final gate stopped at Step 0 on 2026-09-27 because tool
  discovery returned `directInteractionTools=[]`: this host exposes no desktop click/type, Chrome
  profile, screenshot or recording capability. No browser, user session or route was opened and no
  site record was mutated. Host reachability and every visible role scenario therefore remain
  untested, and successful-run video is unavailable. Final canonical documentation remains deferred
  until runtime acceptance succeeds. TSK-603 remains independent and does not block this route.
