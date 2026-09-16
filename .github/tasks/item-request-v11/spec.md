# Item Request and Asset Fulfillment v11

**Target:** Frappe 16.31.0 and ERPNext 16.32.1.  This record is the normative v11
source of truth for the greenfield Item Request domain.  v11 supersedes v10: the
Equipment module and every Equipment route, record, lock, API, menu, and test are
removed.  There is no legacy-data conversion because the old design never reached
production; a clean install/migrate is required.

## 1. Intent and automatic routing

An Item Request stores only Company, Employee, Required By, Request Type
(`Transfer | Demo | Borrow`), Delivery Site, Return Required/Expected Return Date,
and Requestable Item/UOM/Qty rows.  The requester never chooses warehouse,
location, asset, batch, serial, pickup, dispatch address, or route.  One request
has one complete outbound cycle; partial dispatch is forbidden.

The execution graph is:

```text
Item Request -> Fulfillment Plan -> Fulfillment (Stock | Asset)
-> native Stock Entry / Asset Movement -> Outbound -> Obligation
-> Return Match -> QA / Repair / Release / Resolution
```

`request_type` is classification only. Demo and Borrow default to
`return_required=1`; external company-controlled custody always requires return.
`return_required=0` is allowed only for an Internal Site.  Stock and Asset are the
only fulfillment routes.  There is no reservation, zero-value demo, Asset/Stock
conversion outside the Demo provisioning rules below, or direct Stock Ledger write.

### Demo route decision

For each Demo row the server, under deterministic locks, assesses usable and
unlocked native Assets mapped by Requestable Item.  It allocates available Assets
first.  A candidate Asset is *expected-return eligible* exactly when its frozen
expected return date is inclusive of both boundaries:

```text
assessment_date <= expected_return_date <= Required By
and expected_return_date <= assessment_date + 30 calendar days
```

The candidate must cover the same mapped Asset Item and be expected to complete its
current obligation; cancelled/reversed obligations and unusable, locked, sold,
scrapped, maintenance, or out-of-order Assets do not qualify.  If there is at least
one current shortage and available Assets plus eligible expected returns cover every
Demo row, the request shows one request-level `Decision Required` prompt.  The
requester must explicitly choose `Wait for Return` or `Convert Stock Now`; the
approver approves that recorded choice.  There is no timeout or automatic choice.
`Wait for Return` waits through the selected frozen expected dates.  On the next
business day after the latest selected expected-return date passes, the server automatically provisions the
remaining shortage once, with fresh locks and valuation; it does not prompt again.
Stock User cannot change the decision or route.

If no eligible return can cover the shortage, Stock→Asset provisioning is automatic.
If the selected/automatic choice is conversion, only the shortage is provisioned.
Assessment is recomputed at Submit for Approval and Plan creation.  A changed
candidate set, Required By, mapping revision, valuation, or fingerprint expires the
old choice and reopens `Decision Required`; no stale choice may create accounting
documents.  If a waited-for Asset is not returned, is written off, or becomes
unusable, the system records that failure immediately but SHALL NOT provision early.
All such remaining shortage is provisioned exactly once, on the next business day
AFTER the latest selected expected-return date, using fresh locks and revaluation;
the system never issues a second prompt.

## 2. Records, quantities, and locks

Master: Requestable Item and Fulfillment Site. Request: Item Request and Item Request
Item. Planning: Item Request Fulfillment Plan and Item Request Fulfillment. Technical:
Item Request Obligation, Item Request Active Lock, Item Request Operation. Return:
Delivery Receipt, Return, Return Match, Unit Return Inspection, and Return Resolution.
`Item Request Resolution Voucher` is a server-managed child audit table.

`route_type` is required and immutable after Allocate. Stock requires stock item,
source/target warehouse, and positive planned Stock-UOM quantity; Asset requires one
native Asset and canonical quantity 1.  The fields are mutually exclusive.  Approval
freezes canonical UOM, conversion factor, precision, and quantity.  Per request row:

```text
required = normalize(requested_qty * frozen_request_to_canonical_factor)
normalize(sum(fulfillment.canonical_qty)) = required
```

Use Decimal round-half-even at frozen precision, never raw float equality or cross-row
offsetting.  Thus 2 Box × 10 Nos/Box requires 20 Nos; 19/21 fail.  Stock return and
obligation quantities use Stock UOM; Asset quantities are integer physical units.

