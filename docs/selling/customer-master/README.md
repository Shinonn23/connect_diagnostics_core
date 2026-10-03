# Customer Master

A Customer uses its required manual Customer Code as the document name. The code may be corrected until the Customer has its first Quotation, Sales Order, Sales Invoice, or Delivery Note; after that point the app prevents the rename path that would rewrite already-issued transaction references.

Tax-invoice readiness is calculated live from the Customer and related master data. A submitted Sales Invoice may surface a readiness warning when the required primary Billing Address, Thai address, tax ID, or branch code is incomplete; the readiness check is advisory and does not replace ERPNext submission rules.

`Customer Credit Request` is the controlled route for changing payment terms and credit limits. Its intrinsic submit effect applies the requested values under locking. Direct edits remain restricted by the app's Customer accounting permission rules.

Canonical implementation includes:

- `connect_diagnostics_core/api/erpnext/customer.py`
- `connect_diagnostics_core/setup/customer.py`
