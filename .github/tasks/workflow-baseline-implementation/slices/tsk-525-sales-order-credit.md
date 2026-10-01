# TSK-525 — Sales Order commercial/credit approval demo

Status: code complete and independently reviewed; Computer Use acceptance blocked by unavailable
browser controls. Production policy remains unapproved.

Demo revision: `D-SALES-DEMO-2026-09-23.1`

## Goal and authority

Prove that standard ERPNext `Sales Order` can be protected by one native Frappe Workflow, current
review/approval snapshots, separation of duties, a critical-field digest, and server-side submit
provenance. Submitted Sales Order remains the only native source for Delivery Note and Sales
Invoice. No parallel order, credit ledger, exception DocType, or posting engine is permitted.

The user authorized invented demo values on 2026-09-23 so behavior can be proven before final
business policy exists. This revision is local.test-only and must not be promoted to shared DEV,
UAT, or production. It does not resolve production D-SALES, D-CORE, D-IDENTITY,
SHARED-531-CORE, or TSK-602 decisions.

Source priority is this demo revision, the bounded controls below, the verified clean local.test
inventory, the baseline specification/manifest, then installed Frappe/ERPNext v16 behavior.

## Demo route and actors

Every Sales Order uses the same route; demo values never select or bypass a branch.

```text
Sales Order Draft
  -> Sales Order Pending Commercial/Credit Review
  -> Sales Order Pending Final Approval
  -> Sales Order Approved
  -> Sales Order Submitted
```

- Maker: `Sales User`.
- Commercial/Credit Reviewer: `Sales Manager`.
- Final Approver and native submit actor: `C-Level Approver`.
- Maker is snapshotted as `approval_maker_user` when the native Submit for Review action runs;
  mutable document `owner` is not approval identity. Maker, Reviewer, and Final Approver are three
  distinct authenticated Frappe Users. Employee links resolve to immutable `user_id`. A multi-role
  user may act in only one protected stage.
- Administrator, service, background, API, RPC, and import identities receive no SoD or approval
  bypass.
- Return from either review stage moves to Draft and clears current approval evidence. Reject moves
  to Rejected with no downstream effect; Revise moves a rejected document to Draft.
- The same C-Level Approver may Approve then Post because Post executes an already-recorded
  decision; it is not a second approval.
- Delegation, backup approvers, employee scope, and service approval are deferred/disabled.

Demo evidence values are not business thresholds:

| Purpose | Demo value |
| --- | ---: |
| Currency | Native `_Test Company` currency (INR on `local.test`) |
| Customer credit limit | 100,000 in company currency |
| Standard order | 50,000 in company currency |
| Credit-limit crossing order | 120,000 in company currency |
| Special discount case | 15% |

Native Customer Credit Limit remains the exposure engine. During the bounded credit-crossing test,
Accounts Settings `credit_controller` is temporarily `C-Level Approver` and is restored afterward.
No permanent Customer/Company credit policy is installed.

## Approval binding and edit policy

The approval digest binds demo revision plus:

- customer, company, transaction/order dates, delivery date, and order type;
- currency, conversion rates, selling price list, and price-list currency;
- item code, quantity, UOM/conversion factor, rate/price-list rate, margin, item/additional
  discounts, delivery date, and warehouse;
- tax template/category, shipping rule, and tax rows;
- payment-terms template and payment schedule;
- incoterm/named place and server-calculated base/net/grand totals;
- current Customer Credit Limit value and its Sales Order bypass flag.

Dynamic outstanding exposure is not frozen because concurrent native transactions change it;
ERPNext rechecks current exposure during submit. A critical document or credit-setting change after
Review invalidates approval.

While Pending Final Approval or Approved, critical edits are rejected and the actor must Return for
correction. The only non-critical changes after Review are the native Workflow state, owned
approval/snapshot fields written by transition tasks, and Frappe audit metadata (`modified`,
`modified_by`, assignment/comment/like metadata). Every other standard or unknown Custom Field is
fail-closed as critical. Tests cover one permitted Workflow/snapshot update and unknown-field
rejection. Draft correction requires full Review and Approve again.

Approval digest/user/signature fields are `no_copy`. An amended Sales Order starts at Draft without
prior evidence and must traverse the complete demo route.