Unique technical locks are `PLAN::<request>`, `ASSET::<asset>`,
`ASSET_FUTURE::<asset>`, and `RETURN_SERIAL::<serial>`.  The future claim's request and
plan owner are separate fields. PLAN remains from
Draft Plan through execution and prevents a second cycle.  Reset retargets it
atomically.  Asset locks remain through return, write-off, settlement, or reversal.
Future claims do not release the current owner's Asset lock; on verified receipt the
lock and claim are retargeted atomically to the waiting Plan.  Direct Not Required
delivery releases the unit lock atomically; Shipment releases it at receipt.  Reverse
Receipt may reacquire it only when no later allocation/movement/use exists.  Native
Asset Movement, scrap, repair, and normal API paths must reject movement of locked
units unless executing the owning coordinator.

Operations are POST-only, server-derived and idempotent.  Initial `make_*` calls take
the server-issued expected state revision; Operation stores input and resulting
revisions and typed input hash.  Physical keys are dispatch, receipt, return-dispatch,
return-receipt, direct-return, release, and resolution; epochs distinguish cancelled
voucher history.  `voucher_key` is separate and unique per native DocType, derived
from operation/epoch/phase/sequence.  Concurrent retries wait and return the same
result or a retryable conflict.  Failure rolls back Operation, vouchers, locks, and
state.  Lock order is Operation → Request → Plan → sorted Fulfillments → Obligations /
Matches → Locks → Stock resources → Assets → downstream drafts.

## 3. Approval, snapshots, and lifecycle

Approval states are Draft, Pending Approval, Rejected, Withdrawn, Approved (docstatus
1), and Cancelled (docstatus 2).  Direct approval services own persistence when no
Workflow is active.  A compatible Workflow must use the same states, synchronous
domain task, same-document native Save/Submit/Cancel ownership, and invariant kernel;
async domain tasks or background submission are Configuration Errors.  Workflow
compatibility is checked on every action and is never cached across configuration
revisions.  JE has no Item Request approval workflow: Account Manager may submit JE
through native accounting permissions.

Submit for Approval refreshes and freezes Delivery Site, address/contact/warehouse/
location, Requestable Item mapping and UOM snapshots.  Allocate freezes dispatch
endpoint snapshots.  Downstream reads snapshots, not changed masters.

Outbound derives Not Planned → Planned → In Transit → Delivered.  Return derives Not
Required → Outstanding → In Progress → Completed/Cancelled.  `return_due_qty` is zero
when not required; Not Required preserves fulfilled quantity.  Close keeps docstatus 1,
requires Delivered, no debt/active return/pending operation, and records controlled
close audit fields.  Reopen only clears that projection.  Cancel after submitted
outbound is blocked; reverse and reset are required first.  Delivered requests use
Return/Resolution and Close.

## 4. Stock→Asset provisioning

Demo provisioning is a first-class server-managed `Item Request Asset Provisioning`
record (and unit children), linking Request/Plan/row, source Stock Entry or Asset
Capitalization, native Asset, actual unit value, threshold snapshot, and reversal
state.  Provisioning completes before final allocation, then Fulfillment remains a
normal Asset route linked to each created Asset.

The Company must use THB as its default currency.  The fixed threshold is THB 10,000
per physical unit (not configurable): positive value `< 10,000` uses one native
Material Issue (Credit Inventory, Debit configured Low-Value Asset Expense) and then
one native Asset per unit with `asset_type=Existing Asset`,
`net_purchase_amount = opening_accumulated_depreciation = actual_unit_value > 0`,
`calculate_depreciation=0`, and `value_after_depreciation=0` (zero NBV).  The Asset
record posts no second GL.  The mapped native asset_item's ordinary Asset Category
is reused; no separate low-value category is required.
Value `>= 10,000` uses one Composite Asset draft per physical unit and native Asset
Capitalization.  The same mapped asset_item/category may be used, but that category
must have valid finance-book and depreciation settings for the high-value path.
Zero/negative or missing value, non-THB Company currency, or invalid category/account
configuration is a Configuration Error; no guessed account/category is allowed.
Stock source, serial/batch, Bin and valuation are locked and revalidated.  Provisioning
is atomic with every unit creation; failure rolls back stock issue/capitalization,
assets, locks, and Operation.  Reversal uses native cancellation/restoration semantics
and is legal only before downstream allocation/movement/use.

Company configuration stores Demo source Site/location, low-value Expense Account,
Asset transit/QA/repair locations, clearing account,
Stock Adjustment Account, and existing native transit/receivable/disposal accounts.
Every action validates required configuration before any draft is created.

## 5. Outbound, return, valuation, and native safety

