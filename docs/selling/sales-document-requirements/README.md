# Sales Document Requirements

Customer Sales Document Requirements define prerequisites for selling transactions. They are process gates, not print configuration.

The current requirement is `quotation_required`: a Sales Order must carry the standard ERPNext Quotation mapping through `Sales Order Item.prevdoc_docname`.

A user with the `Sales Requirement Override` role may proceed only by recording `requirement_override_reason`; role membership alone does not bypass the rule. The reason remains on the document as audit evidence and is cleared when the underlying gap no longer exists.

Server-side ownership is in:

- `connect_diagnostics_core/api/erpnext/sales_requirements.py`
