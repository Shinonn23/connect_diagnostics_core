# Print Behavior

App-owned Print Formats and Print Log belong to the `Connect Diagnostics Print` module.

## Print format ownership

- App-owned Print Formats are self-contained records: Jinja/HTML remains in the format `html` field and format-specific CSS remains in `css`.
- Shared date formatting uses the registered Buddhist-era date helper; templates do not perform their own year conversion.
- Monetary rendering uses the registered shared money helpers rather than local formatting macros.
- Pagination splits whole measured item rows before rendering; CSS is not used to hide overflow.
- Real visual verification uses Frappe's native print/PDF rendering path with site assets and print media, not a standalone file screenshot.

## Print sidebar

The print page loads the app print engine before its providers. Providers register bounded per-document controls and send request-only values through Frappe's print settings. Print options are not persisted as Customer configuration.

When no app provider applies, the engine delegates back to Frappe's native additional print settings so unrelated DocTypes retain standard behavior.

Canonical implementation:

- `connect_diagnostics_core/public/js/custom/print/engine.js`
- `connect_diagnostics_core/public/js/custom/print/providers/`
- `connect_diagnostics_core/api/erpnext/print_configuration.py`
- `connect_diagnostics_core/setup/print_documents.py`

## Print audit

Real print and PDF-download channels create insert-only Print Log records. Preview and emailed PDFs are outside that audit channel. Print audit failures are logged without blocking the user's print operation.

Canonical implementation:

- `connect_diagnostics_core/api/frappe/print_log.py`
- `connect_diagnostics_core/connect_diagnostics_print/doctype/print_log/`
