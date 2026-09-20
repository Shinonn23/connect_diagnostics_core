# Workflow baseline implementation

Status: planning checkpoint accepted; no runtime implementation slice is ready.

This record supersedes conflicting assumptions in the eight attached plans. It does not treat
planning text, task status, fixture presence, or old tests as runtime evidence. The complete goal
remains all required WF-01–18 implementation and evidence gates; this checkpoint does not narrow
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
- Plan 01–08 corrections and WF-01–18 ownership are recorded in `spec.md`.
- `slices/shared-531-core.md` is the selected first runtime slice. Its plan is bounded, but the
  slice is blocked until D-CORE, required D-IDENTITY decisions, target approval, exact files, and
  a second independent readiness review are complete.

## Dependency graph

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

## Task register

| ID                          | Status                             | Start dependencies                                        | Close dependencies / evidence                                               |
| --------------------------- | ---------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------- |
| AUDIT-BASELINE              | Completed for `local` audit target | None                                                      | Recheck findings affected by any source/config/target change                |
| DECISION-REGISTER           | Active                             | Audit                                                     | Approved revision/effective date and route scope per decision               |
| TSK-512-ENABLED-ROUTES      | Paused/incomplete external task    | D-TRANSFER or D-ASSET per route                           | Canonical Item Request/tracked-equipment evidence for each enabled consumer |
| TSK-521-TRANSFER            | Required; not accepted             | D-TRANSFER, 531 Core                                      | WF-01/02 native direct/transit, receipt, retry and conservation evidence    |
| TSK-523-ASSET-EQUIPMENT     | Required; not accepted             | D-ASSET, 531 Core; 512 for enabled generated routes       | WF-06/08 custody/site/receipt/installation/reversal evidence                |
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
