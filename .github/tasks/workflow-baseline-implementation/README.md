# Workflow baseline implementation

Status: normalized-baseline TSK-602 plan ready; implementation active.

The 2026-09-26 normalized-baseline request supersedes the old WF-01–18 business-workflow count.
The canonical target is ten standard ERPNext/HRMS DocType routes; TSK-600/601 are shared controls,
not additional business workflows. The old mapping remains below as historical task context until
TSK-602 completes the reviewed manifest and task-register migration.

This record supersedes conflicting assumptions in the eight attached plans. It does not treat
planning text, task status, fixture presence, or old tests as runtime evidence. The complete goal
remains all required WF-01–19 implementation and evidence gates; this checkpoint does not narrow
that goal.

## Fixed constraints

- Native ERPNext/HRMS documents own stock, GL, AR, AP, asset, payment, and payroll effects.
- No parallel posting engine is permitted.
- The app may ship explicitly reviewed, allowlisted `Workflow`, `Workflow State`, and
  `Workflow Action Master` fixtures for approved named routes. Each route requires a configuration
  manifest, owner, target/scope, collision policy, deterministic migrate/re-run behavior, recovery
  plan, and independent validation. Fixture sync must not silently overwrite, disable, delete, or
  repurpose an existing site-owned record, and business Workflow records must not be created or
  changed through ad hoc install, startup, setup, hook, or runtime writers.
- Salary Slips submit only through Payroll Entry; no Salary Slip Workflow is introduced.
- Retired Stock Count code is not revived. Native Stock Reconciliation is the posting endpoint;
  the count evidence/recount/accepted-quantity model remains a stock-policy decision.
- Existing dirty files and site configuration are contested input, not an implementation base.
  No install, update, migrate, or fixture sync may expose them to shared DEV/UAT.

## Last verified checkpoint

- Repository and installed-source audits completed on 2026-09-17 against the `local` audit site.
- Reproducible source/configuration evidence is recorded in `verification.md`.
- Decision and configuration questions are recorded in `decisions.md`.
- Plan 01–08 corrections and WF-01–19 ownership are recorded in `spec.md`; WF-19 is the
  owner-confirmed Journal Entry route recorded in `slices/tsk-603-journal-entry.md`.
- `slices/shared-531-core.md` is the selected first runtime slice. Its plan is bounded, but the
  slice is blocked until D-CORE, required D-IDENTITY decisions, target approval, exact files, and
  a second independent readiness review are complete.

## Active normalized dependency graph (authoritative)

```text
D-TARGET + D-NORMALIZED-ROUTES + D-CORE + D-IDENTITY
  -> TSK-600/601 shared controls
  -> TSK-590 Stock Entry
  -> TSK-591 Stock Reconciliation
  -> TSK-592 Asset Movement
  -> TSK-593 / TSK-603 Journal Entry
  -> TSK-594 Sales Order
  -> TSK-595 Sales Invoice Return/Credit Note
  -> TSK-596 Purchase Order
  -> TSK-597 Purchase Invoice
  -> TSK-598 Payment Entry
  -> TSK-599 Payroll Entry
  -> TSK-602 normalized fixture/migration integration
  -> automated gates -> Computer Use -> docs -> accepted
```

Advanced count/recount, asset disposal/equipment, delegation, backup, amount/credit thresholds,
bank settlement, and baseline-freeze workflows are outside this graph. A blocked route blocks only
its own acceptance; TSK-602 continues all independent routes and evidence.

## Historical dependency graph (superseded by TSK-602)

```text
FIXED-CONSTRAINTS
├── D-CORE ── SHARED-531-CORE
│              ├── domain adapters
│              └── SHARED-531-ADAPTER-COVERAGE (WF-15/16/17)
├── D-STOCK ── SHARED-522-CORE ── STOCK-01-02
│                              └── SHARED-522-COUNT-COVERAGE (WF-03/04/05)
├── D-SALES ── SALES-03
├── D-CREDIT ── CREDIT-04-CORE ── CREDIT-04-REFUND
├── D-PROCURE ── PROCURE-05 ── AP-06-CORE
├── D-AP ──────────────────────┘
├── D-PAYMENT ── CONFIG-PAYMENT + SHARED-529-CORE
│                                  └── SHARED-529-HANDOFF-COVERAGE (WF-10/12/13/14)
└── D-PAYROLL ── PAYROLL-07-CORE ── PAYROLL-07-BANK-HANDOFF

FREEZE-08-REGISTER may proceed from the traceability contract.
FREEZE-08-SIGNOFF waits for every required WF-01–17 and G0–G4.
```

