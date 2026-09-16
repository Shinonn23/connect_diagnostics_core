# Thai Payroll

- Payroll config is code-managed and idempotent in `connect_diagnostics_core/setup/payroll.py`,
  applied on `after_install` / `after_migrate` through `ensure_configuration()`. The payroll
  DocTypes are HRMS's (Salary Component / Structure / Structure Assignment / Income Tax Slab /
  Payroll Period / Salary Slip); `erpnext_thailand` covers only creditor withholding (ภงด3/53),
  **not** employee personal income tax.
- Employee payroll fields are third-party Employee Custom Fields managed through Frappe
  Customize Form and committed through the selected module's exported `custom/*.json`, split
  across two sections.
  The **Thai Payroll** section (Overview tab) holds only genuine payroll settings:
  `custom_social_security_eligible` and `custom_provident_fund_rate` (Percent, per-employee,
  **no default** —
  real rates differ, e.g. 3% / 7.5%). The **National ID & Social Security** section (Personal
  Details tab, right after Passport Details) holds identity data instead: `custom_national_id` (13-digit
  citizen ID, stored as plain digits — no dashes; doubles as the personal tax ID for ภงด1/ภงด1ก —
  Employee otherwise stores only `passport_number`), the read-only `custom_national_id_display`
  (auto-formatted `X-XXXX-XXXXX-XX-X`), and `custom_social_security_id`. No property setter makes
  any of these five required.
- `custom_national_id`/`custom_national_id_display` are kept consistent by
  `connect_diagnostics_core.api.erpnext.employee.normalize_national_id`, wired as the Employee
  `validate` hook (`hooks.py`): it strips non-digits from `custom_national_id`, `frappe.throw()`s unless
  exactly 13 digits remain with a valid check digit (`has_valid_national_id_checksum`, mod-11 over
  digits 1-12), and computes `custom_national_id_display` from the cleaned value. Existing records are
  backfilled once by `patches/v1_0/backfill_national_id_display.py`, which reuses the same length
  and checksum checks to decide what to skip. The patch's legacy column names are retained only
  for backwards-compatible migration handling.
- `setup/payroll.py` seeds, **create-only-if-absent** so a later manual edit survives: 14 Salary
  Components (8 earnings / 6 deductions), the `Thailand Personal Income Tax` Income Tax Slab, a
  current-year Payroll Period, and the `Connect Diagnostics Monthly` Salary Structure. The
  company-scoped records (slab, period, structure) are skipped fail-open when no default Company
  resolves; Salary Components are company-agnostic.
- Formulas run in the HRMS component eval context (`hrms/payroll/utils.get_component_eval_context`),
  which exposes `base` (from the Structure Assignment), Employee fields, and the `min` / `max`
  globals. Social Security = `min(base, 17500) * 0.05` — the company caps the contribution base at
  17,500 (875/month), above the statutory 15,000 / 750. Provident Fund =
  `base * (custom_provident_fund_rate or 0) / 100`. Withholding Tax uses
  `variable_based_on_taxable_salary`
  so HRMS computes PIT from the slab.
- The slab folds the personal allowance (60,000) and the capped 50% expense deduction (max 100,000)
  into `standard_tax_exemption_amount = 160000`; per-person deductions (spouse, children, insurance,
  SSO/PF paid) flow through Employee Tax Exemption Declarations, enabled by `allow_tax_exemption`.
  The `Employee Welfare Fund` component is seeded **disabled** until it becomes mandatory
  (1 Oct 2026, 0.25%).
- Salary Slips are submitted only through Payroll Entry. This one rule is independent of any
  workflow and survives the custom-workflow reset: `salary_slip.validate_submission` still blocks a
  direct Salary Slip submit (`frappe.flags.via_payroll_entry` is set only by HRMS's Payroll Entry
  batch), so HRMS creates the salary-accrual Journal Entry through its standard Payroll Entry path.
  The former `Salary Slip Review` workflow and its `Salary Slip Reviewed` gate were removed — no
  review state is required before Payroll Entry submits a slip.
- Not yet built — do not assume present: per-employee Salary Structure Assignment (base pay),
  historical Salary Slip seeding for mid-year go-live YTD (SSO / income / tax accumulate only from
  submitted slips; HRMS opening fields cover tax only, and only for mid-period joiners), and the
  Thai year-end ภงด1 / ภงด1ก and annual Social Security reports (absent from HRMS and
  `erpnext_thailand` — must be built in-app).
