# TSK-77 — Native Stock Reconciliation Approval

Status: POC mechanics accepted; production implementation blocked on owner policy

## Local demo authorization — 2026-09-26

The owner authorized a non-production proof of concept on `local.test` before final business
policy is available. This does not resolve D-STOCK or D-IDENTITY and must not be promoted as the
production policy.

- Demo maker: a distinct user with `Stock User` plus `Stock Manager` only because the installed
  native DocPerm grants Stock Reconciliation Create exclusively to `Stock Manager`.
- Demo sender: a distinct user with `Stock User` plus `Stock Manager`. The existing Send transition
  incorrectly has `allow_self_approval = 0`, so Frappe prevents the owner from sending; native
  DocPerm also grants Read only to Stock Manager, so a Stock User-only sender cannot open/action it.
- Demo approver/poster: a distinct user with `Stock Manager`.
- The existing two-stage native route is used unchanged: Send for Review → Approve → Post.
- The POC does not decide Full/Cycle/Recount eligibility, thresholds, monthly/annual policy,
  delegation, multi-role precedence, or final production authority.
- No repository runtime/configuration file changes are in POC scope. Site mutations are limited to
  reversible `_Test` users/master data and Stock Reconciliation evidence on `local.test`.
- Success proves only that the existing native Workflow can gate a real Stock Reconciliation and
  that ERPNext creates the expected SLE/GL effects. It does not prove stale-approval, shared SoD,
  safe migration, retry/concurrency, production permissions, or final workflow acceptance.
- The elevated POC sender technically can approve/post because native self-approval checks only the
  document owner. Using a separate approver demonstrates the intended path but does not prove that
  the current configuration enforces sender-versus-approver SoD.

Before production implementation resumes, explicitly re-open the owner questions for maker,
reviewer, final approver/poster, multi-role/self-approval, delegation/backup, service identities,
enabled count types, adjustment cadence/cutoff/exclusions, recount authority, and adjustment
account policy.

The production permission design must also decide whether Stock User receives code-managed Create
and Read/Write permission or whether makers/senders are intentionally Stock Managers. The POC must
not silently promote its dual-role maker/sender as the final least-privilege design.

The production Workflow must also change the maker's non-approval Send transition to permit the
owner to send their own draft; the extra POC sender is evidence of the current configuration gap,
not an intended business role.

The target site initially contains no Stock Ledger Entry. ERPNext therefore treats its first Stock
Reconciliation as opening stock and requires a Balance Sheet difference account. The POC uses the
existing `Temporary Opening - TCP1` account for that first-entry condition; this is test-fixture
behavior, not the production adjustment-account decision.

## POC execution finding — 2026-09-26

The first complete-path attempt reached `Stock Reconciliation Approved` for `SR2569090002`, then
the app's existing `before_submit` freeze guard blocked the document against itself. Both active
reconciliation queries included every non-terminal draft reconciliation and did not exclude the
current Stock Reconciliation name. The failed submit created no Stock Ledger Entry or GL Entry;
`SR2569090001` remains a rejected draft and `SR2569090002` remains an approved draft on
`local.test` pending the guarded rerun.

The owner-authorized POC therefore includes the smallest prerequisite correction:

- exclude only the current Stock Reconciliation name from the item- and warehouse-level freeze
  queries during that document's own `before_submit` validation;
- continue blocking every other active reconciliation and preserve all other DocType and
  `get_active_freeze_scope` behavior;
- prove both sides with focused automated tests before rerunning the POC.

Independent plan review result: **ready**. The reviewer confirmed the exclusion must be
parameterized, limited to the current Stock Reconciliation, and applied to both query levels.

After the freeze correction passed its focused tests, the next POC attempt reached native SLE/GL
posting and exposed a separate `local.test` prerequisite in ERPNext Thailand: its GL Entry hook
requires every company to have a `Thai Tax Settings` company row before it checks whether the
voucher type is tax-relevant. The demo company had no row. The POC may add a company-only demo row
because Stock Reconciliation is not a tax-invoice voucher, but it must remove only that exact,
unchanged row on both success and failure. Production tax accounts and policy remain an explicit
setup question and are not inferred from this temporary demo value.

## POC result — 2026-09-26

The mechanics-only POC passed on `local.test` using the reviewed task-worktree freeze correction.

- `SR2569090003` reached Rejected and created no SLE or GL Entry.
- The maker's attempt to approve `SR2569090004` was denied with `Self approval is not allowed` and
  left the document Pending Review.
- The distinct approver moved `SR2569090004` through Approved and Submitted.
- Native posting changed `_Test Item` / `Finished Goods - TCP1` from 0 to 3 at valuation rate 100,
  created one active SLE for 300, and created balanced GL Entries: debit `Stock In Hand - TCP1` 300
  and credit `Temporary Opening - TCP1` 300.
- Native cancellation reached Cancelled, restored the balance to 0, created the reversing SLE, and
  left all four GL rows netting to zero.
- The temporary Thai Tax Settings company row was removed and verified absent after the POC.
- Three focused automated tests passed for current-document exclusion and continued item/warehouse
  blocking by a different active reconciliation. Independent code review found no remaining issue.
