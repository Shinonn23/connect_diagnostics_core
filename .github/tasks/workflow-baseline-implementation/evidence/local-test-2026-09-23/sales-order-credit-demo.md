# TSK-525 Sales Order Commercial/Credit Demo Evidence

Date: 2026-09-23
Target: `local.test` / `dev.erp.connectdiagnostics.test`
Revision: `D-SALES-DEMO-2026-09-23.1`

## Result

The server-side adapter and an ephemeral native Frappe Workflow passed focused automated
acceptance. The persisted Desk route and Computer Use gate remain blocked because this Codex host
did not expose browser-control, screenshot, or video-recording tools. No browser pass is claimed.

The demo feature gate was returned to its safe state after the blocked browser attempt:

- `sales_order_approval_demo_enabled = 0`
- the Bench Python path was restored to the normal app checkout
- the existing `Connect Sales Order Blueprint` remained the active site-owned Workflow
- no repository Workflow fixture or migration was changed

## Automated evidence

Focused tests were run with the Sales Order worktree on `local.test`:

- Sales Order unit tests: `10/10` passed
- Sales Order native Workflow integration tests: `18/18` passed twice consecutively
- Workflow field setup tests: `2/2` passed
- targeted pre-commit: trailing whitespace, EOF, merge conflict, Python AST, debug statements,
  JSON, Ruff check/format, Prettier JSON, `ty-check`, Semgrep, and `pip-audit` passed
- independent code review: READY with no remaining P0/P1 code finding

The integration route used real `frappe.model.workflow.apply_workflow` transitions and real
ERPNext Sales Orders. It covered:

- direct Submit/API-style bypass rejection
- wrong-role, state-spoof, maker/reviewer/approver separation, and multi-role behavior
- Employee-backed checked/authorized signature binding
- critical item/payment/policy drift and unknown child fields
- direct Sales Order, native Quotation mapping, and the same route for a 15% discount
- native Customer hold plus a 100,000 company-currency credit limit crossed by a 120,000 order
- Return, edit, full re-review, and re-approval
- Reject without submission or downstream effect
- one-use Post marker and replay rejection
- native Cancel versus blocked direct cancel
- amend with cleared approval evidence and re-entry
- native Delivery Note and Sales Invoice mapping only from a submitted Sales Order

## Full-app gate

The full app run completed `679` unit tests successfully. Of `91` integration tests, four existing
Stock Count tests failed outside the Sales Order scope:

- `test_creates_submitted_material_transfer`
- `test_posts_per_row_warehouse_across_multiple_warehouses`
- `test_posts_receipt_for_surplus_and_issue_for_shortage`
- `test_rejects_second_generation`

The failures reproduce unchanged against the baseline app checkout. They reflect an existing
Stock Count contract mismatch: current code creates a draft transfer for Workflow submission and
writes `Stock Reconciliation`, while the old tests/schema still expect an immediately submitted
Material Transfer and do not allow `Stock Reconciliation` in the adjustment entry type. No Stock
Count file was changed for TSK-525.

## Browser gate

The dedicated `browser_tester` stopped at capability discovery. No Computer Use controls,
browser-session inspection, screenshot capture, or video recording were available. It therefore
could not configure the persisted Workflow through Desk, authenticate the three actors, or record
the required successful run. Per repository policy, it did not simulate or claim acceptance.

## Required continuation

Resume on a Computer Use-capable desktop host. Configure the approved universal demo route through
Desk on `local.test`, enable both demo site-config gates, verify Asia/Bangkok timestamp behavior,
then execute and record the Sales Maker, Commercial/Credit Reviewer, and Approver handoffs. After
that gate passes, write final canonical documentation under `docs/` and perform documentation
review.
