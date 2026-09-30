# TSK-512 isolated Demo lifecycle prototype

## Status

`active`

This record governs an isolated prototype on branch
`feat/tsk-512-borrow-prototype`, based on `developments`. The prototype must not be
merged, deployed, or migrated onto the normal interactive site before the owner reviews the
runtime evidence and resolves the workflow-baseline overlap.

## Goal

Prove and then implement a usable Demo request lifecycle in isolation:

`Material Request (Demo) -> Fulfillment -> existing/reusable Asset or Stock Asset Conversion
-> Asset Movement -> Dispatch -> return or native fixed-asset sale`.

The supplied TSK-512 plan is the functional hypothesis. Existing accepted ERPNext behavior,
repository security policy, and executable evidence remain authoritative when the hypothesis
and the pinned framework disagree.

## Scope and decision boundary

- New Demo behavior is isolated to this worktree, branch, and dedicated `tsk512.test` site.
- No production, UAT, shared DEV, or normal `local` migration is authorized.
- Existing `request_usage` and route fields remain available for historical compatibility.
- Native non-Demo Material Request purposes must remain unchanged.
- ERPNext core and installed dependencies must not be patched.
- Phase 0 is a hard gate. Production-facing schema and UX work cannot begin until the stock,
  GL, Asset, depreciation, cancellation, and sale mechanics pass executable integration tests.
- Stop and return evidence if safe posting requires direct SLE/GL insertion, manual deletion of
  submitted ledgers, an ERPNext core patch, or cannot prevent duplicate acquisition GL.
- Owner review is required before any merge or environment promotion.

## Dependencies and overlap

- TSK-523 owns the workflow-baseline Asset Movement route. This prototype may exercise native
  Asset Movement and adapt Dispatch locally, but it must not claim the TSK-523 workflow scope.
- The workflow-baseline record previously deferred Equipment workflow scope. `Equipment Model`
  in this prototype is only a Stock Item to Fixed Asset Item mapping master, not a posting engine
  or an approval workflow.

## Implementation backlog

| ID | Status | Depends on | Bounded result |
| --- | --- | --- | --- |
| TSK512-P0 | completed | none | Executable native-mechanics proof on `tsk512.test` |
| TSK512-P1 | completed | P0 | Equipment Model mapping, validation, permissions, Stock navigation |
| TSK512-P2 | completed | P1 | Demo-only Material Request UX, query, validation, approval handoff |
| TSK512-P3A | completed | P2 | Idempotent, non-posting Fulfillment snapshot and read-only Desk surface |
| TSK512-P3B | completed | P3A | Reusable/returning Asset reservation and replanning |
| TSK512-P4 | completed | P0,P3 | Production Stock Asset Conversion lifecycle and shared preview/post builders |
| TSK512-P5 | completed | P4 | Native depreciation treatments and preview freshness |
| TSK512-P6 | completed | P3,P4 | Native Asset Movement and existing Dispatch integration for outbound/return |
| TSK512-P7 | completed | P6 | Native fixed-asset Sales Invoice action and reservation blocker |
| TSK512-P8 | completed | P1-P7 | Migration compatibility, full regression, concurrency, and ledger evidence |
| TSK512-UAT | blocked | P8 | Role-by-role Computer Use acceptance on `tsk512.test` |
| TSK512-DOC | proposed | UAT | Canonical documentation and independent documentation review |

## Phase 0 owned files

The first implementation slice is limited to:

- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_asset_conversion/__init__.py`
  — DocType package marker.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_asset_conversion/stock_asset_conversion.json`
  — minimal submittable voucher schema needed by the executable proof.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_asset_conversion/stock_asset_conversion.py`
  — stock/GL/Asset lifecycle using native ERPNext services.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_asset_conversion/test_stock_asset_conversion.py`
  — integration evidence for submit, rollback, cancel, depreciation, and sale mechanics.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_asset_conversion_item/__init__.py`
  — child-table package marker.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_asset_conversion_item/stock_asset_conversion_item.json`
  — the single source-unit row and the exact generic child DocType name required by ERPNext v16
  Serial and Batch Bundle handling (`<voucher type> Item`).
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/stock_asset_conversion_item/stock_asset_conversion_item.py`
  — typed child document controller.
- `connect_diagnostics_core/setup/document_naming.py`
  — register the required `SAC` operational naming prefix.
- `connect_diagnostics_core/setup/tests/test_document_naming.py`
  — naming regression for the new voucher.
- this task record — status, evidence, and restart instructions.

Phase 0 will not change Material Request, Company, Asset, Dispatch, workspaces, fixtures,
permissions, reports, hooks, patches, or accepted documentation.

Any additional file requires an updated complete owned-file list and independent plan review
before editing.

## Phase 0 acceptance criteria

1. One submitted voucher consumes exactly one stock unit through ERPNext stock-ledger services.
2. The removed stock value is the source of a balanced `Dr Fixed Asset / Cr Inventory` posting.
3. One normal ERPNext Asset with no purchase-document acquisition context is created/submitted
   with no duplicate acquisition GL. Validation rejects a composite Asset or an Asset linked to a
   Purchase Receipt/stock-updating Purchase Invoice so the Asset cannot become a second owner of
   acquisition GL. Integration tests cover the accepted and rejected Asset branches.
4. Failure inside the posting transaction leaves no permanent SLE, GL, or submitted Asset.
5. Cancellation uses native reversal behavior and restores stock and GL without deleting ledgers.
6. A native one-entry depreciation schedule can reach zero NBV and still permit native sale.
7. Normal depreciation remains native.
8. Serialized/batched stock follows ERPNext v16 Serial and Batch Bundle rules through the
   repository-owned `Stock Asset Conversion Item` child DocType; no ERPNext source is changed.
9. Focused tests and the repository pre-commit gate pass.

## Phase 1 decision and owned files

The workflow-baseline project removed/deferred an operational **Equipment workflow**. Phase 1 does
not reintroduce that domain: `Equipment Model` is a non-transactional mapping master only, has no
workflow or posting behavior, and ERPNext Item/Asset remain the operational records. This keeps the
prototype within the recorded TSK-512 distinction and leaves TSK-523 Asset Movement ownership
unchanged.

The Phase 1 implementation slice is limited to:

- `connect_diagnostics_core/connect_diagnostics_stock/doctype/equipment_model/equipment_model.json`
  — mapping-master schema with System Manager-only maintenance permissions.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/equipment_model/equipment_model.py`
  — Item-kind, enabled-capability, same-record, and active-uniqueness validation plus the reusable
  Demo-eligible Stock Item selector.
- `connect_diagnostics_core/connect_diagnostics_stock/doctype/equipment_model/test_equipment_model.py`
  — integration tests for invalid/duplicate mappings, disabled capability behavior, and Demo
  eligibility.
- `connect_diagnostics_core/connect_diagnostics_stock/report/equipment_model_mapping_review/equipment_model_mapping_review.json`
  — System Manager-only admin report metadata.
- `connect_diagnostics_core/connect_diagnostics_stock/report/equipment_model_mapping_review/equipment_model_mapping_review.py`
  — read-only mapped/unmapped Item review rows without name/suffix inference.
- `connect_diagnostics_core/connect_diagnostics_stock/report/equipment_model_mapping_review/test_equipment_model_mapping_review.py`
  — report structure/status tests.
- `connect_diagnostics_core/setup/workspace.py`
  — add the master and review report under existing Stock Setup/Reports navigation; no new
  Workspace or desktop icon.
