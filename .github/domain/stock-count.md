# Stock Count

## Location model

- Physical stock locations are modeled entirely through ERPNext's native
  Warehouse tree: a location is a leaf `Warehouse` (`is_group: 0`) nested under
  its parent Warehouse via `parent_warehouse`. There is no separate location
  DocType or dimension.
- This replaces a retired custom **Storage Location** DocType that was also
  registered as an ERPNext Inventory Dimension (`apply_to_all_doctypes: 1`),
  which auto-generated `storage_location` / `to_storage_location` /
  `from_storage_location` / `rejected_storage_location` Custom Fields on every
  stock transaction doctype plus Stock Ledger Entry and Stock Closing Balance.
  The dimension was un-registered (`frappe.delete_doc("Inventory Dimension",
"Storage Location", ...)`, whose `on_trash()` deletes the generated Custom
  Field records) and its orphaned columns dropped explicitly — deleting a
  Custom Field does not drop the underlying column, so schema-changing patches
  in this app always pair a field/dimension removal with an explicit
  `ALTER TABLE ... DROP COLUMN IF EXISTS`.
- Migration path (patches/v1_0, in order): `migrate_storage_locations_to_warehouses`
  (each Storage Location row becomes a child Warehouse) →
  `migrate_stock_count_warehouse_field` (Stock Count's old single `warehouse`
  Link becomes one `Stock Count Warehouse` child row, then both orphaned
  `warehouse`/`storage_location` columns on Stock Count itself are dropped) →
  `retire_storage_location_inventory_dimension` (dimension + generated columns
  removed) → `remove_storage_location_doctype` (the DocType itself deleted,
  mirroring `remove_alias_name_doctype.py`). All four patches read/write via
  raw SQL or `frappe.db.exists` guards rather than the ORM where the source
  field is already gone from DocType meta, and all run in `[post_model_sync]`
  like every other patch in this app — Frappe's schema sync only _adds_
  columns for JSON field changes, it never drops one, so the orphaned source
  data is still there for a `post_model_sync` patch to read.

## Stock Count scope

- `Stock Count.warehouses` is a `Table MultiSelect` (options: `Stock Count
Warehouse`, a one-field `warehouse` Link child table) — a count can span
  several warehouses/locations at once, following the idiomatic Frappe
  multi-select pattern (compare `erpnext.manufacturing.doctype
.production_plan_material_request_warehouse`).
- `Stock Count Item.warehouse` stays a plain Link: each count _line_ is always
  exactly one leaf warehouse, even when the header selects several. Duplicate
  detection (`validate_duplicate_lines`) keys on
  `(item_code, warehouse, batch_no, serial_no)`.
- `selection_method` (monthly cycle counts only — yearly counts always cover
  every selected warehouse):
    - `Manual` — hand-pick any number of items across all selected warehouses.
    - `Random by Count` / `Random by Percentage` — sample at the count-line
      grain (item + warehouse + batch/serial is one unit) across all selected
      warehouses.
    - `Random by Warehouse` — picks one of the selected warehouses at random
      (`random.choice`, done in `fetch_items` _before_ querying, not inside
      `_apply_selection`), then every item in that one warehouse is a candidate
      — no further sub-sampling and no extra required field. This replaced the
      old "Random by Zone", which sampled within a Storage Location's `zone`
      field; there is no replacement grouping concept, since a warehouse is now
      itself the finest location grain.
- `_leaf_warehouses()` in `api/erpnext/stock_count.py` expands every selected
  warehouse that is a group (`is_group`) into its descendant leaves via
  `get_descendants_of`, then dedupes preserving order — so selecting a parent
  warehouse still counts every location beneath it.
- `fetch_items` builds count lines straight from Stock Ledger Entry grouped by
  `item_code, warehouse[, batch_no, serial_no]`; there is no sub-warehouse
  scoping left to apply, since Bin/SLE's item+warehouse grain is already the
  finest grain there is once locations are warehouses.

## Generated Stock Entries

- `generate_holding_transfer` (monthly) and `generate_stock_adjustment`
  (yearly) build one Stock Entry whose **rows** each carry their own counted
  line's warehouse (`s_warehouse`/`t_warehouse` = `row.warehouse`), not a
  single document-wide warehouse — required now that the header has no single
  warehouse, and it also fixed a latent bug where a group-warehouse-scoped
  count previously mis-attributed every generated row to the header warehouse
  instead of the row's actual leaf warehouse.
- The Stock Entry header's `from_warehouse`/`to_warehouse` convenience fields
  are only set when every row shares one warehouse — ERPNext's own Stock Entry
  validation (`validate_warehouse`) checks `s_warehouse`/`t_warehouse` per
  row, not the header, so leaving the header blank when rows differ is safe.

## Stock movement freeze during a count

- `api/erpnext/stock_count_freeze.py` blocks stock-moving transactions
  against whatever a _draft_ (`docstatus=0`) Stock Count has already fetched
  lines for. Hooked as `before_submit` on `Stock Entry`, `Delivery Note`,
  `Purchase Receipt`, `Sales Invoice`, `Purchase Invoice`, `Stock
Reconciliation`, and `Pick List` — submission is the point stock actually
  moves, matching this app's existing `regulatory_transactions.py` convention
  of gating at `before_submit` rather than `validate`.
- Freeze granularity differs by count type: a **Monthly cycle count** freezes
  only the exact `(item_code, warehouse)` pairs present in its `Stock Count
Item` rows; a **Yearly count** freezes every item in each of its selected
  `Stock Count Warehouse` rows (whole warehouse), since a yearly count already
  covers the entire warehouse and per-item checking there would be redundant.
  Both checks additionally require the Stock Count to already have at least
  one `Stock Count Item` row — the freeze window is Fetch Items through
  Submit/Cancel, not draft creation, so an empty draft blocks nothing.
- `Sales Invoice`/`Purchase Invoice` are only checked when `update_stock` is
  set, since that is the only case those doctypes move stock. `Stock Entry`
  checks both `s_warehouse` and `t_warehouse` per row (either side changing
  quantity can invalidate a count); `Delivery Note`/`Sales Invoice` check
  `warehouse` and `target_warehouse` (internal transfer); `Purchase
Receipt`/`Purchase Invoice` check `warehouse` and `rejected_warehouse`.
- This is a hard block with **no bypass** — no settings doctype, no
  role-based override, no approval document. If an emergency-movement
  exception process is needed later, design it as its own change; do not
  silently add one here.

## No approval workflow

- Stock Count's submit gate is role permission only (`Stock Manager` /
  `Accounts Manager` / `System Manager` can submit), matching this app's
  documented no-app-owned-workflow baseline — see `connect_diagnostics_core/AGENTS.md`.
  A prior "Stock Count Approval" Frappe Workflow was
  removed app-wide in the custom-workflow reset; do not reintroduce a
  `count_state`-style field or workflow-state check here. `stock_count.js`
  gates the "Generate Holding Transfer" / "Generate Stock Adjustment" buttons
  on `frm.doc.docstatus === 1`, nothing else.