Direct submits Source→Destination Stock Entries and canonical Asset Movement sequences
atomically, then creates one Obligation per Fulfillment. Shipment submits Source→Transit
and Shipment atomically; receipt submits Transit→Destination and Delivery Receipt with
Employee-B snapshot signature or Stock Manager override/reason.  Return direct moves
custody→QA; Shipment return moves custody→Return Transit then receipt to QA.  There is
no generic reverse: named reversal actions preserve audit history.  Reverse receipt
does not undo substitution; reverse return dispatch/direct return does, in dependency
order.  Rejected return remains QA until send-back or resolution.  Repair completion
requires a new accepted inspection before release.

Equivalent Stock return is 1:1 in Stock UOM; Asset return is exact.  Substitution
lineage belongs to the obligation quantity slice; represented original is removed at
most once.  Existing-custody and External-Supplied origin cannot switch mid-chain.
External Repack must be value-neutral.  FIFO/LIFO/Moving Average preview is hashed and
revalidated under lock; future/Standard Cost variance is blocked.  Rejected exchange
uses only configured Clearing.  Carry-only write-off/settlement uses protected JE and
never issues stock that is already gone; terminal Clearing must be zero. Settlement JE
completion closes the obligation immediately; collection remains normal accounting.
Settlement is Company currency only in v11.

Native Asset resolution reversal uses `restore_asset` semantics: disposal depreciation,
schedules/finance books, disposal references, status, GL, obligation, and lock are
checked together; pre-existing depreciation is never cancelled wholesale.
Retroactive SLE/GL/Repost is blocked only when it intersects a protected exchange chain;
unrelated current work remains legal.  Generated native vouchers and Bundles are
read-only/source-linked and cannot be bypassed by Desk, API, or `ignore_permissions`.

## 6. APIs, roles, navigation, and gates

The public facade is `connect_diagnostics_core.api.erpnext.item_request`; there is no
equipment facade.  It exposes approval, plan, dispatch, shipment/receipt, return,
inspection/repair/release/resolution, configuration, close/reopen, and provisioning
methods named in the implementation contract.  All mutation endpoints are POST-only,
permission checked, revision/epoch locked, idempotent, and return
`{"data": ..., "message": ...}`.  Route/asset selection is never accepted from Stock
User.

Item Requester owns drafts, approval request, and assigned Employee receipt confirmation.
Approver approves/rejects.  Stock User operates plan/dispatch/return/inspection and
same-item equivalence.  Stock Manager configures, overrides/reverses, closes, writes
off, settles, and performs cross-item equivalence.  System Manager has full domain
access.  No generic accounting permission is granted to Stock Manager.

Navigation places Item Request after Material Request and Requestable Item/Fulfillment
Site in Stock Setup; technical DocTypes have no standalone menu.  No Equipment module,
workspace, sidebar, desktop icon, or menu exists.

Freeze gates must prove UOM/row isolation, automatic Asset-first Demo routing, inclusive
30-day/Required-By decision and fallback, ASSET_FUTURE concurrency, low/high-value
atomic provisioning and reversal, Not Required lock lifecycle, dispatch/return
reversal, replacement carry closure, native Asset restore, Workflow/direct API guards,
voucher protection, protected repost scope, clean install/migrate, unit/integration/
patch tests, `pre-commit run --all-files`, and Desk verification for every role.

## 7. Retained native integration detail

### Sites and endpoints

Internal Sites map to internal leaf Warehouses and Asset Locations. Customer Sites use
a dedicated same-Company leaf Warehouse whose native `customer` equals the Site Customer.
Employee Sites use a dedicated leaf Warehouse with `customer` empty and retain Employee
on the Site. Warehouses are created only by Stock Manager below the configured external
custody parent, never on Site insert. Reassignment/unlink is blocked after any SLE or
active Obligation; Site deletion is blocked by Request, Plan, SLE, or Obligation. External
Site A→B is forbidden: use Return→QA→Release→new Request. Endpoint/address/contact/
warehouse/location/custodian values are frozen snapshots.

Required configuration is checked before drafting: external custody parent, native
Company outbound transit, return transit, Asset transit Location, QA Hold Warehouse/
Location, Repair Warehouse/Location, exchange Clearing Account, Stock Adjustment Account,
native Receivable and Disposal Accounts, `Company.custom_demo_source_site` (a Link to
an Internal, same-Company Fulfillment Site, whose Warehouse and Location are snapshotted),
and `Company.custom_demo_low_value_asset_expense_account` (a Link to an existing
same-Company P&L expense Account). No account auto-creation or guessed fallback is legal.
Company default currency must be THB.

