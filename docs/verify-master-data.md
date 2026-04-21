# Master Data Verification — Source of Truth

## Overview

Read-only tool that compares master data in Google Sheets against ERPNext and reports mismatches.

All configuration lives in a single Google Sheets tab called `Mapping`. No Python config files needed — add/remove entities by editing the spreadsheet.

## Mapping Tab (Single Source of Truth)

| sheet_name | sheet_column         | erpnext_field        | doctype             | is_key | parent_doctype |
| ---------- | -------------------- | -------------------- | ------------------- | ------ | -------------- |
| Uom        | UOM Name             | uom_name             | UOM                 | yes    |                |
| Uom        | Must Be Whole Number | must_be_whole_number |                     | no     |                |
| Brand      | Brand Name           | brand                | Brand               | yes    |                |
| Item       | Item Code            | item_code            | Item                | yes    |                |
| Item       | Item Name            | item_name            |                     | no     |                |
| Bundle     | Parent Item Code     | ignored              | Product Bundle      | yes    |                |
| Bundle     | Item                 | Item                 | Product Bundle Item | no     | Product Bundle |
| Bundle     | Qty                  | Qty                  | Product Bundle Item | no     | Product Bundle |

### Column Definitions

| Column         | Description                                                                   |
| -------------- | ----------------------------------------------------------------------------- |
| sheet_name     | Sheet key and also the data tab name to read from                             |
| sheet_column   | Column header in the data tab                                                 |
| erpnext_field  | Field name or label resolved from ERPNext metadata                            |
| doctype        | Parent DocType for non-child rows, child DocType for child rows               |
| is_key         | `yes`/`no` — marks key row in each mapping group                              |
| parent_doctype | Optional. Required for child rows to link child DocType to its parent DocType |

## Child Table Mapping Behavior

- One parent DocType can have multiple child DocTypes in the same `sheet_name`.
- Verifier now splits mapping groups by `(sheet_name, parent_doctype, child_doctype)` and validates each child group independently.
- Entity keys are deterministic:
    - single mapping in a sheet: `sheet_name`
    - multiple mappings in a sheet: `sheet_name:doctype`
    - child mapping groups: `sheet_name:parent_doctype:child_doctype`

## Key Matching Behavior (Current)

- For flat entities, matching uses the resolved key field from mapping logic.
- For child entities, matching groups expected rows by parent identifier and compares children under each parent group.
- If ERPNext records use hash-generated internal keys (`name`), the sheet key must currently align with that matching key path. Pure business-key remapping for hash-only internal IDs is not yet implemented.

## Query Method

All entities use `frappe.get_all()` to fetch actual data from ERPNext:

```python
frappe.get_all(
    "<DocType>",
    fields=["<key_field>", "<mapped_field_1>", ...],
    as_list=False,
)
```

## Results Output

CLI summary prints:

- aligned totals (entities, rows expected/matched, mismatches, missing counts)
- PASS/FAIL status
- per-entity issue details (mismatch, missing in ERPNext, missing in sheet)

When mismatches are found, details are written to a tab named `Verify Results`:

| Entity | Key | Field | Expected | Actual | Issue Type |
| ------ | --- | ----- | -------- | ------ | ---------- |

Issue types: `Mismatch`, `Missing in ERPNext`, `Missing in Sheet`

## Command

```bash
bench verify-master-data --spreadsheet-id <id>
bench verify-master-data --spreadsheet-id <id> --entity "Uom"
bench verify-master-data --spreadsheet-id <id> --ignore-missing-in-sheet
```

## Credentials

```bash
bench --site <site> set-config cd_google_credentials_path "/path/to/service-account.json"
```
