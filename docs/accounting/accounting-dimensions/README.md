# Accounting Dimensions

The app ships ERPNext's standard `Department` and `Territory` as Accounting Dimension records through `connect_diagnostics_core/fixtures/accounting_dimension.json`.

ERPNext owns the generated accounting-document fields and their propagation to GL Entry. The app does not recreate those generated fields as Custom Fields.

## Department boundary

`Department` is the accounting master. HR records are not used as the source of the accounting dimension, and payroll/HR processing does not implicitly populate Department accounting values.

## Canonical implementation

- `connect_diagnostics_core/fixtures/accounting_dimension.json` — dimension records.
- `connect_diagnostics_core/setup/accounting_dimension.py` — compatibility/setup boundary; it must not create substitute dimension fields.