- `connect_diagnostics_core/setup/tests/test_workspace.py`
  — navigation placement/idempotency regression.
- this task record — plan, review decision, evidence, and restart state.

Phase 1 will not modify Material Request, Item custom fields, Stock Asset Conversion, Asset,
Asset Movement, Dispatch, hooks, fixtures, roles, workflows, patches, desktop icons, or accepted
documentation. No production mapping is inferred from Item names. Any added file or changed
surface requires an updated complete list and independent plan review before editing.

### Phase 1 acceptance criteria

1. Stock Item mappings require `is_stock_item=1`, `is_fixed_asset=0`; fixed-asset mappings require
   `is_stock_item=0`, `is_fixed_asset=1`; the two links cannot be the same record.
2. Demo or conversion capability cannot be enabled while either mapped Item is disabled.
3. At most one non-disabled Equipment Model can own a Stock Item and at most one can own a Fixed
   Asset Item. Conflicting rows are locked during validation.
4. Demo eligibility returns only non-disabled models that allow Demo and whose current Stock Item
   remains enabled and valid; an optional Company filter includes global models.
5. The admin mapping report shows mapped, disabled, invalid, and unmapped Stock/Fixed Asset rows
   without proposing matches from Item codes or names.
6. Only System Manager can maintain or run the mapping review directly. Later requester queries
   consume eligible Item results without exposing mapping configuration.
7. Equipment Model and its review report appear in the existing Stock navigation in the correct
   Setup/Reports sections and converge idempotently.
8. Focused tests and scoped repository gates pass on `tsk512.test`.

No package `__init__.py` files are added: the repository policy reserves module-level generated
artifacts for Frappe, and the migrated DocType/report resolve correctly without them.

## Phase 2 prototype decisions

Until the owner chooses a final workflow and terminology, the isolated prototype will use the
existing `request_usage = Customer Demo` switch instead of changing ERPNext's native
`material_request_type` options. ERPNext uses that native field to map Purchase, Transfer, Issue,
Manufacture, Subcontracting, and Customer Provided requests into downstream documents; extending
it here would create broad native-regression and workflow-baseline risk.

Phase 2 therefore proves only the safe request boundary:

- every Customer Demo row must resolve through an active, Demo-enabled Equipment Model valid for
  the request company; global mappings are allowed;
- the Desk Item picker shows only those Stock Items, and server validation rejects API/import
  bypasses;
- all non-Demo usages retain the installed ERPNext v16 Item query and existing behavior;
- no Workflow fixture, role, approval authority, posting, Fulfillment creation, or downstream
  transaction is added in this phase;
- the existing Material Request workflow may be exercised on `tsk512.test`, but its activation or
  authority model remains an owner/workflow-baseline decision.

### Phase 2 owned files

- `connect_diagnostics_core/api/erpnext/material_request.py` — add one shared Demo-only server
  validation guard called by both the ordinary `validate` hook and
  `validate_submit_for_approval`, plus a permission-checked eligible-Item endpoint that returns
  Item identifiers only; reuse the Phase 1 selector.
- `connect_diagnostics_core/api/erpnext/tests/test_material_request.py` — cover valid/global/company
  mappings, unmapped/disabled/wrong-company bypasses, endpoint permissions/shape, hook integration,
  and non-Demo regression.
- `connect_diagnostics_core/public/js/custom/material_request/doctype.js` — load eligible Item IDs
  for Customer Demo, constrain the row Item query, and reproduce the pinned ERPNext v16 native
  filters unchanged for non-Demo purposes.
- this task record — decisions, review, verification, and restart state.

Phase 2 will not change setup fields, DocType schemas, hooks, fixtures, workflows, roles,
permissions, patches, reports, print formats, Equipment Model, Stock Asset Conversion, Fulfillment,
Asset, Asset Movement, Dispatch, or accepted documentation. Any added file or changed surface
requires an updated complete list and independent plan review before editing.

### Phase 2 acceptance criteria

1. A Customer Demo row is accepted only when its requested Stock Item belongs to an active,
   Demo-enabled Equipment Model whose company is either blank/global or matches the request.
2. Disabled/missing/wrong-kind Items, disabled models, and company-mismatched mappings are rejected
   on the server even when Desk filtering is bypassed.
3. The eligible-Item endpoint requires Material Request `create` or `read` access. For a supplied
   Company it loads the actual Company document, rejects a missing or group Company, and requires
   `read` permission on that Company before querying. It exposes only Item identifiers and follows
   the repository response envelope. Blank Company requests fail closed with no Items.
4. The Desk Item picker fails closed while Demo eligibility is loading and contains only eligible
   Stock Items after loading.
5. The custom script waits until `onload_post_render`, captures the native Item field `get_query`
   function installed by ERPNext, and wraps that exact function. For non-Demo requests it returns
   the native result unchanged. For Customer Demo it preserves the native query/filters and adds
   only `name in <eligible IDs>`. Repeated refreshes keep the originally captured native function,
   and changing usage/company refreshes eligibility without stacking wrappers. Thus Purchase,
   Material Transfer, Material Issue, Manufacture, Subcontracting, Customer Provided, and
   non-Demo app usages preserve installed ERPNext behavior rather than duplicating its filter code.
6. Both normal document validation and `validate_submit_for_approval` call the same Demo helper;
   focused tests call each lifecycle path and verify stale mappings fail approval. Approval creates
   no Fulfillment, Stock, GL, Asset, Movement, or Dispatch record.
7. Focused automated tests cover the server paths and assert that the client wrapper retains and
   invokes the captured native query for representative native-purpose results while adding only
   the Demo Item constraint. The final role-based Computer Use phase remains the acceptance source
   for the actual Desk picker lifecycle.

## Phase 3A prototype decision and owned files

Phase 3 is split because durable planning and Asset reservation have different failure modes.
Phase 3A first establishes the idempotent, non-posting planning boundary. When a Customer Demo
Material Request reaches submitted state, its `on_submit` hook creates or returns one initial
`Material Request Fulfillment` for the immutable submitted demand. The initial allocations copy
each request row and its Equipment Model mapping with `source_type = Unplanned`; they do not select,
reserve, move, convert, dispatch, or post anything.

The prototype uses a unique operation identity `material-request:<MR>:submitted` and locks the
Material Request before checking/creating the plan. A repeat invocation returns the existing plan.
The parent stores a source digest and version `1`; later Phase 3B replans create later versions and
preserve earlier plans rather than overwriting them. Workflow fixtures and approval authority remain
unchanged: any native/workflow path that validly submits the MR reaches the same hook.

Phase 3A is limited to:

- new `connect_diagnostics_core/connect_diagnostics_stock/doctype/material_request_fulfillment/`
  JSON, typed controller, minimal Desk script, and integration tests;
- new `connect_diagnostics_core/connect_diagnostics_stock/doctype/material_request_fulfillment_allocation/`
  child JSON and typed controller;
- new `connect_diagnostics_core/api/erpnext/material_request_fulfillment.py` and focused tests for
  idempotent handoff, immutable source snapshot, mapping validation, permissions, and no posting;
- `connect_diagnostics_core/hooks.py` — add the Material Request `on_submit` handler and narrowly
  scoped Fulfillment permission-query/document-permission callbacks;
- `connect_diagnostics_core/setup/document_naming.py` and its existing tests — add prefix `MRF`;
- `connect_diagnostics_core/setup/workspace.py` and its existing tests — add the planner under the
  existing Stock primary navigation without a new Workspace or desktop icon;