## Native transition tasks and one-use Post provenance

Frappe v16 `apply_workflow` verifies persisted state, action, role, condition, and native
self-approval, runs synchronous transition tasks, then calls `save()` or `submit()` in the same
transaction. The demo configures these registered methods:

| Workflow action | Ordered synchronous tasks |
| --- | --- |
| Submit Sales Order for Review | `Capture Sales Order Demo Maker` |
| Review Sales Order | `Capture Print Action: Checked`, then `Capture Sales Order Demo Review` |
| Approve Sales Order | `Capture Print Action: Authorized`, then `Capture Sales Order Demo Final Approval` |
| Return/Reject/Revise | `Clear Sales Order Demo Approval` |
| Post Sales Order | `Authorize Sales Order Demo Submission` |

The Maker task records the authenticated User at the first native transition. The adapter
Review/Approve tasks require the linked Employee and non-empty signature written by the preceding
shared print task, record immutable User actors, validate digest and SoD, and abort the same
transaction when evidence is incomplete.

`Authorize Sales Order Demo Submission` sets a request-scoped `frappe.flags` marker with exactly
`{doctype, name, approval_revision, approval_digest, action, actor}`. It is bound to Sales Order,
the current name/digest, revision `D-SALES-DEMO-2026-09-23.1`, action `Post Sales Order`, and
`frappe.session.user`.

The Sales Order `before_submit` guard locks and re-reads persisted Approved state, checks submit
permission, current digest, signatures, and three distinct actors, validates the exact marker, then
consumes it by clearing the flag in a `finally` block on success or failure. Completed Workflow
Action or persisted Approved state never substitutes for the one-use marker. Tests cover direct
submit, missing/stale marker, wrong document, digest/revision/action/actor, retry after failure, and
concurrent Post.

## Technical local.test boundary

The adapter is active only when both site-scoped values exist and match:

- `sales_order_approval_demo_enabled = 1`
- `sales_order_approval_demo_site = "local.test"`

Document hooks are inert elsewhere; transition tasks fail closed when disabled. Tests prove a
missing configuration and a different site cannot activate the demo guard.

The demo does not modify shipped `fixtures/workflow*.json`,
`fixtures/workflow_action_master.json`, `patches.txt`, or add a Workflow migration. Automated
integration tests create and remove an ephemeral native Workflow. Computer Use temporarily updates
the existing local.test blueprint through native Desk only after fingerprint recheck. Setup,
runtime hooks, patches, and console code never create or mutate a business Workflow.

## Exact implementation ownership

The implementation worker exclusively owns the Python/setup/hook files below. The primary agent
alone owns the task register, route manifest, and evidence files.

| File | Intended change |
| --- | --- |
| `connect_diagnostics_core/api/erpnext/sales_order_workflow.py` | Demo gate; critical digest; maker/reviewer/approver/signature snapshots; mutation, submit, cancel and amend guards; five named transition tasks; one-use Post provenance. |
| `connect_diagnostics_core/api/erpnext/tests/test_sales_order_workflow.py` | Isolated digest, state, permission, identity, mutation, marker, spoofing, site-gate, retry and concurrency tests. |
| `connect_diagnostics_core/api/erpnext/tests/test_sales_order_workflow_integration.py` | local.test native Workflow, Quotation/Sales Order, credit, downstream, reject/return and amend integration. |
| `connect_diagnostics_core/setup/workflow_fields.py` | Hidden, read-only, no-copy Sales Order digest/maker/reviewer/approver User fields. |
| `connect_diagnostics_core/setup/tests/test_workflow_fields.py` | Exact field and idempotent setup contract. |
| `connect_diagnostics_core/hooks.py` | Preserve existing Sales Order validation/regulatory ordering; add adapter hooks and five named Workflow methods. |
| `connect_diagnostics_core/setup/tests/test_workflow_fixture_blueprints.py` | Prove shipped production blueprint is not silently converted into the local demo route. |
| `.github/tasks/workflow-baseline-implementation/workflow-route-manifest.json` | Record non-promotable local.test demo revision without accepting production D-SALES. |
| `.github/tasks/workflow-baseline-implementation/evidence/local-test-2026-09-23/sales-order-credit-demo.md` | Automated, Computer Use and recovery evidence plus demo limitations. |

