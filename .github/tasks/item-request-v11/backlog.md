# Item Request v11 implementation backlog

This is the authoritative remaining-work register at the pause checkpoint. Status values are
`accepted`, `ready`, `active`, `blocked`, and `pending`. Nothing below is complete merely
because a function or test file exists.

## Dependency graph

```text
IR11-F0 Physical operation and voucher lineage foundation
├─ IR11-P1 Automatic Demo Plan A/B/C orchestration
├─ IR11-P2 Native Stock→Asset provisioning coordinator
├─ IR11-O1 Shipment outbound verification/remediation
└─ IR11-R0 Shared physical reversal transition helper
   └─ IR11-R1 Return preparation extraction and approval boundary
      ├─ IR11-R2 Stock/equivalent return adapters
      ├─ IR11-R3 Asset return adapter
      └─ IR11-R4 Return Shipment mutation
         └─ IR11-R5 Return aggregate coordinator
            ├─ IR11-Q1 QA/repair/release/send-back
            └─ IR11-X1 Stock/Asset terminal resolution

IR11-C1 Configuration and Fulfillment Site actions
IR11-C2 Close/reopen
IR11-A1 Complete public API and Desk actions
IR11-G1 Integrated gates and Desk verification
```

## IR11-F0 — Physical operation and native voucher lineage foundation

Status: **active changes interrupted; independent review has open P1 findings**.

Owned files when resumed:

- `services/item_request/operations.py`
- `services/item_request/stock_execution.py`
- `services/item_request/voucher_protection.py`
- focused operation/stock/voucher tests

Required work:

- Remove obsolete `_DOMAIN_MUTATIONS["submit_asset_provisioning"]`; Provisioning submit must
  have exactly one identity: Physical `provisioning:<provisioning>` with the Provisioning
  record as primary and revision owner.
- Retain the constrained stock tuple only:
  `Provisioning / Material Issue / Low Value Issue`, created by the Plan-owned
  `prepare_asset_provisioning` mutation and submitted by the Physical operation.
- Enforce Asset Movement stored `sequence` against the unit/epoch-derived voucher identity.
- Add real Asset Capitalization parent→Stock Item child lineage validation. Each child needs a
  child-specific doctype-qualified key, immutable provisioning/unit lineage, reload validation,
  and tamper rejection.
- Prove forged family, purpose, phase, creator, owner, provisioning, unit, sequence, and key are
  rejected. Preserve Outbound/Receipt/Return behavior.

Accepted only when focused persisted tests cover low-value Stock Entry/SABB and high-value
Capitalization parent/child lineage, physical-operation tests pass, and an independent reviewer
reports no P0/P1 findings.

## IR11-P1 — Automatic Demo Plan and future claims

Status: **plan reviewed twice; final corrected contract awaits final confirmation and code**.

Owned files:

- `planning.py`, `plan_execution.py`, `automatic_demo.py`, `locks.py`
- Plan controller only for an explicitly reviewed controlled-field table
- focused Plan/future-claim/scheduler tests

Required contract:

- Prepare freezes the Company-configured Demo source Site/warehouse/location snapshot before
  Asset locks or Draft Fulfillments.
- Current Assets are selected deterministically first. Wait creates `ASSET_FUTURE`; Convert and
  automatic shortage create no future claim.
- No provisioning before the immutable fallback date. Invalid claims may be retired earlier,
  but actual shortage is provisioned only on the next business day after the latest selected
  expected-return date.
- The provisioning handoff is three committed transactions with no manual commit:
  - A: prepare/advance Plan Mutation creates exact deterministic Provisioning parent(s), stores
    `prepare_operation`, source/assessment/fallback snapshots, and completes.
  - B: each separate Physical `provisioning:<name>` operation submits native work only.
  - C: registered `complete_automatic_demo_provisioning` Mutation validates
    `{prepare_operation, sorted provisioning_names, A resulting Plan revision}`, bridges exactly
    those submitted parents to Asset Fulfillments, and sets Ready only at full row coverage.
- A enqueues B after commit; B enqueues C after commit. HTTP returns pending. Recovery resumes
  only exact persisted correlations and never infers from all Provisioning rows for a Plan.
- Release handoff lock order covers both source and waiting Requests/Plans deterministically;
  handoff is legal only after accepted QA and physical release to the frozen source.

Acceptance includes sufficient-current-Asset, immediate Convert, no-eligible-return automatic
conversion, Wait/handoff, fallback once, crash after A/B/C, concurrent claim/fallback, reset,
reversal, and no requester leakage.

## IR11-P2 — Native low/high Stock→Asset provisioning coordinator

Status: **blocked by IR11-F0 and known P1 defects**.

Owned files:

- `asset_provisioning.py`
- Provisioning parent/unit controllers
- provisioning native integration tests

Known defects to resolve:

- Low-value scope currently grants `("Stock Entry", entry.name)` before `entry.name` exists.
- Generated Asset insertion lacks the exact operation-scope grant.
- High-value `_asset_capitalization` invocation has an argument-count mismatch.
- The Plan replacement bridge is called while Provisioning is still `Prepared`, although the
  bridge requires `Submitted`; the subsequent Provisioning save also lacks its grant.
