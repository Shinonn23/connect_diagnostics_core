# Accounting Dimensions — Department & Territory

This app registers two ERPNext **Accounting Dimensions** so their values reach the
GL: **Department** (backed by the custom `Accounting Department` tree) and
**Territory** (backed by the standard ERPNext `Territory` tree). Both are wired the
same way — see [Registering the dimensions](#registering-the-dimensions). Department
carries the extra HR-vs-accounting subtlety below; Territory does not.

## Two separate "Department" concepts

The system keeps two unrelated masters that both say "Department":

- **HR `Department`** (ERPNext `Setup` module, customized by HRMS) — the org chart.
  Employees are assigned to it; Payroll Entry's own `department` field is a link to
  it, used **only** to filter which employees a payroll run includes. Nothing about
  it is a financial dimension.
- **`Accounting Department`** (module `Connect Diagnostics Accounting`) — a company-
  scoped nested-set tree modeled on Cost Center, used to slice Income/Expense for
  financial reporting. It is the value behind the `department` custom field already
  present on Sales/Purchase Invoice and their item/tax rows.

These are deliberately **not** merged. HR reorganizations must not silently rewrite
financial reporting buckets, and HR roles must not implicitly own a finance master.

## Registering the dimensions

`connect_diagnostics_core/setup/accounting_dimension.py::ensure_configuration()`
registers each entry in `DIMENSIONS` idempotently on `after_install`/`after_migrate`
(called from `setup/__init__.py::apply_all()` after the custom-field pass, so the
pre-existing `department`/`territory` fields already exist):

- **Department** — `document_type="Accounting Department"`, `fieldname="department"`.
- **Territory** — `document_type="Territory"`, `fieldname="territory"`.

Both fieldnames already exist as fields on the Sales/Purchase transaction doctypes
(`department` as custom fields; `territory` as custom fields plus a **native** field
on Sales Invoice), so ERPNext's `validate_fieldname_conflict()` leaves those
untouched and reuses their value. Every **other** doctype in
`accounting_dimension_doctypes` that lacks the field — most importantly **GL Entry**
and **Journal Entry Account** — has it created automatically. This is what finally
carries the value down to the ledger; before registration it stopped at the source
documents.

`mandatory_for_bs` / `mandatory_for_pl` and `dimension_defaults` are intentionally
left unset — those are owner decisions made in Desk, not in code.

Territory needs nothing further: it is a standard ERPNext doctype (its own Desk home
already exists, so no navigation change), and Payroll Entry has no native `territory`
field, so the payroll leakage fix below does not apply to it.

## Payroll cost allocation (unchanged) and the dimension fix

Payroll GL postings resolve **Cost Center** per employee via HRMS's existing chain:
`Employee.payroll_cost_center` → (fallback) `Department.payroll_cost_center` →
(fallback) `Payroll Entry.cost_center`. This app does not change that chain.

To mirror it for the new dimension, `Department` and `Employee` each gain an
`accounting_department` custom field (`setup/department.py`, `setup/employee.py`);
`Employee.accounting_department` defaults from `Department.accounting_department`
via `fetch_from` + `fetch_if_empty`, exactly like `payroll_cost_center`.

**Correctness fix — required, not optional.** HRMS's `update_accounting_dimensions`
copies each enabled dimension value straight off the Payroll Entry
(`row.update({dimension: self.get(dimension)})`). Payroll Entry's `department` field
is the **HR** Department, but the dimension's `department` field is a link to
**Accounting Department** — so once the dimension is registered, every Journal Entry
Account row Payroll Entry generates would receive an HR Department docname in an
Accounting-Department field (silent data corruption). `PayrollEntryAccountingDimensionMixin`
(`api/erpnext/payroll_entry.py`, wired via `extend_doctype_class` alongside
`PayrollEntryReviewMixin`) overrides `update_accounting_dimensions` to blank
`department` on those rows. Payroll's generated Journal Entries therefore post with
`department` **blank**.

### Tier 1 (shipped) vs Tier 2 (deferred)

- **Tier 1 (this change):** register the dimension, add the supporting fields, and
  suppress the payroll corruption (blank `department` on payroll JEs).
- **Tier 2 (not built):** per-employee Accounting Department split on payroll's GL
  expense side (mirroring the per-employee Cost Center split). It requires
  overriding ~6 non-whitelisted HRMS internals and is HRMS-upgrade-fragile — a
  separate, owner-approved change.

**Dependency to watch:** if the owner later enables `mandatory_for_bs`/
`mandatory_for_pl` on this dimension, payroll's blank-`department` Journal Entries
will fail GL validation — Tier 2 becomes mandatory at that point.

### Out of scope, flagged

`Expense Claim` is also in HRMS's `accounting_dimension_doctypes` and also has a
native colliding `department` field; `Expense Claim Detail` / `Expense Taxes and
Charges` have none and will gain a new `department` link when the dimension is live.
Audit Expense Claim's GL posting for the same `self.get("department")` issue before
relying on the dimension there.

## Key files

- `connect_diagnostics_core/setup/accounting_dimension.py` — dimension registration
- `connect_diagnostics_core/setup/department.py`,
  `connect_diagnostics_core/setup/employee.py` — `accounting_department` fields
- `connect_diagnostics_core/api/erpnext/payroll_entry.py` — `PayrollEntryAccountingDimensionMixin`
- `connect_diagnostics_core/hooks.py` — `extend_doctype_class["Payroll Entry"]`
- `connect_diagnostics_core/setup/workspace.py` — Accounting Department navigation
  (ERPNext `Invoicing` plus HRMS `HR Setup` and `Payroll` Setup sections)
