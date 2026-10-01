# Workflow implementation branch map

Parent integration branch: `feat/workflow-baseline-checkpoint-20260919`

All workflow implementation branches below are created from the parent integration branch and
merge back into that parent first. The parent branch is the only workflow branch that later merges
into `developments`.

| Task owner           | WF coverage                                                                   | Branch                                 |
| -------------------- | ----------------------------------------------------------------------------- | -------------------------------------- |
| TSK-77 / Plans 01–02 | WF-04 Full/Cycle Stock Count, WF-05 Variance/Recount                          | `feat/wf-tsk-77-stock-count`           |
| TSK-521              | WF-01 Internal Location Transfer, WF-02 Warehouse Transfer                    | `feat/wf-tsk-521-transfer`             |
| TSK-522              | WF-03 Emergency Movement During Freeze                                        | `feat/wf-tsk-522-emergency-freeze`     |
| TSK-523              | WF-06 Asset Movement/Transfer, WF-08 Equipment Assignment/Installation        | `feat/wf-tsk-523-asset-movement`       |
| TSK-524              | WF-07 Asset Disposal                                                          | `feat/wf-tsk-524-asset-disposal`       |
| TSK-525 / Plan 03    | WF-09 Sales Order/Credit Approval                                             | `feat/wf-tsk-525-sales-credit`         |
| TSK-526 / Plan 04    | WF-10 Credit Note/AR Write-off                                                | `feat/wf-tsk-526-credit-writeoff`      |
| TSK-527 / Plan 05    | WF-11 Procurement Approval                                                    | `feat/wf-tsk-527-procurement-approval` |
| TSK-528 / Plan 06    | WF-12 PI/Payment Handoff                                                      | `feat/wf-tsk-528-ap-payment-handoff`   |
| TSK-529              | WF-13 Payment Approval                                                        | `feat/wf-tsk-529-payment-approval`     |
| TSK-530 / Plan 07    | WF-14 Payroll Processing/Review                                               | `feat/wf-tsk-530-payroll-review`       |
| TSK-531              | WF-15 Role/Scope Assignment, WF-16 Delegation, WF-17 Self-Approval Protection | `feat/wf-tsk-531-approval-controls`    |
| TSK-532 / Plan 08    | WF-18 Workflow Baseline Freeze                                                | `feat/wf-tsk-532-baseline-freeze`      |
| TSK-603              | Canonical manual Journal Entry route                                          | `feat/wf-tsk-603-journal-entry`        |
| TSK-602              | Cross-cutting normalized-baseline integration and migration                   | parent integration branch              |

## Merge flow

```text
feat/wf-tsk-*
      |
      | PR
      v
feat/workflow-baseline-checkpoint-20260919
      |
      | integration + complete validation
      v
developments
```

Internal slices such as `SHARED-531-CORE`, `SHARED-522-CORE`, `SHARED-529-CORE`,
`STOCK-01-02`, `SALES-03`, `CREDIT-04-*`, `PROCURE-05`, `AP-06-*`,
`PAYROLL-07-*`, and `FREEZE-08-*` remain subtasks inside the branch owned by their workflow
task. Do not create another branch for an internal slice unless file ownership proves that the
slice must be isolated.

`TSK-512` is an external dependency for enabled Item Request/asset routes and does not receive a
workflow branch from this baseline.

Before implementation begins on a child branch, update it from the parent branch, record exact file
ownership in the task plan, and obtain independent plan review. After implementation, follow the
repository acceptance lifecycle through automated tests, code review, Computer Use acceptance,
final documentation, and documentation review before merging it into the parent.