- this task record.

No `__init__.py`, Company/Item/Asset custom field, workflow/role/fixture, patch, Dispatch, Asset
Movement, Stock Asset Conversion, print format, accepted documentation, or dependency changes are
authorized in Phase 3A.

### Phase 3A acceptance criteria

1. Submitting an eligible Customer Demo MR creates exactly one initial Fulfillment with one copied
   allocation per MR row, the correct Equipment Model/fixed-asset mapping, quantity/UOM, source
   version/digest, and no selected source or downstream reference.
2. Repeating the same handoff, including from two connections, returns the same operation/plan and
   never creates a duplicate.
3. Non-Demo submission creates no Fulfillment. Draft, cancelled, wrong-company, stale, unmapped, or
   no-longer-eligible input is rejected or ignored at the correct lifecycle boundary.
4. The hook changes no Asset status/location/custodian and creates no SLE, GL Entry, Stock Entry,
   Asset Movement, Stock Asset Conversion, or Dispatch.
5. Phase 3A grants parent read-only role permission to Purchase User, Purchase Manager, Stock User,
   Stock Manager, Accounts User, Accounts Manager, and System Manager; it grants no role create,
   write, delete, or submit permission. Purchase roles are additionally restricted by permission
   query and document permission to rows whose linked Material Request `owner` is the current user;
   Stock, Accounts, and System Manager roles may read all otherwise-permitted company rows. Child
   rows have no independent permissions and inherit the parent. Later Phase 3B must explicitly add
   planner mutation permissions/API.
6. The `on_submit` function is the only Phase 3A creation path. It locks and revalidates the
   submitted MR, sets a request-local internal handoff flag, inserts with `ignore_permissions=True`,
   and always clears the flag. The controller rejects every `before_insert` without that flag, so
   direct Desk/API creation—including Administrator—cannot reuse the permission bypass. Tests cover
   direct insertion denial, flag cleanup after failure, and the role/row read matrix.
7. The DocType is visible in existing Stock navigation, naming follows
   `MRF[YYYY-BE][MM-DATE][####]`, migration is idempotent, and focused tests/scoped gates pass only
   on `tsk512.test`.
8. Phase 3B reservation/replanning must independently define stable Asset locks, active-hold
   uniqueness, returning-Asset policy, release/consume transitions, and Dispatch final revalidation
   before it changes any `Unplanned` allocation.

## Phase 3B plan and owned files

Phase 3B adds planning and reservation only; it does not move an Asset, post stock/GL, create a
conversion, or alter the TSK-523 Asset Movement workflow. Native Asset `status`, `location`, and
`custodian` remain authoritative and are not reused as reservation fields.

The active plan exposes three Stock-role actions. **Use Available Assets** reserves eligible Assets
already at the configured Company Demo pool. **Wait for Returning Assets** reserves eligible Assets
on an open Customer Demo whose expected return is inside the configured reuse window and whose
original outbound source is the Demo pool. **Use Stock Now** marks the remaining units as Stock
Conversion candidates without creating a conversion. Each action appends an immutable plan
revision; prior plans and allocations are retained and the former active plan is marked
`Superseded` only after the new plan and holds succeed.

Active holds use a separate server-owned `Demo Asset Reservation` record. Its nullable unique
`active_asset_key` equals the Asset name only while state is `Active`, providing a database-backed
one-active-hold invariant in addition to deterministic `for_update` locks. Release clears that key
but retains history. Reservation types distinguish `Existing Asset` and `Returning Asset`; future
availability is never presented as current availability. Dispatch consumption/final revalidation
belongs to Phase 6, so Phase 3B holds cannot yet make a Fulfillment `Ready`.

The existing P3A schema already permits multiple Fulfillments for one `material_request`; only
`operation_id` is unique. Phase 3B adds required `plan_revision` with default `1` and backfills the
existing P3A rows to revision 1 during normal DocType synchronization. Replan operation identities
are `material-request:<MR>:plan:<revision>`. The server locks the Material Request first, then
re-reads all plans and requires exactly one latest `Planned` revision before calculating `n+1`.
Because every creation path remains server-flag guarded, that lock plus unique operation identity
is the one-latest-plan invariant; concurrent replans serialize and the loser returns the winner or
re-evaluates the now-current plan. The new plan is inserted and its holds are secured before the
old plan is changed to `Superseded`, all in one transaction.

Phase 3B is limited to:

- `connect_diagnostics_core/connect_diagnostics_stock/doctype/demo_asset_reservation/` — new
  server-owned hold schema, typed controller, and focused integration tests;
- existing Material Request Fulfillment parent/allocation JSON, controllers, and Desk script — add
  revision/status/configuration and read-only reservation/source fields plus the three planner
  actions;
- `connect_diagnostics_core/api/erpnext/material_request_fulfillment.py` and its tests — candidate
  discovery, append-only replanning, deterministic locks, active-hold uniqueness, release on
  superseding choices, and Stock-role APIs;
- `connect_diagnostics_core/hooks.py` — read-only reservation permission callbacks if needed;
- `connect_diagnostics_core/setup/procure_to_pay.py` and its existing tests — add only the missing
  Company `demo_asset_pool_location` and `demo_return_reuse_window_days` settings;
- `connect_diagnostics_core/setup/workspace.py` and its existing tests only if the reservation
  audit list needs an explicit existing-Stock navigation link;
- this task record.

Phase 3B will not change Dispatch, Asset Movement, Stock Asset Conversion, Asset, Item, Material
Request schema, workflows, fixtures, patches, print formats, accepted documentation, or external
dependencies. Any such change requires a new scope review.

### Phase 3B acceptance criteria

1. Immediate candidates are submitted, same-company fixed-asset Items at the configured leaf Demo
   pool Location, usable under native Asset status, not outstanding on Dispatch, and not actively
   held. Returning candidates additionally come from a submitted delivered Customer Demo outbound,
   have an expected return inside the Company window, originate at the pool, remain outstanding,
   and have no successor hold.
2. Planner actions require Stock User/Stock Manager, read access to the Fulfillment, a currently
   active latest plan, and complete Company settings. Every input is revalidated server-side.
3. Replanning preserves prior parent/allocation rows, creates revision `n+1`, preserves already
   chosen units, splits Asset-backed units to quantity 1, and keeps the active allocation sum equal
   to every submitted Material Request row quantity.
4. Deterministic Asset locks plus the unique active key prevent two Fulfillments from reserving the
   same Asset. A two-connection integration test proves exactly one winner without duplicate holds.
5. Existing and returning holds are visibly distinct. Returning holds store expected availability;
   late/sold/scrapped/repair-blocked/no-longer-outstanding candidates fail revalidation and require
   a new plan rather than silently changing source.
6. Superseding an Asset choice releases its old active hold only after the replacement plan is
   valid. Release clears the active key and retains audit history; repeated actions are idempotent.
7. No planner action creates or mutates SLE, GL Entry, Stock Entry, Asset Movement, Stock Asset
   Conversion, Dispatch, Asset status/location/custodian, or Material Request demand.
8. Migration is idempotent and focused tests, relevant regressions, repository gates, independent
   code review, and available browser acceptance pass only on `tsk512.test`.

