# Customer Demo Material Request

## Goal

Implement Customer Demo requests through the standard Material Request `items` table. A requested Fixed Asset Item maps to an existing Stock Item, which can be capitalized into individual Assets. Requests can hold exact Assets expected back from another customer's demo and continue after the selected Assets return.

## Scope and owned files

- `connect_diagnostics_core/connect_diagnostics_core/custom/item.json`: sole source for Item Custom Fields, Item Property Setters, and Item field order, including existing fields and the Stock Item mapping.
- `connect_diagnostics_core/setup/item.py` and Item-only declarations in `setup/tds.py`: remove duplicate Item schema/order setup; retain non-Item TDS behavior.
- `connect_diagnostics_core/custom/material_request.json`, `asset_movement.json`, and `asset_capitalization.json`: Customer Demo Custom Fields are exported with their respective DocTypes. Customer Demo uses the standard Material Request `set_warehouse` field; no child-row or Item Warehouse field is added.
- New Customer Demo Candidate/Asset Claim DocTypes: exact candidate Assets and exclusive per-Asset claims.
- `connect_diagnostics_core/api/erpnext/material_request_asset_transfer.py`, Material Request and Asset Movement client scripts, and `hooks.py`: MR validation, Hold/return/Create actions, claim lifecycle, and Movement authorization.
- Focused API/setup/DocType tests and restore-patch tests.

## Acceptance criteria

- Customer Demo uses standard MR item rows containing non-stock Fixed Asset Items; each maps to an existing Stock Item. The standard Material Request `set_warehouse` field is the single Source Warehouse for paired Stock Items.
- Existing eligible Assets at Source Location are preferred; native Asset Capitalization consumes paired stock for the remaining units.
- Hold stores a reason and exact candidate Assets per MR unit. Candidate claims are unique and atomically protected by Asset-row locks.
- Only the candidate's return to the claimant Source Location makes the request Ready and sends one notification. Claimed Assets cannot be moved elsewhere or cancelled; cancellation, replacement, and fulfillment release claims.
- Create offers native Asset Capitalization and Asset Movement drafts. Return movement validates submitted Customer Demo provenance and matching Source Location.
- Existing Asset Transfer behavior remains intact. ERPNext's native Material Request status remains native.
- Existing Item fields, setters, and intended field order are preserved in `custom/item.json`; no Custom Field declarations remain in setup Python.

## Risks and verification

- Asset Movement and claim operations must lock Asset rows in sorted order and re-read Asset/claim state before authorization.
- Run focused tests and pinned pre-commit. Automated and Computer Use tests target `local.test` only; the currently inspected bench does not provide that site, so report this gate blocked unless the approved test site becomes available.
- Complete independent code review, runtime acceptance, and final behavior documentation before closing.

## Rollback

Revert the Customer Demo fields/DocTypes, movement hooks, and UI as one change. Preserve the current Item fields and property setters in `custom/item.json` during rollback; do not restore duplicate Item setup declarations.

The legacy setup package initializer imports `setup.item`; the repository generated-file guard prevents editing `setup/__init__.py`. `setup/item.py` therefore remains as an inert compatibility shim with no field or setter definitions.
