# Customer Sales Document Requirements

- A Customer states what it needs before a sale proceeds, in its _Sales Document
  Requirements_ tab. This is a process gate, not a print setting: it says what must
  exist. Print options are chosen per print in the print sidebar.
- `quotation_required` rejects a Sales Order with no `Sales Order Item.prevdoc_docname`,
  the standard ERPNext link to the Quotation a line was mapped from. It is the only
  Customer requirement; the former source-Purchase-Order-copy requirement (and its
  `use_customer_po` predecessor, plus the whole "attach the supplier PO to the invoice
  PDF" feature) was removed.
- `connect_diagnostics_core/api/erpnext/sales_requirements.py` owns the rule and the
  `validate` hook for Sales Order. Every evaluator accepts a `Document` or a plain
  mapping so one form and a whole report page share the same logic; the whitelisted
  `get_transaction_requirements` takes the form's document rather than a name, so an
  unsaved order shows the requirement while it can still be met.
- A holder of the `Sales Requirement Override` role proceeds by writing
  `requirement_override_reason`, which stays on the document as the audit trail. The
  role alone does not bypass the gate, and the reason is cleared once the gap closes.
- The retired mapping doctypes (`DKSH Item Mapping`, `Partner Item Mapping`), workflow,
  roles, Sales Order fields, and dedicated selling Price List must not be recreated. The
  new `DKSH Item` reference master is a distinct, allowed DocType, not one of those.
  Retirement migrations may delete only those explicitly retired records and fields; they
  must not rename or delete Customer, Item, Supplier, Asset, or historical transactions.
- The retired DKSH APIs and hooks are explicitly exempt from the usual one-release
  deprecation period because this domain was removed before go-live. Do not restore
  compatibility stubs for them.