Schema verification must begin from the accepted Phase 3A database checkpoint. It must prove the
existing version-1 row remains readable as revision 1, can append revision 2, and is not overwritten.
Rollback before owner acceptance is restoration of
`sites/tsk512.test/private/backups/20260927_171306-tsk512_test-database.sql.gz` (plus its matching
site-config/public/private archives) and removal of this isolated branch/worktree; no reverse patch
or destructive row deletion is authorized.

## Phase 4 plan and owned files

Phase 4 connects one unit-sized active `Stock Conversion` allocation to the already proven native
posting voucher. The Warehouse action creates or returns one **Draft** Stock Asset Conversion;
posting remains an explicit submit action for the existing Stock Manager/Accounts Manager roles.
The controller re-locks and revalidates the active Material Request, Fulfillment, allocation, source
Warehouse, and native Serial and Batch Bundle immediately before submit. ERPNext `StockController`
remains the sole stock-ledger path, and Stock Asset Conversion remains the sole owner of the
`Dr Fixed Asset / Cr Inventory` reclassification and Asset creation.

Every linked voucher stores immutable `material_request_fulfillment`, `fulfillment_allocation`, and
unique operation identity `fulfillment-allocation:<allocation>:stock-asset-conversion`. Repeated
create calls return the same voucher. Stock Conversion replanning produces one quantity-1
allocation per physical unit. The source Warehouse and optional native Serial and Batch Bundle are
confirmed on the voucher row, not overloaded into the Asset `selected_source` field. A linked
conversion can only be inserted by the server handoff flag; standalone Phase-0 mechanics remain
available for their existing non-Demo proof/tests.

All linked identity fields are read-only in Desk. For a linked Draft, the controller compares every
save with the persisted document and rejects changes to Company, Fulfillment/allocation/operation
identity, source Item, source Warehouse, quantity/UOM, bundle/serial/batch identity, target Item,
Asset Category, or target Location. It also re-resolves the allocation and Equipment Model on every
validate/submit rather than trusting saved client values. Only depreciation inputs intentionally
owned by the later Accounts review remain editable; Phase 5 will add their preview/freshness gate.
The same controller rules apply to direct API saves. Standalone Phase-0 vouchers have no linked
identity and retain their current edit/validation behavior.

On successful submit, the server writes only lifecycle fields on the immutable allocation:
conversion state `Ready`, downstream DocType/reference, and source confirmation. On cancellation it
retains the cancelled reference for audit and changes the lifecycle state to `Cancelled`; it never
deletes SLE/GL rows or silently creates a second conversion. Phase 5 owns previews/freshness and
Phase 6 owns Asset Movement/Dispatch consumption, so this phase does not mark the Fulfillment ready
for outbound use.

Phase 4 is limited to:

- existing Stock Asset Conversion parent/item JSON, controllers, Desk script, and tests — add
  immutable Fulfillment traceability, server-only linked creation, submit/cancel revalidation, and
  lifecycle callbacks while retaining the proven native ledger builders;
- Material Request Fulfillment allocation JSON/controller and planner API/tests — unit-sized Stock
  Conversion rows, source confirmation/lifecycle fields, and the permission-checked idempotent
  Draft creation endpoint;
- Material Request Fulfillment Desk script — add the Warehouse Draft-conversion action;
- Stock workspace/navigation and existing tests — expose Stock Asset Conversion in the existing
  Stock area without a new Workspace or icon;
- this task record.

Phase 4 will not add Workflow/fixtures, preview formulas, depreciation posting actions, Company
accounting fields, Asset Movement, Dispatch, Sales Invoice integration, patches, print formats,
accepted documentation, or dependencies.

### Phase 4 acceptance criteria

1. Only an active latest Stock Conversion allocation with quantity 1 and no active conversion can
   create a Draft voucher; Stock User/Manager permission, Company, mapping, pool Location, source
   Warehouse, and native bundle identity are checked server-side.
2. Repeated and concurrent create requests for one allocation return exactly one operation/voucher.
   Different allocations cannot consume the same serialized physical unit; deterministic locks and
   ERPNext bundle/stock validation run again at submit.
3. Submit atomically produces one outward SLE, one balanced conversion GL pair from actual removed
   stock value, and one submitted normal Asset with no Asset-owned duplicate acquisition GL.
4. Successful submit marks the allocation `Ready` with exact voucher/source traceability only after
   posting succeeds. Any failure leaves no partial ledger, Asset, or Ready allocation.
5. Cancellation uses native Asset/SLE/GL reversal, retains the cancelled voucher reference, and
   marks the allocation `Cancelled`; it does not delete submitted ledgers.
6. Serialized/batched and ordinary stock use the pinned ERPNext v16 Serial and Batch Bundle path;
   wrong item/company/Warehouse/bundle, insufficient stock, stale/latest-plan, and duplicate source
   cases fail closed.
7. Existing Phase-0 standalone mechanics and all earlier Demo paths remain backward compatible.
   Tests attempt linked Draft tampering through normal save and direct document/API mutation while
   proving an unlinked standalone Draft still follows the Phase-0 contract.
8. Migration, focused integration/concurrency tests, regressions, repository gates, independent
   review, and available browser acceptance pass only on `tsk512.test`.

Rollback before owner acceptance is restoration of the accepted Phase 3B backup
`sites/tsk512.test/private/backups/20260927_173837-tsk512_test-database.sql.gz` with its matching
archives and removal of the isolated branch/worktree; no reverse patch or manual ledger deletion is
authorized.

## Phase 5 plan and owned files

Phase 5 adds an Accounts-owned, non-posting preview/freshness gate only for linked Demo conversions.
It deliberately keeps Phase-0 standalone vouchers backward compatible. The preview resolves the
outgoing value through ERPNext's pinned `get_incoming_rate` path using the exact Item, Warehouse,
posting date/time, Company, quantity, Serial/Batch fields, and native bundle. It then passes that
value into the same conversion-GL builder used after the real SLE is posted. Preview must never
insert SLE, GL Entry, Asset, Asset Depreciation Schedule, or Journal Entry rows.

The Company owns a configurable `demo_low_value_asset_threshold`; no runtime amount is hard-coded.
The preview recommends `Full Depreciation — Single Entry` when the native stock value is at or below
the configured threshold and `Normal Depreciation` above it. The recommendation never silently
changes the selected treatment. If Accounts chooses the other treatment, a reason is required.
Only Accounts Manager or System Manager may confirm and persist a preview; other existing read and
submit permissions are not expanded.

The linked Draft stores the approved native value/rate, recommendation, deterministic hash,
reviewer, and review time. The hash covers the immutable source/allocation/model identity, current
pool and account resolution, posting context, native value, threshold, selected treatment, and all
depreciation inputs. Changing an Accounts-owned input clears the approval. Submit first posts the
native outward SLE inside the same transaction, rebuilds the approval facts from its actual stock
value difference, and blocks/rolls back if the value or hash differs. Only a fresh approval reaches
the existing shared GL builder and Asset submit. This proves preview equals actual posting without
creating a second valuation engine or leaving partial ledgers.

The depreciation preview is intentionally a native **configuration preview**: treatment, schedule
start, frequency, count, residual value, Finance Book, and the expected one-entry amount/NBV for the
already-proven full-depreciation case. It does not synthesize a Normal Depreciation schedule because
ERPNext v16 creates that schedule only for a persisted Asset. Phase 5 does not create a provisional
Draft Asset; the accepted P0/P4 atomic submit remains the sole Asset creation boundary, avoiding
orphan cleanup and acquisition-GL risk. The owner may later choose a separately reviewed Draft-Asset
subphase after seeing the runtime evidence.