## Active normalized task register

| ID | Route / responsibility | Status | Close evidence |
| --- | --- | --- | --- |
| TSK-600/601 | Shared snapshot and SoD helpers | integration review required | shared tests; no Workflow rows |
| TSK-590 | Stock Entry — Material Transfer | source worktree available | focused tests + migration/browser evidence |
| TSK-591 | Stock Reconciliation | source evidence incomplete | focused tests + migration/browser evidence |
| TSK-592 | Asset Movement | source worktree available | focused tests + migration/browser evidence |
| TSK-593 / TSK-603 | Manual Journal Entry | source worktree available | focused tests + generator non-bypass + migration/browser evidence |
| TSK-594 | Sales Order | demo source only; production adapter review required | focused tests + migration/browser evidence |
| TSK-595 | Sales Invoice Return/Credit Note | source worktree available | focused tests + migration/browser evidence |
| TSK-596 | Purchase Order | source worktree available | focused tests + migration/browser evidence |
| TSK-597 | Purchase Invoice | trial source only; production adapter review required | focused tests + migration/browser evidence |
| TSK-598 | Payment Entry | POC source only; production adapter review required | focused tests + migration/browser evidence |
| TSK-599 | Payroll Entry | source worktree available | focused tests + migration/browser evidence |
| TSK-602 | Normalized fixture/migration integration | active | exactly ten routes; history-safe repeatable migration; final gates |

## Historical WF-01–18 task register (superseded business-workflow taxonomy)

| ID                          | Status                             | Start dependencies                                        | Close dependencies / evidence                                               |
| --------------------------- | ---------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------- |
| AUDIT-BASELINE              | Completed for `local` audit target | None                                                      | Recheck findings affected by any source/config/target change                |
| DECISION-REGISTER           | Active                             | Audit                                                     | Approved revision/effective date and route scope per decision               |
| TSK-512-ENABLED-ROUTES      | Paused/incomplete external task    | D-TRANSFER or D-ASSET per route                           | Canonical Item Request/tracked-equipment evidence for each enabled consumer |
| TSK-521-TRANSFER            | Required; not accepted             | D-TRANSFER, 531 Core                                      | WF-01/02 native direct/transit, receipt, retry and conservation evidence    |
| TSK-523-ASSET-EQUIPMENT     | Blocked at Computer Use acceptance | D-ASSET-2026-09-26, accepted TSK-600/601 shared controls  | Browser-capable host; final docs after acceptance; WF-08 remains disabled   |
| TSK-524-ASSET-DISPOSAL      | Required; not accepted             | D-ASSET-DISPOSAL, 531 Core; 529 for receipt/refund        | WF-07 Asset Register/GL/reversal evidence                                   |
| SHARED-531-CORE             | Blocked                            | D-CORE, required D-IDENTITY, approved target, plan review | Contract tests; no domain/config ownership                                  |
| SHARED-531-ADAPTER-COVERAGE | Blocked                            | Core plus enabled adapters                                | WF-15/16/17 evidence across every protected route                           |
| SHARED-522-CORE             | Blocked                            | D-STOCK, SHARED-531-CORE                                  | Freeze/exception/reference-time contract tests                              |
| SHARED-522-COUNT-COVERAGE   | Blocked                            | Core plus stock consumers                                 | WF-03/04/05 cross-entry-point evidence                                      |
| SHARED-529-CORE             | Blocked                            | D-PAYMENT, SHARED-531-CORE                                | Payment identity/bank evidence/post/retry/settlement contract               |
| SHARED-529-HANDOFF-COVERAGE | Blocked                            | Core plus refund/AP/payroll consumers                     | WF-10/12/13/14 integration evidence                                         |
| STOCK-01-02                 | Blocked                            | D-STOCK, 531 Core, 522 Core                               | Count/recount/freeze/native reconciliation evidence                         |
| SALES-03                    | Blocked                            | D-SALES, 531 Core, native credit contract                 | Downstream and applicable cross-module tests                                |
| CREDIT-04-CORE              | Blocked                            | D-CREDIT, 531 Core, native invoice/return contract        | Credit/write-off tests; no blanket SALES-03 dependency                      |
| CREDIT-04-REFUND            | Blocked                            | Credit Core, 529 Core                                     | Allocation/refund/settlement tests                                          |
| PROCURE-05                  | Blocked                            | D-PROCURE, 531 Core, demand/PO/PR contract                | PR/PI handoff for enabled routes                                            |
| AP-06-CORE                  | Blocked                            | D-AP, 531 Core, approved PO/PR/PI contract                | Duplicate/match/posting tests                                               |
| AP-06-PAYMENT-HANDOFF       | Blocked                            | AP Core, 529 Core                                         | Advance/balance/payment integration                                         |
| PAYROLL-07-CORE             | Blocked                            | D-PAYROLL, 531 Core, Payroll Entry contract               | Review/accrual/recovery/privacy evidence                                    |
| PAYROLL-07-BANK-HANDOFF     | Blocked                            | Payroll Core, 529 Core                                    | Bank JE/evidence/settlement tests; no duplicate PE                          |
| CONFIG-PAYMENT              | Blocked                            | D-PAYMENT, approved site owner/target                     | Desired state, pending PE/actions, permissions, migration/re-run/rollback   |
| TSK-603-JOURNAL-ENTRY       | Route implementation; integration review required | D-CORE, D-IDENTITY, approved manual-JE actor contract | Manual Journal Entry tests, collision-aware migration, browser evidence |
| TSK-602-NORMALIZED-BASELINE | Plan review                        | Target snapshot, TSK-600/601, route source decisions      | Exactly ten routes, guarded migration/recovery, G0–G4 evidence              |
| FREEZE-08-REGISTER          | Active (documentation only)        | Scope/traceability contract                               | Complete owner/decision/evidence row for WF-01–18                           |
| FREEZE-08-SIGNOFF           | Blocked                            | All required coverage                                     | G0–G4, manifest, migration rehearsal, independent sign-off                  |