- Read-only Desk/Computer Use inspection was attempted but the browser tester host exposed no
  browser, session, screenshot, or video capability. No UI acceptance is claimed; this is a
  tooling blocker, not an observed application failure.

Evidence: `evidence/local-test-2026-09-26/stock-reconciliation-poc-result.md`.

## Goal

Keep ERPNext Stock Reconciliation as the only inventory-adjustment posting document and require
an approved, revision-bound native Workflow route before ERPNext creates SLE/GL effects.

## Bounded scope

- Native Stock Reconciliation review, approval, submit, and cancel boundaries.
- Server-side protection against direct submit, state spoofing, stale approval, unauthorized
  actors, and self-approval.
- Signed action snapshots only for the business-approved protected actions.
- Native SLE/GL posting and cancellation/reversal evidence.
- Deterministic, collision-safe configuration migration and recovery.

Retired Stock Count workflow/state engines, freeze/emergency movement, direct ledger writers, and
unapproved count-policy rules are excluded.

## Acceptance criteria

- Only a currently approved native Stock Reconciliation can submit.
- Return/reject creates no SLE or GL entries.
- Posting-critical mutation invalidates approval.
- Protected actors are authorized, distinct, and recorded with native Workflow history.
- Retry/concurrency cannot create duplicate adjustment effects.
- Cancellation and reversal remain native ERPNext behavior.
- Repeated migration converges without overwriting site-owned configuration.

## Proposed owned files

Exact ownership is not assigned until the required decisions and shared-control dependency are
accepted. The candidate Stock-owned surfaces are:

- `connect_diagnostics_core/api/erpnext/stock_reconciliation_workflow.py`
- `connect_diagnostics_core/api/erpnext/tests/test_stock_reconciliation_workflow.py`
- Stock-specific integration tests for Workflow, SLE, GL, cancellation, retry, and concurrency
- Stock-specific migration/recovery modules and tests, if runtime inspection proves they are needed
- This task record and Stock route evidence
- `docs/stock/stock-reconciliation/README.md` only after runtime acceptance

Shared `hooks.py`, `patches.txt`, workflow fixtures, setup fields, print actions, and shared approval
controls require a serialized integration owner after their upstream contract is accepted.

## Dependencies and blockers

- D-STOCK: enabled count types, adjustment eligibility, cutoff/exclusions, recount authority, and
  accounting policy.
- D-IDENTITY: maker/reviewer/final-approver identity, scope, multi-role, delegation, and service
  identity rules.
- D-TARGET: authorized mutation and acceptance targets.
- Accepted SHARED-531 approval digest/SoD API and serialized ownership of shared integration files.
- TSK-602 disposition for legacy records remains separate and non-destructive.

## Verification plan

- Focused unit and integration tests on `local.test` for positive, return/reject, wrong-role,
  self-approval, state spoof/direct submit, stale mutation, retry/concurrency, cancellation, SLE,
  and perpetual-inventory GL behavior.
- Full app tests on `local.test` and `pre-commit run --all-files`.
- Distinct-user Computer Use acceptance on `dev.erp.connectdiagnostics.test` after automated gates.
- Final documentation and independent documentation review after runtime acceptance.

## Native posting-critical field contract

Read-only inspection of the installed ERPNext v16 controller and DocType metadata establishes the
policy-independent digest boundary below. The implementation must still be reviewed against the
accepted shared digest API before code is written.

- Header input: `company`, `purpose`, `posting_date`, `posting_time`, `set_posting_time`,
  `expense_account`, `cost_center`, and every enabled Accounting Dimension field used by GL.
- Provenance/policy input: the app-managed `stock_count` reference and the future approved
  count-type/eligibility revision. This prevents an unrelated or later-reclassified draft from
  inheriting approval.
- Item input, preserving row order and identity: `item_code`, `warehouse`, `qty`,
  `valuation_rate`, `allow_zero_valuation_rate`, `use_serial_batch_fields`, `serial_no`,
  `batch_no`, `serial_and_batch_bundle`, and `reconcile_all_serial_batch`.
- Serial/batch approval binds to normalized Serial and Batch Bundle entry content, not only the
  bundle name; otherwise a referenced bundle could change after approval without changing the
  parent row digest.
- Native-derived display/current values (`difference_amount`, `amount`, `current_qty`,
  `current_valuation_rate`, `current_amount`, `quantity_difference`, `amount_difference`, and
  `current_serial_and_batch_bundle`) are verification outputs, not independently editable approval
  inputs. Tests must prove that native validation does not create a false stale-approval failure.
- Non-posting UI helpers such as barcode scan state are excluded unless installed-source tracing
  later proves they alter the SLE/GL payload.

Runtime inspection on `local.test` found one active Workflow
`Connect Stock Reconciliation Blueprint`, a code-compatible `workflow_state` Custom Field, no
Stock Reconciliation Workflow Actions, and no approval digest/snapshot fields. The installed route
matches the repository fixture: Stock User sends for review; Stock Manager approves, posts, and
cancels; transition tasks are absent.

## Plan review — 2026-09-26

Independent review result: **not ready**. Implementing roles, posting eligibility, or shared
approval controls now would invent unresolved business authority or conflict with contested
cross-task files. No runtime code/configuration edit is authorized until the blockers above are
resolved and the revised exact-file plan passes another independent review.
