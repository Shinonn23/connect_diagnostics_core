# TSK-512 Borrow prototype

Status: BORROW-P1 completed; BORROW-P2 awaiting owner scope approval

## Goal

Build and verify an isolated, Stock-only Borrow MVP without changing the accepted workflow
baseline or the native ERPNext Material Request purpose contract. The prototype must be usable on
`local.test` before an owner decides whether to adopt, revise, or discard it.

## Isolation contract

- Branch: `feat/tsk-512-borrow-mvp`, based on `origin/developments`.
- Runtime target: `local.test` only, with this worktree placed first on `PYTHONPATH`.
- Request selector: existing `Material Request.request_usage = Employee Borrow`.
- Stock effects: submitted native Stock Entries only. No direct Stock Ledger or GL writes.
- No Workflow, Workflow State, Workflow Action Master, workspace-baseline, or TSK-521/590/600
  changes.
- No migration or rewrite of existing Borrow/Demo records in the prototype.
- No `Material Request.material_request_type = Borrow` option and no global Material Request
  controller override in the MVP.
- No push, PR, merge, or deployment without a later explicit request.

## Final MVP acceptance

1. An eligible Stock Item can be requested on an Employee Borrow Material Request.
2. One submitted Employee Borrow request can create one Stock Borrow idempotently.
3. Stock Borrow preserves company, employee, customer/personal/internal context, due date, and
   request-row quantities.
4. Outbound preparation creates a draft native Material Transfer from a selected source warehouse
   to the responsible employee's Borrow Warehouse.
5. Submitting/cancelling the outbound Stock Entry recomputes issued and outstanding quantities.
6. Exact-return preparation creates a draft native Material Transfer from Borrow Warehouse to the
   configured return-hold warehouse.
7. Return Stock Entry submission is rejected until the prototype records physical receipt.
8. Submitting/cancelling the return recomputes returned and outstanding quantities.
9. Partial outbound and partial exact return are supported without double counting.
10. Native Material Request purposes and existing Demo/Asset paths remain unchanged.

Replacement identity via Repack is a hard-gated follow-up slice. It is not part of MVP acceptance
until executable native Serial/Batch and valuation evidence passes.

## Backlog

| ID | Status | Depends on | Scope |
| --- | --- | --- | --- |
| BORROW-P0 | completed | none | Read-only native/source feasibility and repository mapping |
| BORROW-P1 | completed | BORROW-P0 | Backend schema, permission contract, exact transfer service, focused tests |
| BORROW-P2 | proposed | BORROW-P1 | Minimum Desk actions, navigation, and local.test integration |
| BORROW-P3 | proposed | BORROW-P2 | Role/permission and Computer Use acceptance on local.test |
| BORROW-P4 | proposed | BORROW-P3 | Native Repack replacement spike and owner decision |
| BORROW-P5 | proposed | owner adoption | Migration, final docs, workflow integration, release path |

## Known plan-review findings

- The pasted plan's first-class `material_request_type = Borrow` is not safe as a metadata-only
  change because ERPNext has hard-coded native-purpose mappings and status queries.
- The repository already has a combined Borrow/Demo model using `request_usage`; the MVP reuses
  that seam and does not create a second live selector.
- Existing Dispatch and return-inspection code mixes Stock and Asset semantics. The MVP does not
  modify it until the pure-Stock ledger flow passes.
- Mixed exact/replacement posting has no accepted atomicity contract; replacement remains gated.

## BORROW-P1 acceptance

- Code-managed Item and Stock Entry fields are exact, idempotent, and tested.
- Item validation rejects `allow_borrow = 1` for non-stock, serialized, or batched Items in the
  initial backend slice.
- One submitted Employee Borrow Material Request creates exactly one Stock Borrow, including under
  duplicate calls; all rows use Stock UOM quantities.
- Outbound and exact-return APIs create correct draft Material Transfers and reject over-issue,
  over-return, wrong warehouses, and unauthorized calls.
- A controlled method records return receipt user/time on one draft return Stock Entry; submission
  is blocked before receipt.
- Submitted/cancelled linked Stock Entries rebuild issued, returned, and outstanding quantities
  from `Stock Entry Detail.transfer_qty` under a lock on the Stock Borrow.
- Unit and focused integration tests pass. User-visible Desk acceptance remains BORROW-P2/P3 and
  is not claimed by BORROW-P1.

## Restart procedure

1. Read this file, `spec.md`, and `verification.md`.
2. Confirm the branch and worktree are clean apart from accounted TSK-512 files.
3. Confirm commands target `local.test` and resolve this worktree's Python package first.
4. Resume only the next ready backlog row; do not infer completion from source presence.
5. Record tests, review findings, migration results, and browser evidence in `verification.md`.
