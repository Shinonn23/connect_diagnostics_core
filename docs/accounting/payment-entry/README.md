# Payment Entry

ERPNext owns Payment Entry posting and accounting effects.

The app's custom Payment Entry behavior is limited to validated integration rules. Allocated Purchase/Sales Invoice references must carry compatible accounting dimensions, and the Payment Entry dimensions are synchronized through the app's Payment Entry integration before posting.

Canonical implementation:

- `connect_diagnostics_core/api/erpnext/payment_entry.py`
- `connect_diagnostics_core/public/js/custom/payment_entry/doctype.js` for Desk-only assistance

Server-side validation remains authoritative; client behavior must not be relied on as the only enforcement point.
