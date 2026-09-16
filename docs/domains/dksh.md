# DKSH module

- `Connect Diagnostics DKSH` (in `modules.txt`, folder
  `connect_diagnostics_core/connect_diagnostics_dksh/`) is the single home for the DKSH
  domain: the DKSH reference masters and the deferred DKSH daily sales import / analysis.
  It is registered in `setup/print_format.py::APP_MODULES` so any future DKSH Print Format
  is not purged. `DKSH Item` lives here (moved from Core by
  `patches/v1_0/move_dksh_item_to_dksh_module.py`, which repoints `DocType.module` and
  reloads from the new folder — records are untouched).
- **DKSH reference master convention.** Each one is a standalone DocType autonamed by its
  DKSH code (`autoname: field:<code>`), carrying an **optional** `Link` to the CD master it
  references (blank = a DKSH stand-alone record). It is reference data only — no workflow,
  no roles, no control over the CD master's lifecycle or transaction eligibility — and may
  offer a Convert-to-CD action. Two shared behaviours live in
  `connect_diagnostics_dksh/reference.py`, so every master is built the same way:
  `validate_reference(doc, *, code_fields, link_field, master_doctype)` trims the codes and
  rejects a second reference pointing at the same CD master; `inject_connection(data, *,
reference_doctype, link_field, group_label)` is the generic `override_doctype_dashboards`
  helper that surfaces the master under the CD form's Connections. `DKSH Item` and
  `api/erpnext/item.py::get_item_dashboard_data` both delegate here.
- `DKSH Customer` is the reference master for customers that carry a 9-digit DKSH code
  differing from their CD Customer Code. It follows the convention above (autoname
  `field:dksh_customer_code`, optional `customer` link, surfaced under the Customer form's
  Connections via `api/erpnext/customer.py::get_customer_dashboard_data`) and additionally
  stores DKSH's own `customer_name` plus a contact/tax block (`tax_id`, `branch_code`,
  address fields, `phone`, `email_id`) for the Convert flow.
- **Convert to CD Customer.** When a `DKSH Customer` has no `customer`, the form
  (`public/js/custom/dksh_customer/doctype.js`) offers **Convert to CD Customer**, which
  opens a **prefilled New Customer form** (name, tax id, branch code, and the read-only
  provenance field `custom_source_dksh_customer` from the exported Customer Customize Form
  `custom/*.json`); the user types the CD
  Customer Code (the document name) and saves. Customer `after_insert`
  (`link_source_dksh_customer`) then links the DKSH Customer back under a row lock — only
  when it is still unclaimed, so it is idempotent — and, when the DKSH Customer carries an
  address and the new Customer has none, creates a primary Billing Address from it (with the
  matching `tax_id`/`branch_code`) so the tax-invoice readiness gate can pass. That address
  creation is fail-open: a failure is logged and never aborts the Customer. Phone→Contact
  creation is a deferred follow-up. When `customer` is already set the form offers **Go to
  Customer** instead.
