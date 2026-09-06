# Accounting Dimensions — Department & Territory

The app registers ERPNext's standard `Department` and `Territory` as Accounting
Dimensions. Their values on accounting documents flow to GL Entry.

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

- `connect_diagnostics_core/setup/accounting_dimension.py` — dimension registration
- `connect_diagnostics_core/patches/v1_0/migrate_accounting_departments_to_departments.py`
  — tree, ledger, and HR-link migration