### Shipment, receipt, and Asset movement

Direct submits Source→Destination Stock Entries and canonical Asset Movement steps
atomically. Shipment submits Source→Transit plus Shipment; receipt submits Transit→
Destination plus Delivery Receipt. Shipment adds only Employee options/links and approved
Address/Contact visibility/mandatory behavior is implemented by the server/client adapter;
no Property Setter is used for it. The server adapter populates pickup,
delivery, Employee snapshot, Address/Contact links and rendered values, parcel count/weight,
positive declared transport value, and native `value_of_goods`, even when client JS is
absent. Employee Site receipt is confirmed by the Employee in the frozen snapshot;
Customer/Internal receipt uses the requester. Stock Manager override requires a reason.

All Asset legs use the pure DB-free `plan_asset_movement(current_location,
current_employee,target_location,target_employee)` function:

| Location | Custodian | Steps |
|---|---|---|
| same | same | none |
| same | none→Y | Issue |
| same | X→none | Receipt |
| same | X→Y | Issue(from X,to Y) |
| different | none→none | Transfer |
| different | none→Y | Transfer, Issue |
| different | X→none | Receipt, Transfer |
| different | X→Y | Transfer and Issue(from X,to Y) |

Different locations with the same Employee use Transfer and Issue, never plain Transfer.
Caller locks/revalidates state, submits steps atomically in order, and reverses in reverse
order. Fully depreciated but usable Assets are eligible; Sold, Scrapped, In Maintenance,
Out of Order, or locked Assets are not. Generated Asset Repair always has
`capitalize_repair_cost=0`.

## 8. Full API and reversal contract

The complete public API is:

```text
submit_for_approval, withdraw_approval_request, approve_item_request, reject_item_request
make_fulfillment_plan, prepare_fulfillment_plan, allocate_fulfillment_plan, reset_fulfillment_plan
assess_demo_supply, choose_demo_supply_decision, prepare_dispatch, prepare_stock_dispatch
make_shipment, prepare_shipment, submit_direct_dispatch, submit_shipment_dispatch
confirm_receipt, override_receipt, reverse_receipt, reverse_shipment_dispatch
make_return, prepare_return, prepare_return_stock, approve_equivalent_item, allocate_return
reset_return, make_return_shipment, submit_direct_return, submit_return_shipment
confirm_return_receipt, reverse_return_receipt, reverse_return_shipment, reverse_direct_return
make_return_inspection, submit_return_inspection, record_return_disposition
reverse_return_inspection, send_return_to_repair, complete_return_repair, reverse_return_repair
release_accepted_returns, reverse_release, send_rejected_return_back, make_return_resolution
submit_return_resolution, reverse_return_resolution, close_item_request, reopen_item_request
create_external_custody_warehouse, validate_item_request_configuration
prepare_asset_provisioning, submit_asset_provisioning, reverse_asset_provisioning
```

All mutations are POST-only, permission checked, revision/epoch locked, idempotent, and
return `{"data": ..., "message": ...}`. Operations use server-derived keys; retries with
the same typed input return the original result, while stale epochs conflict. `voucher_key`
is separate from `operation_key`, includes epoch/phase/sequence, and remains unique after
cancellation. Lock order is Operation→Request→Plan→sorted Fulfillments→Obligations/
Matches→Locks→Stock resources→Assets→downstream drafts.

Reversal is explicit: Reset Plan only before movement; outbound In Transit reverses
Shipment and makes Obligation Reversed; bad receipt reverses Transit→Destination only;
Delivered has no generic reverse. Reset Return cancels only its Draft attempt and releases
serial locks while preserving debt. Return In Transit reverses custody→transit and
substitution; Return Received reverses only transit→QA and keeps substitution committed;
Direct Return reverses movement/substitution only without downstream. Inspection, Repair,
Release, and Resolution reverse only without later downstream. Guarded Draft Shipment,
movement, and Bundles are cleaned atomically by Reset; submitted documents require named
reversal first. Native Asset resolution uses `restore_asset` semantics and checks disposal
depreciation, schedules/finance books, references, status, GL, Obligation, and lock together.