Phase 5 is limited to:

- `connect_diagnostics_core/setup/procure_to_pay.py` and
  `connect_diagnostics_core/setup/tests/test_procure_to_pay.py` — add the idempotent Company Demo
  low-value threshold field and its setup regression;
- Stock Asset Conversion JSON/controller/tests — add read-only approval fields, override reason,
  shared preview/actual builders, approval invalidation, and submit freshness rollback;
- new `connect_diagnostics_core/api/erpnext/stock_asset_conversion.py` and focused tests —
  permission-checked POST preview confirmation with the standard response envelope;
- new Stock Asset Conversion Desk script — Accounts preview action and structured stock/GL/
  depreciation configuration display;
- this task record.

Phase 5 will not create a Draft Asset, post depreciation, alter Workflow/fixtures/roles, change
Asset Movement or Dispatch, patch ERPNext, add dependencies, or change accepted documentation.

### Phase 5 acceptance criteria

1. Preview uses ERPNext native outgoing valuation and the exact GL builder later used by submit;
   it persists no SLE, GL Entry, Asset, depreciation schedule, or Journal Entry.
2. Missing/zero stock, stale bundle/mapping/pool, unresolved accounts, missing threshold, and users
   outside Accounts Manager/System Manager fail closed server-side.
3. Below/equal/above-threshold values give deterministic recommendations; treatment is never
   auto-changed, and contrary selection requires a nonblank override reason.
4. The approval hash changes for source, value, account, threshold, target, posting, treatment, or
   depreciation-input changes. Saving an Accounts-owned input clears approval fields.
5. Linked submit requires an approved preview. It compares the actual native SLE value and complete
   hash before GL/Asset posting; mismatch rolls back all SLE/GL/Asset effects and requires re-review.
6. A fresh preview submits through the existing native P4 transaction and its preview GL equals the
   actual balanced pair. Full and Normal treatments retain native Asset schedule behavior.
7. Standalone Phase-0 conversion, linked cancellation, P0-P4 tests, migration, scoped gates,
   independent review, and available browser acceptance pass only on `tsk512.test`.

Rollback before owner acceptance is restoration of the accepted Phase 4 backup
`sites/tsk512.test/private/backups/20260927_180041-tsk512_test-database.sql.gz` with matching
archives; no manual ledger deletion or writes to another site are authorized.

## Phase 6 plan and owned files

Phase 6 makes the accepted allocation/Asset result usable through native Asset Movement and the
existing Dispatch lifecycle. `request_usage = Customer Demo` remains the authoritative P2
compatibility boundary; the prototype does not rename ERPNext's native Material Request Type or
reactivate the older single-Asset `fulfillment_route/allocated_asset` model. Existing non-TSK-512
Dispatch routes keep their installed behavior unchanged.

Each Demo Dispatch Transfer stores its exact Fulfillment allocation. This is required because one
Material Request row may now produce multiple quantity-1 allocations and Assets, while the legacy
row has only one `allocated_asset` field. A shared server resolver maps `Existing Asset` and
`Returning Asset` allocations to their selected Asset and maps a `Stock Conversion` allocation only
to the submitted conversion's Asset in `Ready` state. Every action locks the submitted Demo request,
latest active Fulfillment, allocations in deterministic order, Asset rows, and active reservations,
then revalidates Company, quantity, current location/status, outstanding Dispatches, and exact
downstream references.

The Warehouse action first creates or returns one **Draft** native Asset Movement for all resolved
allocations. It uses `purpose = Issue`, the request's responsible Employee, the current Asset source
Location, `material_request`, and the native dynamic reference to the Fulfillment. It never submits
the movement or bypasses the TSK-523 workflow; authorized users must complete the existing Asset
Movement approval/post route. After that movement is submitted, a second idempotent action creates
one Draft Outbound Dispatch with one quantity-1 transfer per allocation, the exact submitted
movement, original source Location, Material Request row, and delivery address. Users submit and
confirm it through the existing Dispatch controls.

Dispatch validation recognizes the new allocation link only for a submitted Customer Demo request.
It proves the allocation belongs to the latest Fulfillment, resolves the exact Asset, and requires
one complete transfer per resolved allocation. Rows without the link continue through the legacy
Stock Entry/Existing Asset/Stock Capitalization validators unchanged. Submit records audit links and
`Dispatched` state; delivery confirmation atomically marks the linked allocations `Delivered` and
consumes their active Demo reservations only after the existing POD/movement checks succeed.

For return, an idempotent action on a delivered Demo Outbound Dispatch creates or returns a Draft
native `Receipt` Asset Movement into the Company's existing Return QA Hold Location, referenced to
the outbound Dispatch. It is again approved/submitted through the existing Asset Movement route.
Only after it is submitted may a second action create the Draft Return Dispatch, copying exact
allocation/Asset/original-transfer links. Existing Dispatch return, POD, inspection, repair/release,
failure, retry, and return-to-origin controls remain authoritative. Successful Return delivery marks
the allocation `Returned`; it does not silently move the Asset from QA Hold back to the Demo pool.

Phase 6 is limited to:

- Material Request Fulfillment allocation JSON/controller plus planner API/tests/Desk script — add
  resolved Asset and outbound movement/Dispatch lifecycle links and the two outbound preparation
  actions;
- existing Material Request Asset Movement validator/tests — recognize the exact latest Demo
  Fulfillment allocation set because the legacy one-Asset-per-request-row fields cannot represent
  quantity-split Demo allocations; non-Demo movement validation remains unchanged;
- Stock Asset Conversion controller/tests — publish the successfully created Asset onto its exact
  allocation only after submit;
- Dispatch Transfer JSON/controller — add the immutable Fulfillment allocation reference;
- existing Dispatch JSON/controller/Desk script/tests — allocation-aware validation, completeness,
  submit audit transitions, and return preparation buttons without changing legacy rows;
- existing Dispatch API/tests — idempotent Demo return movement/Dispatch actions and post-POD
  allocation/reservation transitions;
- this task record.

Phase 6 will not alter Asset Movement Workflow fixtures/states/actions/permissions, patch ERPNext,
change stock/GL/depreciation posting, sell Assets, auto-release QA, add dependencies, or change
accepted documentation.

### Phase 6 acceptance criteria

1. Only the latest submitted Customer Demo plan whose every allocation resolves to one unique,
   eligible Asset can create one Draft outbound Asset Movement; Unplanned, unsubmitted conversion,
   stale reservation, duplicate Asset, wrong Company, forbidden status, or outstanding Dispatch
   fails closed.
2. Repeated/concurrent outbound actions return one movement. No action submits or bypasses the
   existing Asset Movement workflow. A submitted Issue to the responsible Employee is required
   before one Draft Outbound Dispatch can be created.
3. The Demo Outbound Dispatch contains every resolved allocation exactly once, supports multiple
   allocations from one Material Request row, and preserves exact allocation, movement, Asset,
   source Location, quantity, and request-row traceability.
4. Legacy Dispatch rows without a Fulfillment allocation retain their existing validators and
   API behavior. TSK-523 Workflow artifacts are byte-for-byte unchanged.
5. Outbound submit/delivery still uses the existing native movement/POD checks. Allocation state
   and reservation consumption occur only after the corresponding transition succeeds and roll
   back atomically on failure.
