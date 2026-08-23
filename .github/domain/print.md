# Print

## Print Formats

- Print lives in its own module. App-owned Print Formats and `Print Log` belong to
  `Connect Diagnostics Print` under `connect_diagnostics_core/connect_diagnostics_print/`.
  There is no per-Customer print configuration: print options are chosen per print in the
  print sidebar (see **Print sidebar engine**), with static registry defaults only.
- Print Formats are app-owned and editable through Desk (`standard = "No"`): `after_sync` and
  `after_migrate` remove every
  `Print Format` whose module is not one of the app modules (`Connect Diagnostics Core`,
  `Connect Diagnostics Stock`, `Connect Diagnostics Accounting`, or `Connect Diagnostics
Print`) or an ERPNext Thailand module (`Thai Tax`, `Thai Billing`, `Thai Deposit`, or
  `Petty Cash`). Retired formats are removed explicitly; `Sales Invoice Print` is retired and
  Sales Invoice defaults to `Tax Invoice Delivery Note and Invoice`. `Withholding Tax Cert` is
  owned by ERPNext Thailand; the app-owned Thai WHT certificate is the separately named
  `Withholding Tax Cert CD`, so the two coexist and neither overwrites the other. Do not add a
  Print Format fixture that restores records from other modules.
- The `css` field is appended verbatim; only `html` is rendered through Jinja. A `{{ ... }}`
  left in `css` is emitted literally and silently breaks whatever it built, so asset paths in
  `css` must be relative (`/assets/...`), never built with `frappe.utils.get_url()`.
- Dates in print formats come from the shared `format_date` Jinja method, which renders
  DD-MM-YYYY in the **Buddhist era**. The `+ 543` conversion lives only in
  `connect_diagnostics_core/utils/date.py`; a template must never convert the era itself.
- Print Format Jinja must be ordered as comment, derived variables, pagination, then HTML.
  Use a namespaced root class, scope CSS beneath that root, keep CSS out of the HTML field,
  and prefer semantic `header`, `section`, `table`, and `footer` elements. Use physical
  dimensions in `mm`; app-owned Print Formats must not use a background image, except formats
  that overlay an official government form scan — `Withholding Tax Cert CD` positions its fields
  over the Revenue Department form image from `erpnext_thailand`, so the background-image and
  semantic-sectioning rules do not apply to it. `Shipment Box
Label` is a 180 × 100 mm landscape Shipment format that uses `cd_logo_v2.jpg`, splits sender
  and recipient details, and shows the recipient Customer's Territory only when present.
- When modifying an app-owned Print Format JSON, update its `modified` timestamp to the current
  time. Frappe imports a standard record only when the source is newer, so an unchanged timestamp
  leaves the deployed format stale after `bench migrate`. The Sales Invoice format also has an
  explicit `sync_sales_invoice_print_format` migration so sites that already ran an earlier
  configuration migration receive the current HTML/CSS.
- Use the registered `format_money(amount, blank_zero=False)` Jinja helper for plain numeric
  amounts. Keep `print_currency` where a template intentionally renders a currency-aware value;
  do not define local money-formatting macros in Print Formats.

## Print sidebar engine

- App-specific print sidebar controls go through a client-side engine, not one-off
  `PrintView` overrides. `page_js = {"print": [...]}` in `hooks.py` loads, in order,
  `public/js/custom/print/engine.js` then each provider under
  `public/js/custom/print/providers/`. `page_js` values are concatenated raw (no bundler,
  `frappe/desk/form/meta.py: get_code_files_via_hooks`), so the engine must be listed first;
  it exposes `connect_diagnostics.print.register(provider)` (idempotent by `name`).
- The engine overrides `PrintView.setup_additional_settings`. When at least one provider's
  `applies_to(view)` is true it **takes over** the dynamic sidebar section: hides the Letter
  Head selector (button only — the default letterhead still applies), skips Frappe's native
  `get_print_settings` controls, and renders the applicable providers. When **no** provider
  applies it restores the Letter Head selector and delegates to Frappe's original
  `setup_additional_settings`, so unrelated doctypes keep the native sidebar untouched. This
  scoping is deliberate — do not make the stripping global.
- A provider is `{ name, applies_to(view), load?(view)→Promise, build?(view,data)→[df],
render?(view,data), on_error?(view,reason), section_label?, prefix? }`. Declarative providers
  return field descriptors (engine renders + wires them via `cd_add_setting`); imperative
  providers own their DOM. Value transport stays Frappe's own (`additional_settings` →
  `print_settings`), shared by preview and print/PDF.
- Current providers: `print_options.js` — registry-driven Print Options (async `load` of
  `print_configuration.get_print_options`, which returns the static field list + registry
  defaults for a document with **no** per-Customer resolution; `cd_` prefix; Reset restores
  the defaults), gated to the registry doctypes (`Quotation`, `Sales Order`, `Sales Invoice`,
  `Payment Entry`, mirroring `setup/print_documents.py`). The sidebar values flow into
  `print_settings` and the server print context reads them back via
  `print_configuration.get_document_print_context`. Add a new sidebar setting by writing a
  provider file and listing it in `page_js` — do not add branches to the engine.

## Print Audit Log

- Every real print and every PDF download is recorded as a `Print Log` row. Rows are
  insert-only: no role has write or delete permission, the DocType is `in_create`, and
  there is no auto-purge — retention is a legal concern, not housekeeping.
- The two channels are hooked differently because Frappe exposes them differently.
  PDF goes through `/api/method/frappe.utils.print_format.download_pdf`, so
  `override_whitelisted_methods` wraps it and the client cannot skip it; the wrapper must
  keep the original signature **and** `allow_guest=True`. The Print button loads the
  `/printview` route instead and cannot be overridden, so it is detected server-side from
  `frappe.form_dict.trigger_print` while the template renders.
- Coverage is not mandated for every app-owned Print Format. Configuration-driven formats
  record themselves through the print context; others may opt in with an explicit
  `{{ register_print(doc) }}` call. When present, that call must sit **outside** any leading
  `{# ... #}` comment, or it is silently swallowed.
- Previews are deliberately not recorded, and neither are emailed PDFs.
- **Two deliberate deviations from the general rules, both required by the feature.** A print
  render is a GET that Frappe does not commit, so the insert calls `frappe.db.commit()` inside
  a read request; enqueuing was rejected because an audit trail must not disappear when
  workers are down. And logging is fail-open: failures go to `frappe.log_error` with full
  context and never block printing. Do not "fix" either without changing this rule first.
