# Payroll Behavior

HRMS owns Salary Slip, Payroll Entry, Salary Structure, Salary Structure Assignment, Income Tax Slab, and Payroll Period behavior. The app adds Thailand-specific configuration and validation without replacing HRMS payroll posting.

## Shared invariants

- Salary Slips are submitted only through Payroll Entry.
- HRMS remains the owner of salary accrual and its standard accounting path.
- Thailand-specific Employee fields on the HRMS Employee DocType are code-managed by the app's Employee setup module.
- Payroll configuration is applied idempotently and must not overwrite later intentional manual edits to create-only configuration records.

## Workflows

- [Thai payroll](thai-payroll/README.md)