6. A delivered Demo outbound can create one Draft Receipt movement into Return QA Hold; only its
   submitted movement can create one Draft Return Dispatch. The exact outbound transfer/allocation
   cannot be returned twice.
7. Return delivery marks the allocation Returned while keeping existing inspection, repair,
   release, failed-delivery, retry, and recovery behavior intact. Dispatch never posts SLE/GL for
   Asset rows.
8. Focused lifecycle/concurrency tests, legacy Dispatch regressions, P0-P5 regressions, migration,
   scoped gates, independent review, and available role-based browser acceptance pass only on
   `tsk512.test`.

Rollback before owner acceptance is restoration of the accepted Phase 5 checkpoint (to be recorded
after Phase 5 passes) and removal of only the isolated branch/worktree; no reverse SQL, Workflow
mutation, or write to another site is authorized.

## Phase 7 plan and owned files

Phase 7 keeps ERPNext's native fixed-asset Sales Invoice as the only sale/disposal owner. An
Accounts action on one delivered Demo allocation creates or returns one persisted Draft Sales
Invoice by calling ERPNext's installed `make_sales_invoice` helper for the resolved Asset and fixed
Asset Item, full quantity one. It then sets the selected Customer, `update_stock = 0`, exact Demo
allocation and delivered Outbound Dispatch provenance, and a unique server-owned operation ID.
Selling price, taxes, payment terms, approval, submission, depreciation-on-sale, Asset Sold status,
and gain/loss GL remain native editable/submit behavior; the original Stock Item is never added.

The action and submit hook lock the allocation, its Asset, the current delivered Dispatch transfer,
and Asset reservations in deterministic order. The selling allocation's own reservation must
already be Consumed by P6 delivery. Any active reservation for the same Asset owned by another
allocation is a successor reservation and blocks Draft creation and submit. A started Return
movement or Return Dispatch also blocks sale. The Asset must remain submitted, quantity one, and
not Sold/Scrapped. Only Accounts User, Accounts Manager, or System Manager with Sales Invoice create
permission and Customer read access may create the Draft; normal Sales Invoice permissions and any
installed approval route remain authoritative afterward.

Sale identity is revisioned under the locked allocation. If a Draft or submitted attempt exists,
repeat calls return it. If the latest attempt is cancelled, the next action assigns
`attempt = previous attempt + 1` and operation ID
`demo-sale:<allocation>:<attempt>`. Both attempt and operation ID are immutable and unique, so
cancelled provenance remains auditable while a later owner-authorized retry can create one new
Draft without collision. Submit/cancel hooks act only when the Invoice is the allocation's recorded
current attempt; stale attempts fail closed.

After native Sales Invoice submission succeeds, an `on_submit` hook atomically records the Invoice
on the exact allocation and changes its lifecycle to `Sold`, closing that allocation's return
obligation. On native cancellation, `on_cancel` clears the current sale link and returns the
allocation to `Delivered`; it never recreates the consumed reservation. Hooks return immediately
for invoices without exact Demo provenance, preserving every ordinary fixed-asset and non-Asset
Sales Invoice. For a mixed Demo delivery, P6 return preparation is narrowed to the remaining
Delivered allocations so Sold allocations are neither returned nor reopened.

Phase 7 is limited to:

- existing Sales Invoice setup module/tests — additive read-only/no-copy allocation, Dispatch,
  sale-attempt and unique operation provenance fields on Sales Invoice;
- existing Sales Invoice API/tests — native Draft builder plus submit/cancel lifecycle hooks and
  sale eligibility/permission/concurrency checks;
- `hooks.py` — register only the narrow Sales Invoice `on_submit` and `on_cancel` handlers and the
  submit revalidation hook without changing existing handler order or behavior;
- Material Request Fulfillment allocation JSON/controller plus planner API/tests/Desk script — add
  current Sales Invoice link, `Sold` lifecycle, Accounts action, successor-reservation blocker, and
  remaining-unsold return selection;
- existing Dispatch controller/API/tests only where needed to accept the exact remaining Delivered
  allocation set after another allocation is Sold;
- existing Material Request Asset Movement validator/tests only where needed for a Receipt movement
  to contain the exact remaining Delivered allocation set after another allocation is Sold; Issue
  movement validation remains the complete active allocation set;
- this task record.

Phase 7 will not alter ERPNext Asset or Sales Invoice controllers, manually post GL/depreciation,
sell stock, submit the Draft, add a Sales workflow/role/fixture, reopen reservations, change tax or
credit controls, or affect invoices without Demo provenance.

### Phase 7 acceptance criteria

1. One delivered, full-unit Demo allocation with no successor reservation or started return creates
   one idempotent Draft native fixed-asset Sales Invoice for its resolved Asset/Item and Customer;
   `update_stock` remains off and no Asset/GL/lifecycle posting occurs in Draft.
2. Missing/wrong provenance, non-Demo/stale allocation, wrong Company/Customer permission, Asset
   mismatch/status/quantity, non-Delivered state, active successor reservation, or started return
   fails closed before Invoice creation.
3. Repeated/concurrent actions return one Draft through allocation locking plus a unique operation
   ID. Submit revalidates all facts under lock so a successor reservation race rolls back native
   sale, Asset and GL effects. After cancellation, one incremented attempt may be created; stale
   attempts cannot mutate the allocation.
4. Native submit owns depreciation-on-sale, Asset Sold status and disposal gain/loss accounting;
   the app only changes the exact allocation to `Sold` after native success and records the Invoice.
5. Native cancellation restores the Asset/accounting and atomically returns only that allocation
   to `Delivered`, without recreating its consumed reservation. A cancelled Invoice retains its own
   immutable attempt provenance for audit while the allocation's current sale link is cleared;
   cancel-and-recreate increments the attempt and remains idempotent.
6. A mixed delivered Demo set can sell one allocation and return the remaining Delivered
   allocations; return movement/Dispatch excludes Sold allocations and cannot reopen them.
7. Sales Invoices without Demo provenance, including ordinary fixed-asset sales, preserve installed
   ERPNext behavior and all existing tax/regulatory/freeze hooks.
8. Focused native sale/cancel, blocker, rollback, concurrency, mixed-sale/return and non-Demo
   regressions, migration, scoped gates, independent review, and available role-based browser
   acceptance pass only on `tsk512.test`.

Rollback before owner acceptance is restoration of the accepted Phase 6 checkpoint and removal of
only the isolated branch/worktree. No reverse SQL, production data mutation, or native controller
patch is authorized.

## Risks and rollback

- A custom `StockController` voucher can participate in reposting and cancellation only if its
  SLE construction matches the pinned ERPNext contract. Tests must cover both directions.
- Asset submission may post acquisition GL for certain purchase/composite configurations. The
  prototype must assert exact GL ownership, not rely on an undocumented flag.
- Preview cannot be a separate valuation formula. Later preview work must reuse the posting
  builders and must never persist ledgers.
- Rollback is branch/worktree removal before merge. Runtime proof records are confined to the
  dedicated `tsk512.test` database and use a unique `_Test TSK512` prefix. Frappe's integration
  runner retains submitted ledger evidence between cases; the site is disposable and can be
  restored from the recorded pre-prototype backup instead of deleting submitted ledgers.

## Test-site metadata isolation

- The first proof runs used `local.test`, but another isolated branch migrated the same shared test
  site and removed the prototype DocType metadata as an orphan. No product code caused that
  failure.
- To remove cross-branch interference, Phase 0 now uses the dedicated MariaDB-backed site
  `tsk512.test`. It was created with the same five installed apps and restored from the recorded
  pre-prototype `local.test` database backup before migrating this worktree.
