# Stock Reconciliation mechanics POC — local.test — 2026-09-26

Result: **PASS for backend mechanics only**

## Verified path

| Check | Evidence |
| --- | --- |
| Reject is non-posting | `SR2569090003`; Rejected; 0 SLE; 0 GL Entry |
| Maker cannot approve own document | `SR2569090004`; `ValidationError: Self approval is not allowed`; state remained Pending Review |
| Native submit changes stock | 0 → 3 units of `_Test Item` in `Finished Goods - TCP1` at valuation rate 100 |
| Native submit posts balanced GL | Debit `Stock In Hand - TCP1` 300; credit `Temporary Opening - TCP1` 300 |
| Native cancel reverses stock | `SR2569090004`; Cancelled; balance restored to 0 |
| Native cancel reverses GL | Four GL rows net to zero after reversal |
| Temporary prerequisite cleanup | Thai Tax Settings child `qllk1ci22m` removed and verified absent |
| Correct code under test | Freeze hook loaded from the `wf-tsk-77-stock-count` task worktree |

## Focused automated evidence

Three tests passed against the task-worktree module:

1. current Stock Reconciliation name is excluded from both freeze checks;
2. a different active reconciliation still blocks at item/warehouse scope;
3. the exclusion parameter reaches the parameterized item and warehouse SQL queries.

## Scope limits

This proves native Workflow gating, maker self-approval denial, ERPNext SLE/GL posting, and native
cancellation mechanics. It does not accept production roles, sender-versus-approver segregation,
stale-approval digest controls, final count policy, production adjustment accounts, delegation, or
migration/retry/concurrency behavior.

Read-only Desk/Computer Use inspection could not run because the browser tester host provided no
browser/session/screenshot/video capability. No UI acceptance is claimed, and no application error
was observed through that unavailable path.

Before production configuration, return to the owner for the requirements listed in the TSK-77
task record. In particular, do not reuse the demo dual-role maker/sender or Temporary Opening
account as production policy.