The existing `setup/print_action_fields.py`, `api/erpnext/print_actions.py`, print format, and their
tests are unchanged. Existing Sales Order `checked_*` and `authorized_*` fields/tasks provide the
Employee-backed signature snapshots consumed by the adapter.

## Explicit exclusions

- Customer Credit Exception/Request state engine or parallel credit ledger.
- Custom Delivery Note, Sales Invoice, stock, GL, or AR posting.
- Hard-coded employee IDs/emails, production amount thresholds, or implicit base currency.
- Workflow creation/mutation from setup, hooks, runtime adapter, console, or migration code.
- Delegation/backup approver policy.
- Changes to existing quotation/regulatory validations beyond ordered hook integration.

## Automated acceptance on local.test

- Standard/direct Sales Order and Sales Order mapped from Quotation complete the route.
- Standard, 15% discount, and native 100,000/120,000 company-currency credit cases use the same
  demo route.
- Self-approval, actor overlap, wrong role, unauthorized/multi-role/Administrator/service identity,
  state and snapshot spoofing are blocked.
- Direct document submit, REST/RPC, import/bulk, background and replayed Approved state cannot
  bypass current approval plus one-use Post provenance.
- Every critical class and unknown Custom Field blocks mutation until Return; only the named
  Workflow/snapshot/audit allowlist succeeds.
- Return/Reject creates no Delivery Note, Sales Invoice, stock, GL, or AR side effect.
- Retry/concurrent action remains one Sales Order and one native submit effect.
- Native Credit Limit, Payment Terms, Price List, discounts/pricing and hold behavior remain active.
- Cancel/amend preserves Workflow Action, Version and Timeline history; amend clears approval and
  requires the full route.
- Approved submitted Sales Order can create native downstream references; draft, rejected,
  unsubmitted and stale-approved orders cannot be treated as approved.
- Focused tests, full app tests on local.test and pinned pre-commit pass.

## Configuration, recovery, UI and documentation

Code-managed hidden fields use the existing idempotent setup/migrate path and are inert unless both
site gates match. No migration changes Workflow or Accounts Settings.

Before Computer Use, recheck the local.test fingerprint, pending Workflow Actions, document-state
distribution, and active Sales Order Workflow. A mismatch stops the demo. Configure the route and
ordered transition tasks through native Desk; temporarily set the credit-controller role; record
Workflow Timeline, negative SoD/permission results, critical-change reapproval, and native
downstream reference on `dev.erp.connectdiagnostics.test`.

Recovery disables/removes both site-config values, restores the exact prior Workflow through native
Desk/fixture recovery, and restores the prior credit-controller. It never deletes or fabricates
Workflow Action, Version, or Timeline history. Hidden fields remain inert; removing them requires a
separate destructive schema migration.

Only after browser acceptance, `doc_writer` updates
`docs/selling/sales-order-approval/README.md` and `docs/selling/behavior.md`, explicitly labeling
the accepted behavior as a local.test demo rather than production policy. An independent reviewer
checks final docs against code/runtime evidence.

## Independent plan review

The original production plan was not ready. The first demo review also was not ready because Post
provenance, transition-task ownership, and the technical site boundary were underspecified. This
revision resolves those items and requires a fresh independent READY verdict before implementation.

## Execution checkpoint — 2026-09-23

- Independent plan review: READY.
- Focused automated acceptance: Sales Order unit `10/10`, native Workflow integration `18/18`
  twice consecutively, setup `2/2`.
- Targeted pre-commit: passed, including Ruff, `ty-check`, Semgrep, and `pip-audit`.
- Independent code review: READY; no remaining P0/P1 code finding.
- Full app: all `679` unit tests passed; `87/91` integration tests passed. The four failures are
  unchanged, independently reproduced Stock Count baseline failures outside this slice. See the
  demo evidence record.
- Computer Use: BLOCKED at capability discovery because the browser tester had no browser-control,
  screenshot, or video-recording tool. The persistent Desk route was therefore not configured and
  no UI acceptance is claimed.
- Recovery: the demo enable flag is `0`, the Bench Python path is restored to the normal checkout,
  and the original site-owned Sales Order Workflow remains active.