- Commands must fail closed unless the active site is exactly `tsk512.test`.
- Do not migrate `local`, shared DEV, UAT, or production.
- If Phase 0 stops, keep the isolated worktree for owner inspection. The prototype tables and
  test records may remain only on `tsk512.test`; recovery is to restore that dedicated test site
  from the pre-prototype backup or rebuild it, never to issue broad manual SQL deletion.

## Computer Use acceptance matrix

Computer Use runs only after deterministic gates pass.

| Actor | Route | Required evidence |
| --- | --- | --- |
| Requester | Demo Material Request | Eligible stock item only; no warehouse/Asset/accounting controls |
| Approver | Demo approval | Separate user; approval creates one Fulfillment idempotently |
| Warehouse | Fulfillment/conversion | Existing Asset first; exact stock unit confirmation; no Accounts action |
| Accounts | Conversion review | Stock, GL, depreciation previews; treatment confirmation; stale preview blocked |
| Warehouse | Asset Movement/Dispatch | Physical outbound and return require valid Dispatch and POD state |
| Sales | Demo sale | Native fixed-asset Sales Invoice; successor reservation blocks sale |

## Verification evidence

- Isolation:
  - branch `feat/tsk-512-borrow-prototype` remains unmerged in its managed worktree;
  - no migration or write was made to `local`, shared DEV, UAT, or production;
  - pre-prototype database backup:
    `sites/local.test/private/backups/20260927_151738-local_test-database.sql.gz`;
- dedicated proof site: `tsk512.test` (`allow_tests=true`).
  - accepted Phase 1 checkpoint database backup:
    `sites/tsk512.test/private/backups/20260927_164235-tsk512_test-database.sql.gz`, with matching
    site-config, public-file, and private-file archives.
- Migration: `PYTHONPATH=<isolated-worktree> bench --site tsk512.test migrate` passed.
- Voucher mechanics: 4 unit and 7 integration tests passed on `tsk512.test`, covering exact
  quantity, SLE-valued balanced GL, normal Asset creation with no acquisition GL, rejected
  composite/purchase acquisition contexts, transaction rollback, native cancellation, serial
  bundle handling, one-entry depreciation to zero plus sale, and native multi-entry normal
  depreciation.
- Naming regression: 22 unit tests passed on `tsk512.test`.
- Scoped repository gate passed with the Bench interpreter: whitespace/EOF/conflict/AST/debug,
  JSON, Ruff check/format, Prettier JSON, `ty-check`, Semgrep Frappe rules, and `pip-audit`.
- The depreciation/sale integration cases temporarily deactivate only active Journal Entry and
  Sales Invoice workflows, run serially on `tsk512.test`, and restore every changed workflow in a
  `finally` block. This isolates native ERPNext mechanics from the separate workflow-baseline
  feature; it is not production behavior.
- Independent final review accepted Phase 0 with no P0/P1 findings. Two P2 follow-ups remain for
  production phases: add API/UI bypass coverage for acquisition-context rejection and keep native
  depreciation tests serialized on the disposable site.
- The full-repository pre-commit run passed every hook except `prettier-eslint`, whose `npx`
  invocation could not determine an executable for existing JavaScript files. The Phase 0 owned
  files contain no JavaScript; the exact scoped gate passed all hooks. This baseline tool failure
  is recorded and is not being fixed outside TSK-512 scope.
- Phase 1 migration and focused verification passed on `tsk512.test`: Equipment Model 7 integration
  tests (including a real two-connection concurrent-create race), mapping review 3 unit tests,
  Stock navigation 30 unit tests, Phase 0 conversion regression 4 unit + 7 integration tests, and
  naming regression 22 unit tests.
- The Phase 1 scoped pre-commit gate passed whitespace/EOF/conflict/AST/debug, JSON, Ruff,
  Prettier JSON, `ty-check`, Semgrep Frappe rules, and `pip-audit` with the Bench interpreter.
- Independent Phase 1 review found and then accepted the concurrency fix: mapped Item rows are
  locked in deterministic order before locking/rechecking conflicting mappings; three consecutive
  two-connection runs retained exactly one active owner. No P0/P1 findings remain.
- Phase 2 focused verification passed on `tsk512.test`: 28 Material Request unit tests, including
  server/API/approval bypass guards and Node VM execution of the real client query wrapper; 4
  procure-to-pay setup regressions; and 4 outstanding-borrowed-report regressions.
- Phase 2 Python, type, security, audit, and formatting gates passed. The JavaScript file was
  formatted successfully with the repository's installed `prettier-eslint` binary from the main
  checkout; the isolated worktree's `npx` hook retains the previously recorded executable-resolution
  limitation.
- Independent Phase 2 code review found no remaining P0/P1 findings and accepted the server guard,
  Company authorization, native-query composition, async stale-response protection, and non-Demo
  isolation. Actual Desk picker behavior remains in the final Computer Use acceptance matrix.
- Phase 3A migration and focused verification passed on `tsk512.test`: 5 unit and 2 integration
  tests cover server-only creation, immutable source snapshot, no-posting effects, permission-query
  boundaries, and a real two-connection handoff. The complete Phase 3A suite passed three
  consecutive concurrency runs, with both callers returning the same plan and exactly one row.
- Phase 3A regressions passed: Phase 2 Material Request 28, Equipment Model 7, Stock Asset
  Conversion 4 unit + 7 integration, Equipment Model Mapping Review 3, Outstanding Borrowed Items
  4, procure-to-pay setup 4, naming 22, and workspace navigation 30 tests.
- The full repository pre-commit gate passed with the Bench interpreter when the isolated
  worktree's known `prettier-eslint` executable-resolution hook was skipped. Both changed
  JavaScript files were separately run through the repository-installed `prettier-eslint` binary;
  the Phase 3A file was unchanged.
- Independent Phase 3A code review accepted the lifecycle, permission, schema, concurrency,
  deadlock-recovery, naming, navigation, and no-posting evidence with no P0/P1 findings.
- Phase 3A Computer Use acceptance is blocked because this Codex host exposes no browser-control,
  screenshot, or recording capability. The tester stopped before opening or mutating any site; no
  UI pass is claimed. The full Desk scenario remains required at the final UAT gate on a capable
  desktop host.
- Phase 3B migration passed on `tsk512.test`. Focused verification now has 6 unit and 4 integration
  tests covering real available-Asset reservation, append-only revisions, remaining-unit Stock
  Conversion planning, reservation release history, returning-Dispatch query boundaries, no
  posting side effects, and a real two-connection/two-Fulfillment race for one Asset. The complete
  module passed three consecutive race runs before the release action was added and passed again
  with the release action.
- Phase 3B regressions passed: Material Request 28, procure-to-pay setup 4, Equipment Model 7,
  Stock Asset Conversion 4 unit + 7 integration, naming 22, and workspace 30 tests. The full
  repository Python/JSON/type/security/audit gate passed; both JavaScript files were separately
  formatted with the repository-installed formatter because the isolated hook retains its recorded
  executable-resolution limitation.
- Independent Phase 3B code review found no P0/P1 issues in revision immutability, quantity
  invariants, parameterized candidate queries, permissions, lock order, unique active holds,
  release behavior, no-posting boundaries, or the race evidence. Computer Use remains deferred for
  the already-recorded host capability blocker.
