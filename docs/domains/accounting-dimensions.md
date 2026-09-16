# Accounting Dimensions — Department & Territory

The app ships ERPNext's standard `Department` and `Territory` as Accounting
Dimension records in `fixtures/accounting_dimension.json`. Their values on
accounting documents flow to GL Entry. ERPNext's Accounting Dimension lifecycle
generates and maintains the corresponding accounting-document fields; this app
does not define those fields as Custom Fields.

## HR separation

Department is the accounting master. The one-way migration clears Department links
from HR records and removes the former `accounting_department` custom fields from
Employee and Department. Payroll and other HR processes do not populate this
dimension.

## Migration

`migrate_accounting_departments_to_departments` replaces the retired custom
Accounting Department tree. It deletes existing standard Department records, copies
the source tree into standard Department, remaps accounting document and GL values,
then deletes the source DocType. The migration is intentionally one-way.

## Key files

- `connect_diagnostics_core/fixtures/accounting_dimension.json` — exported dimension records
- `connect_diagnostics_core/setup/accounting_dimension.py` — inert compatibility shim for the
  legacy setup hook; it must not write dimensions or fields
- `connect_diagnostics_core/patches/v1_0/migrate_accounting_departments_to_departments.py`
  — tree, ledger, and HR-link migration
