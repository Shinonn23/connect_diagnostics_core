# Regulatory module

- `Connect Diagnostics Regulatory` (in `modules.txt`, folder
  `connect_diagnostics_core/connect_diagnostics_regulatory/`) owns medical-device
  regulatory source-of-truth masters. Product Registration has the FDA registration
  number and effective Registered Product rows; Item retains only classification and
  read-only current coverage derived by `api/erpnext/regulatory.py`. Never duplicate
  FDA numbers, NEWCODE, expiry, or regulatory documents onto Item.
- Renewal and variation history belongs in `Medical Device Registration Action`; a
  replacement registration must link its predecessor/successor instead of overwriting
  the historic record. A verified Certificate is the initial activation requirement.
  Do not infer Thai FDA classifications, document requirements, or legal stock policy.
- `setup/regulatory.py` owns the Regulatory Viewer/Operator/Approver roles and
  permissions. **Workflow: not currently defined by the app** — the Product
  Registration approval workflow and its `regulatory_workflow_state` field were
  retired in the custom-workflow reset; the `official_status` field remains as a
  plain business status (no longer driven by workflow transitions), and a future
  approval flow starts from a Workflow Behavior Specification. `setup/workspace.py`
  maintains the independent Regulatory Workspace. Registered Product and Expiry Alert Rule are
  child tables and intentionally have no Desk route.
- `api/erpnext/regulatory_transactions.py` is the only transaction-policy boundary.
  It resolves regulatory coverage by the transaction date, keeps PO/SO non-blocking,
  and snapshots resolved master facts on each submitted row. Never derive a historical
  transaction from the Item's current fields. A Regulatory Override must be an approved,
  document-bound record; it bypasses a gate but is retained in the row snapshot.
- `api/erpnext/regulatory_alerts.py` owns daily expiry processing and weekly digests.
  It de-duplicates alerts by registration/document and threshold through the immutable
  Alert Log; recipient roles/users come from the alert rule, never Item rows. Regulatory
  Script Reports use the read-only `regulatory_reporting.py` helpers. Standard Frappe Data
  Import is enabled for masters; use the preflight API before writing a production import.
- On the Item form (`setup/item.py`), "Medical Device Regulatory" and "Current
  Regulatory Coverage" live in their own "Regulatory" tab and are gated by
  `depends_on: eval:doc.is_medical_device`; `Is Medical Device` itself sits in the
  Variants tab, right after `Has Variants`. `validate_item_classification` clears
  `medical_device_category`, `regulatory_owner`, and the four `current_*` coverage
  fields to blank whenever `is_medical_device` is unchecked — `regulatory_registration_requirement`
  keeps its existing "Not Applicable" enforcement rather than going blank. Opening
  Stock / Valuation Rate / Standard Selling Rate move into their own "Opening" tab via
  a dynamically computed `field_order` Property Setter (`item.ensure_configuration`,
  called from `setup.apply_all`) — Frappe only supports repositioning a _standard_
  field through that DocType-level mechanism, not per-field `insert_after`.