| State | Action | Effect |
|---|---|---|
| Plan, no movement | Reset Plan | Cancel/revise Plan and retarget PLAN lock atomically |
| Outbound In Transit, no receipt | Reverse Shipment Dispatch | Cancel shipment/legs; Obligation→Reversed; Plan remains Allocated |
| Outbound receipt wrong, no downstream | Reverse Receipt | Cancel Transit→Destination only; Obligation→In Transit |
| Delivered | no generic reverse | Return/Resolution only |
| Return Planned, no movement | Reset Return | Cancel attempt and release serial locks; debt remains |
| Return In Transit | Reverse Return Shipment | Cancel custody→transit and substitution; restore pre-return state |
| Return Received, no downstream | Reverse Return Receipt | Cancel transit→QA only; substitution remains committed |
| Direct Return submitted, no downstream | Reverse Direct Return | Cancel movement/substitution in dependency order |
| Inspection/Repair/Release/Resolution | matching Reverse action | Allowed only without downstream; preserve all audit lineage |

## 9. Quantities, return, valuation, and protection

```text
completed_qty = exact_released_qty + equivalent_released_qty
              + written_off_qty + settled_qty
return_due_qty = effective_fulfilled_qty if return_required else 0
outstanding_qty = return_due_qty - completed_qty
available_to_return_qty = outstanding_qty - active_return_qty
active_return_qty = planned + in_transit + qa + repairing + ready_to_release
```

Stages are mutually exclusive and enforce completed/active bounds. Native Quality
Inspection stores only Accepted/Rejected; domain disposition stores Accepted, Repairable,
Damaged Beyond Repair, or Rejected Return. Repair requires a fresh accepted inspection.
Release returns only to the original Plan Site snapshot and cannot be changed by Stock User.
Equivalent Stock return is 1:1 Stock UOM; same-item Batch/Serial is Stock User and cross-item
requires Stock Manager reason/valuation acknowledgement. Asset return is exact. Original
removal occurs once per obligation slice; origin class cannot switch. External Repack is
value-neutral. FIFO/LIFO/Moving Average preview is hashed and revalidated under lock;
variance/future Standard Cost is blocked. Clearing-only write-off/settlement never issues
absent stock and leaves Clearing zero. Settlement JE in THB closes the obligation on Submit;
payment remains normal accounting.

Shelf-life validation runs server-side on external Stock Entry, Delivery Note, and Sales
Invoice update_stock. Default is 90 days; zero disables. Expiry <= posting date plus the
configured days, or missing required expiry, is blocked. Return/internal/QA/repair/
replacement/resolution movements are exempt. Generated native vouchers and Serial/Batch
Bundles are source-linked read-only; Desk/API Save, Submit, Cancel, Delete, and
`ignore_permissions` cannot bypass the private coordinator guard.

## 10. Approval, exports, roles, and gates

Compatible Workflow uses the exact approval states/docstatus, synchronous domain tasks,
same document instance and native Save/Submit/Cancel ownership. Async tasks or background
submission are Configuration Errors. The adapter never loads a second instance. Direct
approval owns persistence only when no Workflow is active; JE has no approval workflow and
Account Manager may Submit it through native accounting permissions. Workflow compatibility
is checked every action and not cached.

Customize Form exports retain all lineage on Stock Entry/Detail, Asset Movement/Item,
Asset Capitalization/Stock Item, Shipment, Sales Invoice/Item, Quality Inspection, Asset
Repair, Company, and Stock Settings. They retain `sync_on_migrate=1`, existing permission
rows, and no Warehouse export. Only Shipment `pickup_from_type` and `delivery_to_type`
Select options may use the native Property Setter exception, preserving native ordering and
appending Employee. No other Property Setter is permitted. The approved native Custom Field exceptions are Stock Settings Single
DocType creation and Module assignment only on newly authored lineage fields.

Requester owns drafts and receipt confirmation; Approver approves/rejects; Stock User
operates plans/dispatch/returns/inspection; Stock Manager configures, overrides/reverses,
closes, writes off, settles, and cross-item substitutes; System Manager has full access;
Stock Manager receives no generic accounting permission. Item Request follows Material
Request in Stock, setup masters are in Stock Setup, and technical DocTypes have no menu.
No Equipment module/workspace/sidebar/icon/menu exists.

Gates cover UOM rows, automatic Demo Asset-first and one request-level decision, inclusive
30-day/Required-By wait and one-time fallback, ASSET_FUTURE concurrency, atomic low/high
provisioning and reversal, Not Required locks, full dispatch/return reversal matrix,
substitution/carry closure, native Asset restore, Workflow/API guards, voucher protection,
protected repost scope, clean install/migrate, all tests, pre-commit, and Desk verification
for every role. New requirements after freeze are CR/v12.
