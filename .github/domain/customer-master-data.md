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
- Master data is required where it is used, not before a sale can start:
  `sales_invoice.validate_tax_invoice_readiness` blocks **submitting** a Sales Invoice
  until tax readiness passes — one active primary Billing Address whose Thai address,
  tax ID, and branch code match Customer. Nothing blocks the order.
- Readiness is **calculated, never stored**. `customer.build_readiness_values` is the
  single place that decides what a Customer is missing; the invoice gate and the
  Customer form both read it live through `get_customer_readiness`. The four readiness
  Select fields, their summary, `customer_onboarding_state`, `correction_reason`, and
  the no-delivery controls were dropped with the workflow, together with the Address
  and Contact hooks that rewrote them on every save.
- `Print Configuration Template` is shared print policy: a `Documents` table with one
  row per registered document, and a `Copies` table of named page sets. It holds no
  per-customer scalars. Every Customer linked to it follows those rows **live** —
  editing a Template changes what its Customers print immediately, with no fetch step.
- Customer `Document / Print Configuration` links one Template and carries only its
  own values: Customer Print Name, Quotation signatory type and Delivery Terms,
  and the source Purchase Order copy settings. Its `Documents` and `Copies` tables are
  overrides: no row means inherit the Template for that document; a row wins wholesale.
- `connect_diagnostics_core/setup/print_documents.py` is the single source of truth for
  which documents exist (Quotation, Tax Invoice, Abbreviated Tax Invoice, Receipt),
  their named copies, whether language is selectable, and whether Batch / Serial
  applies. Doctype rows, sidebar controls, and the print context all derive from it —
  adding a document type is a change there and nowhere else. The retired `invoice` and
  `delivery_note` configurations must not be reintroduced; no print format consumed them.
- Values resolve in four stages, later winning: registry defaults, Template rows,
  Customer scalars and override rows, then request-only `flags.print_settings`. A blank
  Customer text value inherits rather than blanking the resolved value. The resolver
  also reports the source of each value, which the Print sidebar shows under each
  control alongside a Reset to default action.
- The Print sidebar loads only the active format's controls and sends them as
  request-only `settings` overrides. Overrides affect preview, print, and PDF for that
  request only; they never save Customer or the source document. Missing fields during
  a code-before-migration rollout fall back to registry defaults.
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
- Quotation carries its own signatory: `Quotation.sales_representative_employee` is the
  Employee who issues that offer, defaulted from the logged-in user. It prints in the
  contact block on every form and signs the document when the signatory is a Sales
  Representative. Do not resolve the signatory from the Customer Sales Team — Quotation
  has no `sales_team` table, and the retired `Sales Person.employee` chain picked an
  arbitrary first row.
- The caption under the signature line is a fixed literal per signatory type, held in
  `setup/quotation.py` as `SIGNATORY_CAPTIONS`; it is never `Employee.designation`. A
  Managing Director quotation prints an **empty** name by design so the director signs
  and writes the name by hand, and therefore resolves no Employee at all. The retired
  `Company.quotation_authorized_signatory_employee` and its Quotation override must not
  be reintroduced.
- `override_quotation_validity_text` and `quotation_custom_validity_text` live on
  Quotation, not Customer: the wording describes one offer. Customer keeps only
  `quotation_signatory_type` and `quotation_delivery_terms`, copied as defaults to new
  Quotations. `print_documents.QUOTATION_CUSTOMER_FIELDS` is what Customer stores;
  `QUOTATION_EXTRA_FIELDS` is what the sidebar may override for one request.
- The single Quotation format renders Thai, English, or Thai / English and configured
  original/copy pages. `show_date` off and a custom validity text are ordinary
  configuration, not separate formats.
- `Customer Credit Request` is the only route to payment terms and a credit limit,
  for **every** Customer including `GOV. HOSPITAL`, and is approved by the Customer
  Credit Approver. It does not depend on a channel field. Customers start on whatever
  terms they are created with; `Customer.validate` still blocks anyone without the
  Customer Accounting Reviewer role from editing terms or limits directly.
- Customer Credit Request approval states and transitions belong to its Frappe
  Workflow. When that Workflow is inactive, submission bypasses approval and applies
  the requested credit terms and limit while retaining normal data validation.
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
