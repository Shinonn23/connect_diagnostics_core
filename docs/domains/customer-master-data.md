# Customer Onboarding and Master Data

- A Customer's document name is its required manual `Customer Code`; do not restore
  the Customer naming series. The code can be corrected until the Customer has its
  first Quotation, Sales Order, Sales Invoice, or Delivery Note, after which a rename
  would rewrite documents that have already gone out.
- **There is no Customer onboarding workflow.** Sales saves a Customer and can raise
  an order against it in the same breath. The previous queue — Customer Request →
  duplicate verification by IT-UB → accounting activation, with the Customer
  `disabled` throughout — cost more than it caught and is retired along with the
  `Customer Duplicate Verifier` role. Do not reintroduce an activation state.
- Master data is surfaced where it is used, not before a sale can start:
  `sales_invoice.validate_tax_invoice_readiness` **warns** (`frappe.msgprint`, never
  `throw`) when a Sales Invoice is submitted while tax readiness fails — one active
  primary Billing Address whose Thai address, tax ID, and branch code match Customer.
  The warning names exactly what is missing but does not block the submit, and nothing
  blocks the order.
- Readiness is **calculated, never stored**. `customer.build_readiness_values` is the
  single place that decides what a Customer is missing; the invoice gate and the
  Customer form both read it live through `get_customer_readiness`. The four readiness
  Select fields, their summary, `customer_onboarding_state`, `correction_reason`, and
  the no-delivery controls were dropped with the workflow, together with the Address
  and Contact hooks that rewrote them on every save.
- There is no per-Customer print configuration. Print options — language, show date,
  Customer Print Name, and per-copy-type counts — are chosen per print in the print
  sidebar, with static registry defaults only; nothing is stored per Customer. The
  Quotation signatory type may still be overridden per print; Quotation validity and
  delivery wording are document fields only (see below), not sidebar overrides.
  `Print Configuration Template`, its two child tables, and the Customer "Print" tab
  were removed.
- `connect_diagnostics_core/setup/print_documents.py` is the single source of truth for
  which documents exist (Quotation, Tax Invoice, Abbreviated Tax Invoice, Receipt),
  their named copies, whether language is selectable, and whether Batch / Serial
  applies. The sidebar controls and the print context derive from it — adding a document
  type is a change there and nowhere else. The retired `invoice` and `delivery_note`
  configurations must not be reintroduced; no print format consumed them.
- Values resolve from two sources, the sidebar winning: registry defaults, then
  request-only `flags.print_settings` from the print sidebar (`cd_`-prefixed). There is
  no Customer or Template stage.
- The Print sidebar loads the active format's controls from
  `print_configuration.get_print_options` and sends them as request-only `settings`
  overrides, with a Reset to default action. Overrides affect preview, print, and PDF for
  that request only; they never save Customer or the source document.
- Quotation's sidebar adds `Signatory` (Sales Representative or Managing Director). A
  Managing Director selection requires `Manager Signatory`, populated only from the
  Company's `Quotation Authorized Signatories` table. Active Sales Managers without an
  Employee `Quotation E-Signature` remain visible as unavailable and cannot be printed.
- Sales Invoice prints the named copies Original, Customer Copy, Accounting Copy, and
  Sales Copy, plus a Batch / Serial visibility option. All four default to one page set
  each. Sales Invoice is Thai-only: the registry fixes its language and any row value
  is ignored. Named copies are available to every document, not only Sales Invoice.
- Sales Order is a registered print document like the others: its date is the per-document
  `show_date`, resolved live from the Customer and overridable per print request on
  `/app/print/Sales Order/<name>`. The retired `Customer.print_date` flag and the Sales
  Order format's direct read of it must not be reintroduced.
- The combined Sales Invoice format resolves Batch and Serial values from both
  direct item fields and `Serial and Batch Bundle`, renders one traceability
  line per record without ellipsis, then paginates whole item blocks before
  rendering. Each page repeats the invoice summary and resets the current-page /
  total-pages value within each selected copy set; only the final overall page
  omits the page break after it.
- Purchase Order keeps supplier and order header data in separate boxes, adds
  the company's Ship To address and supplier Contact, shows ETA from the
  standard `schedule_date` field plus Incoterm and Currency, and uses Item Code,
  Description, QTY, UOM, Unit Price, and Amount columns without warehouse or
  item-level discount columns.
- Quotation carries its own Sales Contact: `Quotation.sales_representative_employee` is
  the Employee who issues that offer, defaulted from the logged-in user. It prints in the
  contact block on every form. The signatory is either that Employee (Sales
  Representative) or a request-only Managing Director chosen from the Company's
  `quotation_authorized_signatories` table. Do not resolve either person from Customer
  Sales Team — Quotation has no `sales_team` table.
- The Company allow-list accepts only Active Employees in the same Company who have the
  `Sales Manager` role. The Employee's `quotation_signature` field is required at print
  time; missing signatures are shown as unavailable in the sidebar and block Print/PDF,
  while Preview remains usable for correcting settings. Duplicate rows are rejected.
