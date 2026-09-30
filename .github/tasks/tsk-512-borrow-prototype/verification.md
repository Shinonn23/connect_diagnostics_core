# TSK-512 Borrow prototype verification

## Environment

- Source base: `origin/developments` at `a3dc88f1e9f8d42eee6b4b6e6ab24aae2caa76e8`.
- Prototype branch: `feat/tsk-512-borrow-mvp`.
- Approved runtime target: `local.test` only.
- Installed stack observed 2026-09-27: Frappe 16.34.0, ERPNext 16.35.0, HRMS 16.19.0,
  ERPNext Thailand 1.0.2.
- `local.test` system timezone observed as `Asia/Kolkata`; schema timestamps must use the runtime
  system timezone rather than the desktop timezone.

## Completed evidence

- Read-only repository map confirmed the existing `request_usage = Employee Borrow` seam and the
  absence of a Material Request `override_doctype_class`.
- Installed-source review confirmed a custom native Material Request type is not supported by a
  Property Setter alone.
- Installed-source review confirmed native Material Transfer and Repack own Stock Ledger, Serial /
  Batch Bundle, valuation, submission, and cancellation effects.
- Worktree import isolation was proven with `PYTHONPATH`: Frappe resolves
  `connect_diagnostics_core` from this prototype worktree while commands still target `local.test`.
- `PYTHONPATH=<prototype> bench --site local.test migrate` passed on 2026-09-27. The site contains
  `tabStock Borrow`, `Item-allow_borrow`, and `Stock Entry-stock_borrow` after migration.
- The migration removed test-site-only orphan schema from an earlier uncommitted prototype:
  `Stock Asset Conversion`, `Stock Asset Conversion Item`, and orphan Workspace Sidebar
  `Stock Counting`. This did not affect `local`, DEV, UAT, production, or Git, but any data that had
  existed only in those orphan test tables is not recoverable through this task.
- Focused setup/naming/unit modules passed on `local.test`: Item setup (5), Stock Entry setup (1),
  document naming (22), Item API (1), Stock Borrow API (4), Stock Borrow controller integrity (3),
  Material Request (18), Dispatch API (8), Stock Entry workflow (11), and Dispatch controller (8).
  Total: 81 unit tests passed.
- The native lifecycle integration test passed on `local.test`: idempotent Stock Borrow creation,
  partial outbound, real stock movement to the employee Borrow Warehouse, over-issue rejection,
  warehouse-tamper rejection, return rejection before receipt, receipt confirmation, exact return,
  derived totals, cancellation, and Stock Ledger reversal. Total: 1 integration test passed.
- The pinned pre-commit hooks passed for every changed or added TSK-512 file, including Ruff,
  formatting, JSON validation, `ty`, Frappe Semgrep, and dependency audit. A separate repository-wide
  run reached and passed all non-JavaScript gates but could not start `prettier-eslint` for unchanged
  repository JavaScript because `npm` could not resolve that executable; no JavaScript belongs to
  BORROW-P1.

## P1 review result

- Independent final review found no remaining P0/P1 code blocker after the type/i18n fixes and
  local.test evidence.
- True simultaneous duplicate calls, non-Stock-UOM request conversion, unauthorized-role calls
  beyond the focused permission tests, and rollback after a native posting-invariant failure were
  not independently integration-tested. The prototype prevents duplicate creation with a locked
  source row plus a unique link and uses normalized `stock_qty`; those four scenarios remain
  explicit BORROW-P3 hardening evidence rather than being claimed as exhaustively accepted here.

## Computer Use matrix

| Actor | Route | Preconditions | Actions | Expected | Actual / evidence |
| --- | --- | --- | --- | --- | --- |
| Requester | Employee Borrow request | Eligible Stock Item | Create and submit request | One request with no Warehouse/identity choice | Pending |
| Stock User | Outbound | Submitted request, employee Borrow Warehouse | Create Stock Borrow; prepare and submit outbound | Stock reaches Borrow Warehouse; outstanding updates | Pending |
| Stock User | Exact partial return | Active Borrow; physical goods received | Prepare, mark received, submit return | Stock reaches Return Hold; outstanding reduces once | Pending |
| Responsible Employee | Read responsibility | Active Borrow assigned to employee | Open Stock Borrow | Can read obligation; cannot post stock | Pending |

## Blockers

- Replacement identity/Repack remains unverified and outside MVP acceptance.
- Browser acceptance requires the desktop host to reach `dev.erp.connectdiagnostics.test` after all
  automated gates pass.