- Phase 4 migration passed idempotently on `tsk512.test`. The Stock Asset Conversion regression
  remains 4 unit + 7 integration tests, and the Fulfillment module now passes 6 unit + 6
  integration tests covering unit-split allocations, stock availability, idempotent Draft handoff,
  linked-field tampering, stale mapping/pool rejection, native submit/cancel lifecycle, and a real
  two-connection race returning exactly one conversion. The full Fulfillment module, including both
  concurrency cases, passed three consecutive runs.
- Phase 4 navigation 30 and naming 22 tests passed. The scoped Python/JSON/type/security/audit gate
  passed with the known isolated `prettier-eslint` hook skipped; the changed Desk script was
  formatted separately with the repository-installed formatter.
- Independent Phase 4 review's two P1 findings were fixed and re-reviewed: submit now requires the
  allocation's exact current Equipment Model and the current leaf Company Demo pool Location. No
  P0/P1 findings remain from that review. Computer Use remains deferred for the recorded browser
  capability blocker; no UI pass is claimed.
- Accepted Phase 4 checkpoint backup:
  `sites/tsk512.test/private/backups/20260927_180041-tsk512_test-database.sql.gz`, with matching
  site-config, public-file, and private-file archives. Restore this checkpoint before any Phase 5
  rollback; no normal `local`, shared DEV, UAT, or production site was changed.
- Phase 5 migration and focused verification passed on `tsk512.test`: Company setup 5 unit tests,
  Accounts preview API 1 unit test, Stock Asset Conversion 5 unit + 7 integration tests, and
  Fulfillment 6 unit + 6 integration tests. Coverage includes below/equal/above threshold behavior,
  Accounts-only approval, treatment-override reason, edit invalidation, native valuation preview
  without ledger persistence, exact preview-to-posting GL agreement, and transactional rollback
  when actual valuation differs from the approved preview.
- Phase 5 scoped whitespace/JSON/Python/type/security/audit gates passed with the known isolated
  `prettier-eslint` hook skipped; the changed Desk script was separately formatted successfully
  with the repository-installed formatter. Independent review found no remaining P0/P1 issues in
  permissions, native valuation reuse, hash freshness, rollback, treatment selection, depreciation
  semantics, standalone compatibility, or no-preview-persistence behavior. Browser acceptance
  remains deferred for the recorded host capability blocker; no UI pass is claimed.
- Accepted Phase 5 checkpoint backup:
  `sites/tsk512.test/private/backups/20260927_181650-tsk512_test-database.sql.gz`, with matching
  site-config, public-file, and private-file archives. Restore this checkpoint before any Phase 6
  rollback; no normal `local`, shared DEV, UAT, or production site was changed.
- Phase 6 migration passed twice on `tsk512.test`. Material Request now passes 29 unit tests,
  Fulfillment passes 6 unit + 7 integration tests, legacy Dispatch controller/API pass 8 + 8 unit
  tests, and Stock Asset Conversion remains 5 unit + 7 integration tests. The new integration
  lifecycle proves Draft Issue movement, existing workflow-owned submission, exact Draft Outbound
  Dispatch, submit/POD and reservation consumption, Draft Receipt into QA Hold, workflow-owned
  submission, exact Draft Return Dispatch, submit/POD, and final Returned state. Repeated actions
  return the same draft; deterministic source-row locks serialize concurrent preparation paths.
- Phase 6 exact-allocation validation supports multiple quantity-one allocations from one request
  row, rejects partial/duplicate movement sets and mixed legacy rows, checks current pool Location,
  custodian, reservation and outstanding Dispatch state, and leaves legacy unlinked Dispatch rows
  on their existing validators. Scoped formatting, JSON, Python, type, security and audit gates
  passed. Independent review's concurrency, Demo-boundary, and movement-completeness P1 findings
  were fixed and re-reviewed; no P0/P1 findings remain. Browser acceptance remains deferred for
  the recorded host capability blocker; no UI pass is claimed.
- Accepted Phase 6 checkpoint backup:
  `sites/tsk512.test/private/backups/20260927_183924-tsk512_test-database.sql.gz`, with matching
  site-config, public-file, and private-file archives. Restore this checkpoint before any Phase 7
  rollback; no normal `local`, shared DEV, UAT, or production site was changed.
- Phase 7 migration passed on `tsk512.test`. Fulfillment passes 6 unit + 7 integration tests; the
  full native lifecycle test now sends two Demo Assets, creates an idempotent Draft fixed-asset
  Sales Invoice for one, submits it through ERPNext to `Sold`, returns only the other Asset through
  the Phase 6 Receipt movement and Return Dispatch, cancels the sale through ERPNext to restore the
  exact allocation to `Delivered`, and creates revisioned sale attempt 2. The test verifies the
  consumed reservation boundary, no Draft posting, exact Dispatch provenance, and mixed
  sale/return isolation.
- Phase 7 regressions passed: Material Request 29 unit tests, Sales Invoice Demo API 4 unit tests,
  Sales Invoice setup 5 unit tests, Sales Invoice print behavior 9 unit tests, and legacy Dispatch
  controller/API 8 + 8 unit tests. The scoped whitespace/JSON/Python/type/security/audit gate
  passed; the Desk script was formatted separately with the repository-installed formatter because
  the isolated hook retains its recorded executable-resolution limitation.
- Independent Phase 7 review found no P0/P1 issues in native sale/cancel ownership, permissions,
  deterministic locks, successor/start-return blockers, current-attempt idempotency, non-Demo
  passthrough, or mixed sale/return handling. Computer Use remains deferred for the recorded host
  capability blocker; no UI pass is claimed.
- Phase 8 final automated gates passed on `tsk512.test`: migration converged on a second run;
  Fulfillment 6 unit + 7 integration, Material Request 29, Sales Invoice Demo API 4, Sales Invoice
  setup 5, Sales Invoice print 9, Dispatch controller/API 8 + 8, Stock Asset Conversion 5 unit + 7
  integration, Equipment Model 7 integration, mapping review 3, naming 22, workspace 30, and
  procure-to-pay setup 5 tests all passed. The native sale integration asserts non-empty balanced
  Sales Invoice GL, Asset `Sold`/restoration, exact allocation state, and revisioned retry.
- Final scoped whitespace/JSON/Python/type/security/audit gates passed; the one changed Desk script
  passed the repository-installed `prettier-eslint` formatter separately. The existing isolated
  `npx prettier-eslint` hook resolution failure remains unchanged and does not affect the formatted
  result.
- Accepted Phase 8 checkpoint backup:
  `sites/tsk512.test/private/backups/20260927_190620-tsk512_test-database.sql.gz`, with matching
  site-config, public-file, and private-file archives. Restore this checkpoint to preserve the
  accepted isolated prototype; no normal `local`, shared DEV, UAT, or production site was changed.
- Final Computer Use acceptance is blocked at Step 0 because this host exposes no interactive
  browser/session/recording capability. No site was opened or mutated by the browser tester, no UI
  pass is claimed, and canonical final documentation remains gated. A capable desktop host must
  still record the complete role sequence on `tsk512.test` before owner acceptance or promotion.

## Restart procedure

1. Open this worktree and confirm branch `feat/tsk-512-borrow-prototype`.
2. Confirm the main checkout remains untouched and this branch is not deployed.
3. Read this record and the latest reviewer report.
4. Resume only the next backlog item whose dependencies are recorded complete.
5. Run this prototype's automated tests exclusively on `tsk512.test`.