- Asset Capitalization is omitted from Physical Operation generated references.
- Stock/Bin/Batch/Serial/SABB/valuation revalidation and reversal are not proven end to end.
- Dead/shadowed old submit code remains and must not expose a second identity path.

Acceptance requires real native low/high submit, SLE/GL/account assertions, zero-NBV low-value
Asset, normal depreciable high-value Asset, complete lineage, response-loss replay, rollback on
each native leg, contention, and legal native reversal before downstream use.

## IR11-O1 — Shipment outbound lifecycle

Status: **implementation present; independent review and native mixed-route integration absent**.

Review `outbound.py`, `shipment.py`, `receipt_execution.py`, Stock/Asset adapters, API wrappers,
and tests. Prove one Shipment per epoch, Source→Transit atomic mixed routes, In Transit
Obligations, receipt Transit→Destination, Employee-B snapshot/signature, no-return lock release
at receipt, named reverse, redispatch with new voucher keys, and no downstream reversal.

## IR11-R0 through IR11-R5 — Return aggregate

Status: **implementation plan independently accepted; code remains incomplete**.

Order and ownership:

1. `IR11-R0`: add one typed helper in `operations.py` for named reversal to transition the
   original Physical operation history/epoch. Replace divergent raw mutations later.
2. `IR11-R1`: compatibility-preserving mechanical extraction of preparation/approval from
   `return_execution.py`; keep public imports stable. Match preparation accepts only
   obligation/slice/previous/return serial/return batch. Equivalent approval accepts only
   origin/replacement plus cross-item reason/acknowledgement.
3. `IR11-R2`: Stock/equivalent adapter. Aggregate derives and locks every sorted/deduplicated
   original+replacement Bin/Batch/Serial resource once, then passes `LockedStockResource` to
   adapters for exact revalidation/execution. Integrate Existing Custody, External Supplied,
   original-removal-once, carry, clearing, native facts, and inverse reversal order.
4. `IR11-R3`: exact Asset adapter. Aggregate locks Assets once and passes locked
   `AssetMovementState`; adapters never acquire fresh Asset locks.
5. `IR11-R4`: `make_return_shipment` is a Return-primary idempotent Mutation. It creates one
   server-derived Shipment and increments Return revision. Physical Return Dispatch derives the
   current-epoch Shipment from lineage and never accepts a client Shipment.
6. `IR11-R5`: sole aggregate writer. It owns global lock order, native adapter calls, typed
   submitted voucher/SLE/dependency/substitution/removal facts, Match stages, Return projection,
   Obligation balances, retries, and named reversals in one atomic operation.

Required E2E: exact Stock/Asset direct and Shipment, first Existing Custody Transfer+Issue and
rollback, External first Repack and later carry receipt, same/cross-item permissions, stale
valuation denial, serial/batch concurrency, response loss, all three return reversal semantics,
generated voucher/bundle bypass, and protected valuation/repost scope.

## IR11-Q1 — QA, repair, release, and rejected send-back

Status: **pending IR11-R5**.

Implement native repair/release/send-back execution around existing inspection kernels.
Repair completion clears acceptance and requires a fresh accepted inspection. Release returns to
the frozen original internal Plan source only. Asset future-claim handoff occurs inside successful
Release after native movement submit and before completion; any handoff failure rolls everything
back. Add named reversals with downstream-use guards.

## IR11-X1 — Stock and Asset terminal resolution

Status: **pending IR11-R5/IR11-Q1**.

Implement write-off and THB settlement without duplicate physical issue, including carry-only
chains and zero terminal clearing. Settlement closes obligation when JE submits; collection stays
in accounting. Asset reversal must use native `restore_asset` semantics and verify status,
disposal fields, depreciation schedules/finance books, GL, obligation, and lock together.

## IR11-C1 — Configuration and Fulfillment Site actions

Status: **plan review interrupted at pause**.

Implement Stock Manager-only `create_external_custody_warehouse` and
`validate_item_request_configuration`. Preserve leaf/company/customer rules, Employee warehouse
customer blank, configured parent only, no auto-create, no fallback, and native Warehouse customer
semantics regression. Fix the current deletion guard that queries nonexistent Plan
`delivery_site`; Plan references use frozen dispatch snapshots. Define idempotency without forcing
the existing Item Request Operation schema to represent a configuration action with no Request.
Prove reassignment/unlink/delete guards against SLE, Request, Plan, and active Obligation.

## IR11-C2 / IR11-A1 — Close, public API, and Desk

Status: **pending terminal coordinators**.

- Close/reopen is Stock Manager-only, keeps docstatus 1, requires Delivered and no active debt,
  active Return, or pending Operation; Reopen only clears the close projection.
- Reconcile every method in `spec.md` with a service and POST-only facade. Reject server-controlled
  route/resource fields recursively and preserve `{data, message}`.
- Add minimal role-aware Desk actions without exposing Asset, warehouse, serial, valuation, or
  lock identity to requester. Generated native vouchers remain read-only/source-linked.

## IR11-G1 — Final gates

Status: **pending all tasks**.

Run clean migrate, complete focused/native integration matrix, full app suite, patch tests,
metadata/export/navigation checks, `pre-commit run --all-files`, and real Desk verification for
Requester, Approver, Stock User, Stock Manager, Account Manager, and System Manager. No production
promotion or legacy migration is part of v11.
