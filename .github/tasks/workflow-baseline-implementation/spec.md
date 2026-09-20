# Workflow implementation specification

## Plan 01–08 corrections

This matrix is authoritative for implementation until the source plans are replaced. It records
where audit evidence invalidated an old assumption without discarding the original requirement.

| Plan | Corrected implementation contract | Decisions | Owner/evidence |
| --- | --- | --- | --- |
| 01 Full/Cycle Count | Do not reuse/revive retired Count code. Preserve snapshot, blind count, completeness and close requirements; pass accepted target quantity once to native Stock Reconciliation. | D-STOCK | STOCK-01-02; native reconciliation artifacts |
| 02 Variance/Recount | Store append-only recount/decision evidence in the approved new model; never create a second posting engine. | D-STOCK, D-IDENTITY | STOCK-01-02 + 522 coverage |
| 03 Sales/Credit | Reviewed allowlisted native Workflow fixtures may provide the approved route configuration; server validation remains in the adapter and native exposure is reused only after the credit contract is verified. | D-SALES, D-IDENTITY | SALES-03 tests, configuration manifest and native SO/DN/SI evidence |
| 04 Credit/Write-off | Credit/write-off core depends on native original invoice/return facts, not all of SALES-03. Refund is a separate 529 consumer. | D-CREDIT, D-PAYMENT | CREDIT-04 Core/Refund evidence |
| 05 Procurement | Site configuration contract plus server validation adapter; preserve native RFQ/SQ/PO/PR effects. | D-PROCURE, D-IDENTITY | PROCURE-05 evidence |
| 06 PI/Payment handoff | Separate AP matching/posting core from payment handoff; do not combine stock receipt or settlement engines. | D-AP, D-PAYMENT | AP-06 Core/Handoff evidence |
| 07 Payroll | No Salary Slip Workflow and no payment voucher duplicating native payroll Bank JE; review binds to Payroll Entry/slip revisions. | D-PAYROLL, D-PAYMENT | Payroll Core/Bank evidence |
| 08 Baseline Freeze | Separate app release artifacts from site-owned configuration artifacts; register may start early, sign-off requires every required WF-01–17. | All enabled-route decisions | G0–G4 manifest/evidence/sign-off |

The shared-controls source plan is also corrected: Workflow fixtures are limited to reviewed,
allowlisted native configuration with explicit collision, migration/re-run and recovery contracts;
531, 522 and 529 remain split into stable core contracts and downstream adapter-coverage tasks.

## WF-01–18 coverage ownership

| WF | Workflow | Implementation owner | Decision/core gates | Required evidence location |
| --- | --- | --- | --- | --- |
| 01 | Internal Location Transfer | TSK-521 | D-CORE, D-TRANSFER, 531 Core | TSK-521 native transfer evidence |
| 02 | Warehouse Transfer | TSK-521 | D-CORE, D-TRANSFER, 531 Core | TSK-521 direct/transit evidence |
| 03 | Emergency Movement During Freeze | TSK-522 | D-STOCK, 531/522 Core | 522 Count Coverage |
| 04 | Full/Cycle Stock Count | TSK-77 / Plan 01 | D-STOCK, 531/522 Core | STOCK-01-02 evidence |
| 05 | Variance/Recount | TSK-77 / Plan 02 | D-STOCK, D-IDENTITY, 531/522 Core | STOCK-01-02 evidence |
| 06 | Asset Movement/Transfer | TSK-523 | D-ASSET, 531 Core | TSK-523 native movement evidence |
| 07 | Asset Disposal | TSK-524 | D-ASSET-DISPOSAL, 531/529 Core as applicable | TSK-524 Asset Register/GL evidence |
| 08 | Equipment Assignment/Installation | TSK-523 + enabled TSK-512 routes | D-ASSET, 531 Core | TSK-523/512 custody/site evidence |
| 09 | Sales Order/Credit Approval | TSK-525 / Plan 03 | D-SALES, 531 Core | SALES-03 evidence |
| 10 | Credit Note/AR Write-off | TSK-526 / Plan 04 | D-CREDIT; D-PAYMENT for refund | CREDIT-04 Core/Refund evidence |
| 11 | Procurement Approval | TSK-527 / Plan 05 | D-PROCURE, 531 Core | PROCURE-05 evidence |
| 12 | PI/Payment Handoff | TSK-528 / Plan 06 | D-AP; D-PAYMENT for handoff | AP-06 Core/Handoff evidence |
| 13 | Payment Approval | TSK-529 | D-PAYMENT, 531/529 Core, CONFIG-PAYMENT | 529 coverage + site config evidence |
| 14 | Payroll Processing/Review | TSK-530 / Plan 07 | D-PAYROLL; D-PAYMENT for bank | Payroll Core/Bank evidence |
| 15 | Role/Scope Assignment | TSK-531 | D-CORE, D-IDENTITY, 531 Core | 531 Adapter Coverage |
| 16 | Backup Approver/Delegation | TSK-531 | D-IDENTITY, 531 Core | 531 Adapter Coverage |
| 17 | Self-Approval Protection | TSK-531 + every module | D-IDENTITY, 531 Core | Per-adapter identity evidence |
| 18 | Workflow Baseline Freeze | TSK-532 / Plan 08 | All required enabled-route gates | Register, manifest, G0–G4 sign-off |

Every enabled TSK-512 route must be named in the register. Disabled/deferred routes require owner,
reason and effective scope and do not count as passed.

## Cross-cutting invariants

- Approval is revision-bound, server-enforced, independently authorized and rechecked at the
  protected native action; UI state is never authorization.
- Retry uses trusted operation/source identity; equal amounts are not duplicate identity.
- Current-state locks prevent double posting, over-allocation and conflicting resource actions.
- Correction preserves history through supported native cancel/amend/reversal routes.
- Each protected route maps UI, REST/RPC, import/bulk, generated document, queue/background,
  post-submit update, cancel/amend/reopen, report/export/print/email, first native effect,
  transaction boundary, lock, permission, privacy and audit evidence.

## Delivery gates

- G0: fixed constraints, WF-01–18 scope, route decisions, owners, exact files and target baseline.
- G1: native positive/negative/bypass/retry/concurrency/correction evidence per module.
- G2: cross-module revision, lock, provenance, ledger, history and privacy evidence.
- G3: clean install, populated upgrade, repeated migrate, pending-document handling and recovery.
- G4: technical and business owners sign exact version/scope/evidence.