- The caption under the signature line is a fixed literal per signatory type, held in
  `setup/quotation.py` as `SIGNATORY_CAPTIONS`; it is never `Employee.designation`.
- The Quotation carries its own `quotation_signatory_type` and
  `sales_representative_employee`, grouped in their own "Signatory" Section (see
  `setup/quotation.py`); Customer no longer stores any print or signatory defaults.
  `sales_representative_employee` is filtered in Desk by Role
  (`SIGNATORY_EMPLOYEE_ROLES`) via the `signatory_employee_query` Link query — a Desk convenience only, filtering the
  Sales Contact to Active Sales Users/Managers in the selected Company; it is not
  enforced at submit. Both fields live in their own standalone "Signatory" Tab (immediately
  after the Details tab), not a Section within Details. `print_documents.QUOTATION_EXTRA_FIELDS`
  now covers `quotation_signatory_type` and the request-only
  `manager_signatory_employee`; validity (`edit_validity_text` /
  `validity_text`) and delivery terms (`delivery_terms_template` /
  `quotation_delivery_terms`) are document-only fields, required before submit
  (`validate_signatory_before_submit` / `validate_delivery_terms_before_submit` in
  `api/erpnext/quotation.py`) and no longer overridable from the print sidebar.
  `validity_text` is always visible: read-only and kept in sync client-side with
  the computed "N days from Valid Till" text while `edit_validity_text` is
  unchecked (`read_only_depends_on`), and becomes free-text editable once checked
  — the Desk-side preview is Thai-only, distinct from `_validity_text()`'s
  tri-lingual print-time rendering, since language is a print-sidebar choice, not
  a stored document field. `edit_validity_text`/`validity_text` are renamed from
  `override_quotation_validity_text`/`quotation_custom_validity_text` by
  `patches/v1_0/rename_quotation_validity_fields.py`; do not reintroduce the old
  names. Delivery Terms picks from the reusable `Delivery Terms Template` DocType
  (a plain master, seeded with one default row by `quotation.ensure_configuration()`,
  living in its own Section at the top of the standard "Terms" tab alongside
  Payment Terms Template and Terms and Conditions) and stays editable afterward —
  it does not overlap with native Terms and Conditions (`doc.terms`/`tc_name`),
  which this app's Quotation format renders separately as free-form Remarks
  ("หมายเหตุ"), a different print section entirely.
- The single Quotation format renders Thai, English, or Thai / English and configured
  original/copy pages. `show_date` off and a custom validity text are ordinary
  configuration, not separate formats.
- `Customer Credit Request` is the only route to payment terms and a credit limit,
  for **every** Customer including `GOV. HOSPITAL`. It does not depend on a channel
  field. Customers start on whatever terms they are created with; `Customer.validate`
  still blocks anyone without the Customer Accounting Reviewer role from editing terms
  or limits directly.
- **Workflow: not currently defined by the app.** The custom Customer Credit Request
  approval workflow was retired in the custom-workflow reset, along with the
  `credit_request_state` field. Submitting a `Customer Credit Request` applies the
  requested payment terms and credit limit to the Customer under a row lock — that is
  the document's intrinsic effect, not a workflow outcome. Standard DocType permissions
  govern who may submit; the `Customer Accounting Reviewer` and `Customer Credit
Approver` roles are kept because they gate Customer read/write, not because of any
  workflow. A future approval flow starts from a Workflow Behavior Specification.
- Customer, Item, and Supplier keep their current document names and codes. Do not
  add conversion flags or automatically rename these masters. The DKSH reference codes
  `dksh_item_code`, `supplier_product_code`, `mat_group_code`, `mat_group4_code`, and
  `material_type_code` live on the standalone `DKSH Item` DocType (autonamed by
  `dksh_item_code`) with an **optional** `item` link — blank means a DKSH stand-alone
  product with no CD Item. They are optional reference data only, with no workflow and no
  roles of their own, and must not control Item lifecycle or transaction eligibility. The
  link surfaces on the Item form's Connections via `override_doctype_dashboards`
  (`api/erpnext/item.py`). `DKSH Item` and every other DKSH reference master live in the
  `Connect Diagnostics DKSH` module (see [dksh.md](dksh.md)), not in Core. The
  earlier design that grouped these as five Custom Fields on an Item DKSH tab, plus the Item
  list view and the stock-showing `get_item_with_stock` link query that searched them, were
  removed; do not reintroduce them.
- Sales Order uses the standard `item_code` grid and otherwise standard ERPNext
  behavior for every Company. Do not force a selling Price List, Skip Delivery Note,
  external order status, or Company-specific Item link query. The sales document
  requirement gate (see [sales-requirements.md](sales-requirements.md)) is the one
  deliberate exception and is driven by Customer data, not by Company.
