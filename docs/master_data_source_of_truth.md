# Master Data Verification — Source of Truth

## Overview

Read-only tool that compares master data in Google Sheets against ERPNext and reports mismatches.

All configuration lives in a single Google Sheets tab called `Mapping`. No Python config files needed — add/remove entities by editing the spreadsheet.

## Mapping Tab (Single Source of Truth)

| entity | sheet_column         | erpnext_field        | doctype | is_key |
| ------ | -------------------- | -------------------- | ------- | ------ |
| Uom    | UOM Name             | uom_name             | UOM     | yes    |
| Uom    | Must Be Whole Number | must_be_whole_number |         | no     |
| Brand  | Brand                | brand                | Brand   | yes    |
| Item   | Item Code            | item_code            | Item    | yes    |
| Item   | Item Name            | item_name            |         | no     |
| Item   | Default UOM          | stock_uom            |         | no     |

### Column Definitions

| Column        | Description                                                           |
| ------------- | --------------------------------------------------------------------- |
| entity        | Entity key — also used as the data tab name to read from              |
| sheet_column  | Column header in the data tab                                         |
| erpnext_field | Field name in the ERPNext DocType                                     |
| doctype       | DocType name (required on the `is_key = yes` row, optional on others) |
| is_key        | `yes`/`no` — marks which field is used to match records               |

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

When mismatches are found, results are written to a tab named `Verify Results`:

| Entity | Key | Field | Expected | Actual | Issue Type |
| ------ | --- | ----- | -------- | ------ | ---------- |

Issue types: `Mismatch`, `Missing in ERPNext`, `Missing in Sheet`

## Command

```bash
bench verify-master-data --spreadsheet-id <id>
bench verify-master-data --spreadsheet-id <id> --entity "Uom"
```

## Credentials

```bash
bench --site <site> set-config cd_google_credentials_path "/path/to/service-account.json"
```
