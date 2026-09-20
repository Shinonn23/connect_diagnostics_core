# Item Request v11 verification checkpoint

This file distinguishes tests observed passing from gates that remain unverified. Results are
from the shared DEV site `local`; they are not clean-install or production evidence.

## Observed passing evidence

| Area                               | Evidence                                                                             |
| ---------------------------------- | ------------------------------------------------------------------------------------ |
| Approval operation persistence     | `test_operations`: 6 unit + 17 integration passed                                    |
| Physical operation kernel          | `test_physical_operations`: 8 passed                                                 |
| Non-Demo Plan initialization       | Plan controller 15 passed; Stock integration fixture 2 passed                        |
| Demo assessment/approval kernels   | Demo supply 7 passed; approval E2E 4 passed in earlier run                           |
| Automatic Demo scheduler kernels   | `test_automatic_demo`: 6 passed                                                      |
| Outbound contract                  | `test_outbound`: 12 passed                                                           |
| Shipment native snapshot adapter   | `test_shipment_integration`: 4 passed                                                |
| Return preparation contract        | `test_return_execution`: 8 passed                                                    |
| Return integration scaffold        | `test_return_execution_integration`: 2 passed; only leg construction/public surface  |
| Return obligation ledger           | `test_return_ledger`: 23 passed                                                      |
| Existing-custody exchange adapter  | Focused exchange suite reported 13 passed after transfer-only fix                    |
| Provisioning foundation worker run | Stock 40, operation contract 4, voucher protection 56, controller 11 reported passed |

The provisioning foundation result is **not accepted** because subsequent independent review
found open P1 lineage/identity defects. The Return integration result is shallow and does not prove
native submission.

## Open P0/P1 evidence gaps

- No accepted persisted low-value Material Issue→Existing Asset→Receipt Movement test.
- No accepted persisted high-value Composite Asset→Asset Capitalization→submitted Asset test.
- No full Automatic Demo Plan A/B/C, wait handoff, or fallback integration.
- No mixed Stock+Asset Shipment outbound atomicity/rollback/reversal integration.
- No complete Direct/Shipment Stock+Asset Return and equivalent-substitution native integration.
- No QA→repair→fresh inspection→release→future claim handoff E2E.
- No Stock carry-only write-off/settlement or Asset scrap/restore E2E.
- No configuration warehouse action, close/reopen, complete API, or role-aware Desk verification.
- No clean-site `bench --site <site> migrate` evidence for the full current worktree.
- No full app suite, patch suite, or `pre-commit run --all-files` passing evidence after the latest
  changes.

## Latest pre-commit evidence

A checkpoint run against the new task/domain documentation and the changed payroll reference
passed whitespace, EOF, merge-conflict, AST, JSON/TOML/YAML applicability, Ruff, formatting, and
`pip-audit`. It failed `semgrep-frappe`, whose hook scans the tracked repository rather than only
the supplied files. The seven blocking findings reported were:

- `custom/sales_invoice.json`: relaxed `All` role permission;
- `automatic_demo.py`: two `frappe.set_user` findings;
- `voucher_protection.py`: two dynamically formatted SQL findings;
- `public/js/item_request_generated_voucher.js`: deprecated `cur_frm` usage;
- the reviewed native Contact owner-only `All` permission finding.

These findings were not changed because the user stopped implementation. Re-run and resolve or
formally validate every finding before any merge-ready commit.

## Required final command gates

Run only after every backlog item is code-reviewed:

```text
bench --site local migrate
bench --site local run-tests --app connect_diagnostics_core
pre-commit run --all-files
```

Also run focused native integration for every state transition, unique-key conflict, retry,
response-loss replay, rollback, generated-voucher bypass, locked Asset reuse, and protected
valuation/repost case.

After the automated gates pass, run Computer Use acceptance against the approved DEV target. The
matrix must exercise every affected role and server behavior without relying on client JavaScript,
including creator/requester, reviewer/approver, forbidden/self-approval boundaries, generated
voucher handoffs, blocked/rejected paths, visible downstream side effects, and retry/recovery where
reachable. Record route, actor, prerequisites, exact click/type actions, state before/after,
expected result, actual result, PASS/FAIL, and durable failure evidence.

When Computer Use acceptance passes, rewrite the accepted Item Request behavior into the canonical
final documentation under `docs/<module>/<workflow>/` and the relevant module `behavior.md`.
Do not carry this task's backlog, P0/P1 register, temporary evidence, implementation checkpoints,
or unimplemented design into final docs. Independently review the resulting documentation against
the accepted code and runtime behavior before closing the task.

## Pause integrity

- All agents were interrupted before this checkpoint.
- No task is marked complete based only on source presence.
- Known P1 findings are preserved in `backlog.md`.
- The next session starts with IR11-F0 and a fresh `git status`, not with new feature work.