## Ownership and dispatch rules

- Each task receives exact exclusive files, excluded shared files, test ownership, migration and
  rollback impact before `ready`.
- One serialized integration owner controls `hooks.py`, `patches.txt`, setup-managed configuration, and
  migration ordering. The current dirty versions remain contested and excluded.
- Native Frappe/ERPNext/HRMS source is read-only.
- A core contract passing does not close its parent Main Task; coverage closes only after every
  enabled adapter and alternate entry point is verified.
- TSK-521 owns WF-01/02, TSK-523 owns WF-06/08, TSK-524 owns WF-07, and TSK-512 supplies evidence
  only for enabled canonical Item Request/tracked-equipment routes.
- These four rows are required dependencies, not completion claims. Exact files remain with their
  existing task owners and must be recorded before dispatch; FREEZE-08 consumes their accepted
  evidence rather than reimplementing them.

## Restart procedure

1. Read this file, `spec.md`, `decisions.md`, `verification.md`, and the selected slice.
2. Recompute the baseline if any recorded hash, commit, target, or effective configuration changed.
3. Resolve only the decisions required by the next slice; record owner, revision, effective date,
   enabled/deferred routes, and impacts.
4. Assign exact files and obtain independent plan review before editing.
5. Implement the bounded slice, run focused automated tests, obtain independent code review, fix all blocking findings, and re-review before final integration.
6. Never run migrate/install/update/fixture sync on shared DEV/UAT while contested dirty
   Workflow/configuration artifacts are reachable.
7. Run the final automated gates for the integrated slice before browser validation.
8. Run Computer Use acceptance on the approved DEV target for every affected workflow and role handoff. Record actor/role, route, prerequisites, exact UI actions, expected/actual state, permission result, downstream side effects, and durable evidence. Do not use browser success as a substitute for automated coverage.
9. After Computer Use passes, finalize the shipped behavior under the canonical `docs/<module>/<workflow>/` structure and update `docs/<module>/behavior.md` when module-wide behavior changed. Final docs contain no task status, TODOs, temporary evidence, or speculative behavior.
10. Independently review the documentation against the accepted implementation and runtime evidence.
11. Attach current native positive, negative, bypass, retry, concurrency, correction, migration,
    recovery, Computer Use, and final-documentation evidence before accepting a task.
