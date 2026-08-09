# Customer Sales Document Requirements

- A Customer states what it needs before a sale proceeds, in the *Sales Document
  Requirements* section of its Document / Print Configuration tab. These are process
  gates, not print settings: they say what must exist, while the print configuration
  says how the resulting documents print.
- `quotation_required` rejects a Sales Order with no `Sales Order Item.prevdoc_docname`,
  the standard ERPNext link to the Quotation a line was mapped from.
  `source_purchase_order_copy_required` rejects a Sales Invoice whose
  `source_purchase_orders` table has no row naming either a `purchase_order` or a
  `purchase_order_file`.
- `use_customer_po` was renamed to `source_purchase_order_copy_required`. It never held
  the Customer's own purchase order — it asks whether the Customer wants a copy of the
  Purchase Order **we** placed with our supplier — and the old name collided with the
  standard `Sales Order.po_no` ("Customer's Purchase Order"). Its default also flipped
  from 1 to 0; only a handful of Customers actually ask for the copy. Do not reintroduce
  the old name.
- `connect_diagnostics_core/api/erpnext/sales_requirements.py` owns the rules and the
  `validate` hook for both DocTypes. Every evaluator accepts a `Document` or a plain
  mapping so one form and a whole report page share the same logic; the whitelisted
  `get_transaction_requirements` takes the form's document rather than a name, so an
  unsaved order shows the requirement while it can still be met.
- A holder of the `Sales Requirement Override` role proceeds by writing
  `requirement_override_reason`, which stays on the document as the audit trail. The
  role alone does not bypass the gate, and the reason is cleared once the gap closes.
- The source Purchase Order copy is **concatenated as extra PDF pages, never rendered
  inside the tax invoice format**. Nesting fails for two reasons: the `Purchase Order`
  format's CSS sets `@page`, `html, body` and `.print-format` globally and would rewrite
  the invoice's page geometry, and its template calls `register_print`, which would log a
  Purchase Order print to a supplier every time a Customer's invoice printed. The join
  therefore happens in the `download_pdf` override using `pypdf`, which frappe already
  depends on. The `source_purchase_orders` table carries one row per Purchase Order, each
  appended in table order `copies` times (a blank row count falls back to
  `Customer.purchase_order_copy_count`). This covers the PDF channel only — the Print
  button hands HTML to the browser, so the Sales Invoice form offers one print button per
  source row.
- Rendering the Purchase Order deliberately sets `frappe.flags.ignore_print_permissions`.
  The copy is a page the Customer is meant to receive, so anyone allowed to print the
  invoice may produce it; requiring Purchase Order print rights would stop sales staff
  from downloading their own invoices. Like the print audit, the join is fail-open: a
  failure is logged with context and the invoice PDF is returned unchanged.
- `setup/print_configuration_template.py` also creates three document policy Templates —
  `Tax Invoice Only`, `Tax Invoice and Receipt`, `Tax Invoice and Abbreviated Receipt` —
  named after what they print rather than after a Customer Group, because more than one
  group follows each. They are initial contents only: an existing Template is never
  overwritten, since a Template is user data once created.
- The retired mapping doctypes (`DKSH Item Mapping`, `Partner Item Mapping`), workflow,
  roles, Sales Order fields, and dedicated selling Price List must not be recreated. The
  new `DKSH Item` reference master is a distinct, allowed DocType, not one of those.
  Retirement migrations may delete only those explicitly retired records and fields; they
  must not rename or delete Customer, Item, Supplier, Asset, or historical transactions.
- The retired DKSH APIs and hooks are explicitly exempt from the usual one-release
  deprecation period because this domain was removed before go-live. Do not restore
  compatibility stubs for them.
