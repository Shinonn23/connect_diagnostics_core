# Thai Payroll

Thai payroll configuration is maintained by `connect_diagnostics_core/setup/payroll.py` and applied through the app's install/migrate configuration path.

## Employee data

The payroll configuration uses app-managed Employee Custom Fields defined through the Employee setup path for:

- Social Security eligibility.
- Provident Fund rate.
- Thai national ID and its formatted display value.
- Social Security ID.

National ID validation normalizes the stored value to 13 digits, verifies its checksum, and derives the read-only display value through `connect_diagnostics_core/api/erpnext/employee.py`.

## Payroll configuration

The app seeds its Thailand salary components, Income Tax Slab, current Payroll Period, and `Connect Diagnostics Monthly` Salary Structure only when the corresponding records are absent.

Current formulas include:

- Social Security: `min(base, 17500) * 0.05`.
- Provident Fund: `base * (custom_provident_fund_rate or 0) / 100`.
- Personal income tax uses HRMS taxable-salary calculation through the configured Income Tax Slab.

Employee-specific tax exemptions remain represented through HRMS tax-exemption mechanisms rather than a parallel tax engine.

## Submission boundary

A Salary Slip cannot be directly submitted through the app's supported process. Payroll Entry is the submission boundary and HRMS owns the resulting salary-accrual accounting behavior.
