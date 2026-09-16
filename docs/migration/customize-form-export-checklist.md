# Customize Form export checklist

> Historical inventory: the authoritative current contract is
> [Item Request and Asset Fulfillment v11](../../.github/tasks/item-request-v11/spec.md).
> Its configuration/export list supersedes the old restrictions and completion checkboxes below.
> In particular, v11 authorizes the Stock Settings shelf-life field and uses Asset
> Capitalization for Demo provisioning at or above the threshold. The user approved native server-side Customize Form/Export on DEV, with a
> native Custom Field controller exception only for Single DocType Stock Settings. Desk and
> clean-site verification remain required; this historical checklist is not freeze evidence.

This is the handoff for the clean greenfield Stock reset plus the approved Item
Request Asset fulfillment design. The old Loan, Demo, Dispatch, and Equipment design
must not be rebuilt.

## v11 app-owned DocTypes

The complete app-owned Item Request set is: Requestable Item, Fulfillment Site, Item
Request, Item Request Item, Item Request Fulfillment Plan, Item Request Fulfillment,
Item Request Obligation, Item Request Active Lock, Item Request Operation, Item Request
Delivery Receipt, Item Request Return, Item Request Return Match, Item Request Unit
Return Inspection, Item Request Return Resolution, Item Request Asset Provisioning, and
its provisioning unit child. Equipment Type, Tracked Equipment, Equipment Intake,
Equipment Movement, Equipment Repair, and every other equipment DocType are removed and
must not be recreated.

## Item Request Flow integration exports (only allowed Custom Fields)

These are exported from Customize Form, stored in the app custom directory, and
must keep `sync_on_migrate: 1`:

| Done | DocType | Fieldname | Label |
| --- | --- | --- | --- |
| [x] | Company | `custom_default_asset_transit_location` | Default Asset Transit Location |
| [x] | Stock Entry | `custom_item_request` | Item Request |
| [x] | Stock Entry | `custom_item_request_phase` | Item Request Phase |
| [x] | Stock Entry | `custom_is_system_generated` | System Generated |
| [x] | Stock Entry Detail | `custom_item_request_item` | Item Request Item |
| [x] | Asset Movement | `custom_item_request` | Item Request |
| [x] | Asset Movement | `custom_item_request_phase` | Item Request Phase |
| [x] | Asset Movement | `custom_is_system_generated` | System Generated |
| [x] | Asset Movement Item | `custom_item_request_item` | Item Request Item |
| [x] | Asset | `custom_item_request` | Item Request |
| [x] | Asset | `custom_item_request_phase` | Item Request Phase |
| [x] | Asset | `custom_is_system_generated` | System Generated |
| [x] | Asset Capitalization | `custom_item_request` | Item Request |
| [x] | Asset Capitalization | `custom_item_request_phase` | Item Request Phase |
| [x] | Asset Capitalization | `custom_is_system_generated` | System Generated |
| [x] | Asset Capitalization Stock Item | `custom_item_request_item` | Item Request Item |
| [x] | Shipment | `custom_item_request` | Item Request |
| [x] | Shipment | `custom_reference_doctype` | Outbound Document Type |
| [x] | Shipment | `custom_reference_name` | Outbound Document |
| [x] | Shipment | `custom_receipt_method` | Receipt Method |
| [x] | Shipment | `custom_received_employee` | Received Employee |
| [x] | Shipment | `custom_received_by_user` | Received By User |
| [x] | Shipment | `custom_received_at` | Received At |
| [x] | Shipment | `custom_receiver_signature` | Receiver Signature |
| [x] | Shipment | `custom_receipt_override_reason` | Receipt Override Reason |

The table above is abbreviated for labels; the complete approved lineage export uses
these approved fieldnames (`custom_*`); rows explicitly marked pending are required
but not yet present in the current app exports:

| DocType(s) | Complete lineage fieldnames |
|---|---|
| Stock Entry, Asset Movement, Asset Repair, Sales Invoice | `custom_item_request`, `custom_item_request_plan`, `custom_item_request_fulfillment`, `custom_item_request_return`, `custom_item_request_return_match`, `custom_item_request_resolution`, `custom_item_request_operation`, `custom_item_request_shipment`, `custom_item_request_phase`, `custom_item_request_sequence`, `custom_item_request_voucher_key`, `custom_is_system_generated` |
| Stock Entry Detail, Asset Movement Item, Asset Capitalization Stock Item | `custom_item_request`, `custom_item_request_plan`, `custom_item_request_fulfillment`, `custom_item_request_item`, `custom_item_request_return`, `custom_item_request_return_match`, `custom_item_request_resolution`, `custom_item_request_operation`, `custom_item_request_shipment`, `custom_item_request_phase`, `custom_item_request_sequence`, `custom_item_request_voucher_key`, `custom_is_system_generated` |
| Asset | `custom_item_request`, `custom_item_request_phase`, `custom_is_system_generated` |
| Quality Inspection | `custom_item_request`, `custom_item_request_plan`, `custom_item_request_fulfillment`, `custom_item_request_return`, `custom_item_request_return_match`, `custom_item_request_resolution`, `custom_item_request_operation`, `custom_item_request_shipment`, `custom_item_request_phase`, `custom_item_request_sequence`, `custom_item_request_voucher_key`, `custom_is_system_generated` |
| Sales Invoice Item | `custom_item_request`, `custom_item_request_plan`, `custom_item_request_fulfillment`, `custom_item_request_return`, `custom_item_request_return_match`, `custom_item_request_resolution`, `custom_item_request_operation`, `custom_item_request_shipment`, `custom_item_request_phase`, `custom_item_request_sequence`, `custom_item_request_voucher_key`, `custom_is_system_generated` |
| Shipment | `custom_item_request`, `custom_item_request_plan`, `custom_item_request_fulfillment`, `custom_item_request_return`, `custom_item_request_return_match`, `custom_item_request_resolution`, `custom_item_request_operation`, `custom_item_request_shipment`, `custom_item_request_phase`, `custom_item_request_sequence`, `custom_item_request_voucher_key`, `custom_is_system_generated`, `custom_pickup_employee`, `custom_delivery_employee`, `custom_receipt_method`, `custom_received_employee`, `custom_received_by_user`, `custom_received_at`, `custom_receiver_signature`, `custom_receipt_override_reason`, `custom_reference_doctype`, `custom_reference_name` |
| Stock Settings | `custom_minimum_remaining_shelf_life_days` |
| Company (required v11 additions; implementation/export pending) | `custom_demo_source_site`, `custom_demo_low_value_asset_expense_account` |
| Company (existing approved exports) | `custom_default_asset_transit_location`, `custom_default_return_transit_warehouse`, `custom_external_custody_parent_warehouse`, `custom_qa_hold_location`, `custom_qa_hold_warehouse`, `custom_repair_location`, `custom_repair_warehouse`, `custom_replacement_exchange_clearing_account` |

Asset Capitalization itself uses `custom_item_request`, `custom_item_request_phase`,
and `custom_is_system_generated`; its child Stock Item uses the complete child list
above. The two Demo Company fields are required but not yet present in the current
export; implementation/export is a pending task. No field or setter outside this
inventory is part of v11.

### Provisioning export contract (v11)

The native Customize Form exports for Asset, Asset Capitalization, and Asset
Capitalization Stock Item are synchronized with `sync_on_migrate: 1` and retain
their `custom_fields`, `custom_perms`, `links`, and `property_setters` sections.
Asset and Asset Capitalization carry durable request/plan/provisioning/unit,
operation, phase, sequence, voucher-key, and system-generated lineage. The
Asset Capitalization Stock Item export carries the complete child lineage:
request, plan, fulfillment, request item, provisioning, provisioning unit,
return, return match, resolution, operation, shipment, phase, sequence,
voucher-key, and system-generated marker. All are hidden, read-only, no-copy
system fields and are populated only by the protected provisioning coordinator.

The provisioning parent is a non-submittable, operation-owned audit record with
strict `Prepared → Submitted → Reversed` transitions, THB 10,000 fixed
per-unit threshold, immutable snapshots, and an active key until reversal.
Each unit has exactly one mutually exclusive low-value or high-value native
path; submitted units require the native source/Asset/initial receipt lineage
for that path, and all reversal metadata remains immutable and auditable.

The Stock Entry and Asset Movement exports preserve existing Quality Manager
permissions and add equal Stock User/Stock Manager permissions plus read-only
Approver access. Asset Capitalization and Shipment add the same operational
roles and read-only Approver access. No existing role row is removed.

Source/Target Warehouse on Item Request are server-derived execution snapshots.
They are not requester fields and cannot be selected or overridden by Stock User;
automatic Demo routing selects Asset first and provisions Stock to Asset when required.

Shipment Pickup is resolved from the Source Warehouse Address, falling back to
the Company Address. If neither address is configured, Warehouse completes
Pickup on the Shipment. There is no Dispatch Address field on Item Request;
the requester enters the Delivery Address only. Warehouse enters the delivery
Customer and Contact on the Shipment before Submit.

## Reset baseline

- [x] Standard ERPNext Stock is the source of truth.
- [x] App-owned Item Request DocTypes are listed in the v11 inventory above;
  native Stock/Asset DocTypes remain ERPNext-owned.
- [x] Old Loan/Borrowed/Dispatch/Stock Count fields, hooks, workflows,
  reports, print formats, Equipment records, and APIs are removed.
- [x] Stock-related setup generators are inactive; new standard-DocType
  fields must not be added to `setup/*.py`.
- [x] No migration, rollback, or data-cleanup patch is required for this
  unused DEV reset.

## Do not create these customizations

| Area | Required decision |
| --- | --- |
| Material Request, Stock Entry, Delivery Note, Purchase Receipt, Asset, Quality Inspection, and Stock Settings | Keep standard ERPNext fields and behavior. Do not recreate retired Loan, Borrowed, Dispatch, or Stock Count fields. Stock Settings may receive only the approved minimum shelf-life field. |
| Asset Capitalization | Keep the native DocType and use only the approved Item Request lineage exports listed above for automatic Demo provisioning at or above the threshold. |
| Company and Employee | Do not add borrow-warehouse, loan-owner, or other fields from the retired flow. |
| Department and Territory | Do not add custom fields. Let ERPNext manage them as Accounting Dimensions. |
| Item Request and Item Request Item | These are app-owned DocTypes. Design their schema in the DocType JSON/controller; do not duplicate their fields through Customize Form. |

## Doctype and field inventory

The former Standard DocType customization list was retired completely. Those
fields are not part of the clean baseline, must not be recreated in
**Customize Form**, and must not be exported into this app. There are no active
Customize Form rows for that retired list.

### Retired Standard DocTypes

The 50 fields that were previously listed here have been deleted from the
site and from this app's export fixtures. This section is retained only as a
decision record; do not create any of those fields again.

### Excluded: fields owned by installed apps

Do not create these `custom_*` fields in `connect_diagnostics_core`.
Use the existing fieldname from the provider shown below.

| DocType | Removed fieldname | Label | Provider | Existing fieldname |
| --- | --- | --- | --- | --- |
| Account | `custom_is_petty_cash_account` | Is Petty Cash Account | erpnext_thailand | `is_petty_cash_account` |
| Customer | `custom_branch_code` | Branch Code | erpnext_thailand | `branch_code` |
| Employee | `custom_approvers_section` | Approvers | hrms | `approvers_section` |
| Employee | `custom_column_break_45` | — (layout only; blank label) | hrms | `column_break_45` |
| Employee | `custom_default_shift` | Default Shift | hrms | `default_shift` |
| Employee | `custom_employment_type` | Employment Type | hrms | `employment_type` |
| Employee | `custom_expense_approver` | Expense Approver | hrms | `expense_approver` |
| Employee | `custom_grade` | Grade | hrms | `grade` |
| Employee | `custom_health_insurance_no` | Health Insurance No | hrms | `health_insurance_no` |
| Employee | `custom_health_insurance_provider` | Health Insurance Provider | hrms | `health_insurance_provider` |
| Employee | `custom_health_insurance_section` | Health Insurance | hrms | `health_insurance_section` |
| Employee | `custom_job_applicant` | Job Applicant | hrms | `job_applicant` |
| Employee | `custom_leave_approver` | Leave Approver | hrms | `leave_approver` |
| Employee | `custom_payroll_cost_center` | Payroll Cost Center | hrms | `payroll_cost_center` |
| Employee | `custom_salary_cb` | — (layout only; blank label) | hrms | `salary_cb` |
| Employee | `custom_shift_request_approver` | Shift Request Approver | hrms | `shift_request_approver` |
| Item | `custom_is_deposit_item` | Is Deposit Item | erpnext_thailand | `is_deposit_item` |
| Item | `custom_section_break_6buh1` | Thai Tax | erpnext_thailand | `section_break_6buh1` |
| Item | `custom_withholding_tax_type` | Withholding Tax Type (Customer) | erpnext_thailand | `withholding_tax_type` |
| Item | `custom_column_break_lhwzh` | — (layout only; blank label) | erpnext_thailand | `column_break_lhwzh` |
| Item | `custom_withholding_tax_type_pay_supplier` | Withholding Tax Type (Supplier) | erpnext_thailand | `withholding_tax_type_pay_supplier` |
| Item | `custom_withholding_tax_type_pay_individual` | Withholding Tax Type (Individual) | erpnext_thailand | `withholding_tax_type_pay_individual` |
| Item Default | `custom_column_break_deposit_account` | — (layout only; blank label) | erpnext_thailand | `column_break_deposit_account` |
| Item Default | `custom_deposit_defaults` | Deposit Defaults | erpnext_thailand | `deposit_defaults` |
| Item Default | `custom_purchase_deposit_account` | Purchase Deposit Account | erpnext_thailand | `purchase_deposit_account` |
| Item Default | `custom_sales_deposit_account` | Sales Deposit Account | erpnext_thailand | `sales_deposit_account` |
| Journal Entry Account | `custom_column_break_cun7x` | — (layout only; blank label) | erpnext_thailand | `column_break_cun7x` |
| Journal Entry Account | `custom_customer` | Customer | erpnext_thailand | `customer` |
| Journal Entry Account | `custom_is_petty_cash_account` | Is Petty Cash Account | erpnext_thailand | `is_petty_cash_account` |
| Journal Entry Account | `custom_overwrite_tax_invoice` | Overwrite Tax Invoice | erpnext_thailand | `overwrite_tax_invoice` |
| Journal Entry Account | `custom_petty_cash_holder` | Petty Cash Holder | erpnext_thailand | `petty_cash_holder` |
| Journal Entry Account | `custom_petty_cash_holder_name` | Petty Cash Holder Name | erpnext_thailand | `petty_cash_holder_name` |
| Journal Entry Account | `custom_supplier` | Supplier | erpnext_thailand | `supplier` |
| Journal Entry Account | `custom_tax_base_amount` | Tax Base Amount | erpnext_thailand | `tax_base_amount` |
| Journal Entry Account | `custom_tax_invoice_date` | Tax Invoice Date | erpnext_thailand | `tax_invoice_date` |
| Journal Entry Account | `custom_tax_invoice_number` | Tax Invoice Number | erpnext_thailand | `tax_invoice_number` |
| Purchase Invoice | `custom_column_break_t0qgt` | — (layout only; blank label) | erpnext_thailand | `column_break_t0qgt` |
| Purchase Invoice | `custom_deposit_deductions` | Deposit Deductions | erpnext_thailand | `deposit_deductions` |
| Purchase Invoice | `custom_deposits` | Deposits | erpnext_thailand | `deposits` |
| Purchase Invoice | `custom_is_deposit_invoice` | Is Deposit Invoice | erpnext_thailand | `is_deposit_invoice` |
| Purchase Invoice | `custom_manual_deposit_allocation` | Manual Deposit Allocation | erpnext_thailand | `manual_deposit_allocation` |
| Purchase Invoice | `custom_section_break_split_tax_invoice` | — (layout only; blank label) | erpnext_thailand | `section_break_split_tax_invoice` |
| Purchase Invoice | `custom_section_break_tax_invoice` | — (layout only; blank label) | erpnext_thailand | `section_break_tax_invoice` |
| Purchase Invoice | `custom_split_tax_invoice` | Split Tax Invoices | erpnext_thailand | `split_tax_invoice` |
| Purchase Invoice | `custom_splitted_tax_invoices` | Splitted Tax Invoices | erpnext_thailand | `splitted_tax_invoices` |
| Purchase Invoice | `custom_tax_invoice` | Tax Invoice | erpnext_thailand | `tax_invoice` |
| Purchase Invoice | `custom_tax_invoice_date` | Tax Invoice Date | erpnext_thailand | `tax_invoice_date` |
| Purchase Invoice | `custom_tax_invoice_number` | Tax Invoice Number | erpnext_thailand | `tax_invoice_number` |
| Purchase Invoice | `custom_use_untied_deposit` | Include Untied Deposits | erpnext_thailand | `use_untied_deposit` |
| Purchase Invoice Item | `custom_is_deposit_item` | Is Deposit Item | erpnext_thailand | `is_deposit_item` |
| Purchase Invoice Item | `custom_withholding_tax_type` | Withholding Tax Type | erpnext_thailand | `withholding_tax_type` |
| Sales Invoice | `custom_column_break_cijbv` | — (layout only; blank label) | erpnext_thailand | `column_break_cijbv` |
| Sales Invoice | `custom_deposit_deductions` | Deposit Deductions | erpnext_thailand | `deposit_deductions` |
| Sales Invoice | `custom_deposits` | Deposits | erpnext_thailand | `deposits` |
| Sales Invoice | `custom_is_deposit_invoice` | Is Deposit Invoice | erpnext_thailand | `is_deposit_invoice` |
| Sales Invoice | `custom_manual_deposit_allocation` | Manual Deposit Allocation | erpnext_thailand | `manual_deposit_allocation` |
| Sales Invoice | `custom_tax_invoice` | Tax Invoice | erpnext_thailand | `tax_invoice` |
| Sales Invoice | `custom_tax_invoice_date` | Tax Invoice Date | erpnext_thailand | `tax_invoice_date` |
| Sales Invoice | `custom_tax_invoice_number` | Tax Invoice Number | erpnext_thailand | `tax_invoice_number` |
| Sales Invoice | `custom_use_untied_deposit` | Include Untied Deposits | erpnext_thailand | `use_untied_deposit` |
| Sales Invoice Item | `custom_is_deposit_item` | Is Deposit Item | erpnext_thailand | `is_deposit_item` |
| Sales Invoice Item | `custom_withholding_tax_type` | Withholding Tax Type | erpnext_thailand | `withholding_tax_type` |
| Supplier | `custom_branch_code` | Branch Code | erpnext_thailand | `branch_code` |

### Retired print-action and regulatory snapshot fields

All print-action and medical-device regulatory snapshot Custom Fields were
removed from this clean reset. Do not create them in Customize Form and do not
export them into this app. The old inventory is retained below only as a
non-operative history record.

<!--

| Done | DocType | Fieldname | Label |
| --- | --- | --- | --- |
| [ ] | Sales Invoice | `custom_submit_by` | Print Action: Submit By |
| [ ] | Sales Invoice | `custom_submit_at` | Print Action: Submit At |
| [ ] | Sales Invoice | `custom_submit_signature` | Print Action: Submit Signature |
| [ ] | Sales Invoice | `custom_received_by` | Print Action: Received By |
| [ ] | Sales Invoice | `custom_received_at` | Print Action: Received At |
| [ ] | Sales Invoice | `custom_received_signature` | Print Action: Received Signature |
| [ ] | Sales Invoice | `custom_delivered_by` | Print Action: Delivered By |
| [ ] | Sales Invoice | `custom_delivered_at` | Print Action: Delivered At |
| [ ] | Sales Invoice | `custom_delivered_signature` | Print Action: Delivered Signature |
| [ ] | Sales Invoice | `custom_authorized_by` | Print Action: Authorized By |
| [ ] | Sales Invoice | `custom_authorized_at` | Print Action: Authorized At |
| [ ] | Sales Invoice | `custom_authorized_signature` | Print Action: Authorized Signature |
| [ ] | Sales Invoice | `custom_checked_by` | Print Action: Checked By |
| [ ] | Sales Invoice | `custom_checked_at` | Print Action: Checked At |
| [ ] | Sales Invoice | `custom_checked_signature` | Print Action: Checked Signature |
| [ ] | Sales Invoice | `custom_return_received_by` | Print Action: Return Received By |
| [ ] | Sales Invoice | `custom_return_received_at` | Print Action: Return Received At |
| [ ] | Sales Invoice | `custom_return_received_signature` | Print Action: Return Received Signature |
| [ ] | Sales Invoice | `custom_warehouse_checked_by` | Print Action: Warehouse Checked By |
| [ ] | Sales Invoice | `custom_warehouse_checked_at` | Print Action: Warehouse Checked At |
| [ ] | Sales Invoice | `custom_warehouse_checked_signature` | Print Action: Warehouse Checked Signature |
| [ ] | Payment Entry | `custom_submit_by` | Print Action: Submit By |
| [ ] | Payment Entry | `custom_submit_at` | Print Action: Submit At |
| [ ] | Payment Entry | `custom_submit_signature` | Print Action: Submit Signature |
| [ ] | Payment Entry | `custom_received_by` | Print Action: Received By |
| [ ] | Payment Entry | `custom_received_at` | Print Action: Received At |
| [ ] | Payment Entry | `custom_received_signature` | Print Action: Received Signature |
| [ ] | Payment Entry | `custom_delivered_by` | Print Action: Delivered By |
| [ ] | Payment Entry | `custom_delivered_at` | Print Action: Delivered At |
| [ ] | Payment Entry | `custom_delivered_signature` | Print Action: Delivered Signature |
| [ ] | Payment Entry | `custom_authorized_by` | Print Action: Authorized By |
| [ ] | Payment Entry | `custom_authorized_at` | Print Action: Authorized At |
| [ ] | Payment Entry | `custom_authorized_signature` | Print Action: Authorized Signature |
| [ ] | Payment Entry | `custom_checked_by` | Print Action: Checked By |
| [ ] | Payment Entry | `custom_checked_at` | Print Action: Checked At |
| [ ] | Payment Entry | `custom_checked_signature` | Print Action: Checked Signature |
| [ ] | Sales Order | `custom_submit_by` | Print Action: Submit By |
| [ ] | Sales Order | `custom_submit_at` | Print Action: Submit At |
| [ ] | Sales Order | `custom_submit_signature` | Print Action: Submit Signature |
| [ ] | Sales Order | `custom_prepared_by` | Print Action: Prepared By |
| [ ] | Sales Order | `custom_prepared_at` | Print Action: Prepared At |
| [ ] | Sales Order | `custom_prepared_signature` | Print Action: Prepared Signature |
| [ ] | Sales Order | `custom_checked_by` | Print Action: Checked By |
| [ ] | Sales Order | `custom_checked_at` | Print Action: Checked At |
| [ ] | Sales Order | `custom_checked_signature` | Print Action: Checked Signature |
| [ ] | Sales Order | `custom_authorized_by` | Print Action: Authorized By |
| [ ] | Sales Order | `custom_authorized_at` | Print Action: Authorized At |
| [ ] | Sales Order | `custom_authorized_signature` | Print Action: Authorized Signature |
| [ ] | Purchase Order | `custom_submit_by` | Print Action: Submit By |
| [ ] | Purchase Order | `custom_submit_at` | Print Action: Submit At |
| [ ] | Purchase Order | `custom_submit_signature` | Print Action: Submit Signature |
| [ ] | Purchase Order | `custom_ordered_by` | Print Action: Ordered By |
| [ ] | Purchase Order | `custom_ordered_at` | Print Action: Ordered At |
| [ ] | Purchase Order | `custom_ordered_signature` | Print Action: Ordered Signature |
| [ ] | Purchase Order | `custom_authorized_by` | Print Action: Authorized By |
| [ ] | Purchase Order | `custom_authorized_at` | Print Action: Authorized At |
| [ ] | Purchase Order | `custom_authorized_signature` | Print Action: Authorized Signature |
| [ ] | Quotation | `custom_signatory_by` | Print Action: Signatory By |
| [ ] | Quotation | `custom_signatory_at` | Print Action: Signatory At |
| [ ] | Quotation | `custom_signatory_signature` | Print Action: Signatory Signature |
| [ ] | Withholding Tax Cert | `custom_signed_by` | Print Action: Signed By |
| [ ] | Withholding Tax Cert | `custom_signed_at` | Print Action: Signed At |
| [ ] | Withholding Tax Cert | `custom_signed_signature` | Print Action: Signed Signature |

### Medical-device regulatory snapshot fields

These are separate from the retired Loan/Stock Count fields. Keep them only
if the Regulatory requirement remains approved.

| Done | DocType | Fieldname | Label |
| --- | --- | --- | --- |
| [ ] | Purchase Order | `custom_medical_device_regulatory_override` | Medical Device Regulatory Override |
| [ ] | Purchase Receipt | `custom_medical_device_regulatory_override` | Medical Device Regulatory Override |
| [ ] | Stock Entry | `custom_medical_device_regulatory_override` | Medical Device Regulatory Override |
| [ ] | Sales Order | `custom_medical_device_regulatory_override` | Medical Device Regulatory Override |
| [ ] | Delivery Note | `custom_medical_device_regulatory_override` | Medical Device Regulatory Override |
| [ ] | Sales Invoice | `custom_medical_device_regulatory_override` | Medical Device Regulatory Override |
| [ ] | Purchase Order Item | `custom_regulatory_snapshot_section` | Medical Device Regulatory Snapshot |
| [ ] | Purchase Order Item | `custom_regulatory_registration` | Registration |
| [ ] | Purchase Order Item | `custom_regulatory_newcode` | FDA NEWCODE |
| [ ] | Purchase Order Item | `custom_regulatory_identifier` | Identifier |
| [ ] | Purchase Order Item | `custom_regulatory_manufacturer` | Regulatory Manufacturer |
| [ ] | Purchase Order Item | `custom_regulatory_manufacturer_country` | Regulatory Manufacturer Country |
| [ ] | Purchase Order Item | `custom_regulatory_batch_no` | Regulatory Batch No. |
| [ ] | Purchase Order Item | `custom_regulatory_serial_no` | Regulatory Serial No. |
| [ ] | Purchase Order Item | `custom_regulatory_product_expiry_date` | Product Expiry Date |
| [ ] | Purchase Order Item | `custom_regulatory_reporting_uom` | Regulatory Reporting UOM |
| [ ] | Purchase Order Item | `custom_regulatory_reporting_qty` | Regulatory Reporting Quantity |
| [ ] | Purchase Order Item | `custom_regulatory_override` | Regulatory Override |
| [ ] | Purchase Receipt Item | `custom_regulatory_snapshot_section` | Medical Device Regulatory Snapshot |
| [ ] | Purchase Receipt Item | `custom_regulatory_registration` | Registration |
| [ ] | Purchase Receipt Item | `custom_regulatory_newcode` | FDA NEWCODE |
| [ ] | Purchase Receipt Item | `custom_regulatory_identifier` | Identifier |
| [ ] | Purchase Receipt Item | `custom_regulatory_manufacturer` | Regulatory Manufacturer |
| [ ] | Purchase Receipt Item | `custom_regulatory_manufacturer_country` | Regulatory Manufacturer Country |
| [ ] | Purchase Receipt Item | `custom_regulatory_batch_no` | Regulatory Batch No. |
| [ ] | Purchase Receipt Item | `custom_regulatory_serial_no` | Regulatory Serial No. |
| [ ] | Purchase Receipt Item | `custom_regulatory_product_expiry_date` | Product Expiry Date |
| [ ] | Purchase Receipt Item | `custom_regulatory_reporting_uom` | Regulatory Reporting UOM |
| [ ] | Purchase Receipt Item | `custom_regulatory_reporting_qty` | Regulatory Reporting Quantity |
| [ ] | Purchase Receipt Item | `custom_regulatory_override` | Regulatory Override |
| [ ] | Stock Entry Detail | `custom_regulatory_snapshot_section` | Medical Device Regulatory Snapshot |
| [ ] | Stock Entry Detail | `custom_regulatory_registration` | Registration |
| [ ] | Stock Entry Detail | `custom_regulatory_newcode` | FDA NEWCODE |
| [ ] | Stock Entry Detail | `custom_regulatory_identifier` | Identifier |
| [ ] | Stock Entry Detail | `custom_regulatory_manufacturer` | Regulatory Manufacturer |
| [ ] | Stock Entry Detail | `custom_regulatory_manufacturer_country` | Regulatory Manufacturer Country |
| [ ] | Stock Entry Detail | `custom_regulatory_batch_no` | Regulatory Batch No. |
| [ ] | Stock Entry Detail | `custom_regulatory_serial_no` | Regulatory Serial No. |
| [ ] | Stock Entry Detail | `custom_regulatory_product_expiry_date` | Product Expiry Date |
| [ ] | Stock Entry Detail | `custom_regulatory_reporting_uom` | Regulatory Reporting UOM |
| [ ] | Stock Entry Detail | `custom_regulatory_reporting_qty` | Regulatory Reporting Quantity |
| [ ] | Stock Entry Detail | `custom_regulatory_override` | Regulatory Override |
| [ ] | Sales Order Item | `custom_regulatory_snapshot_section` | Medical Device Regulatory Snapshot |
| [ ] | Sales Order Item | `custom_regulatory_registration` | Registration |
| [ ] | Sales Order Item | `custom_regulatory_newcode` | FDA NEWCODE |
| [ ] | Sales Order Item | `custom_regulatory_identifier` | Identifier |
| [ ] | Sales Order Item | `custom_regulatory_manufacturer` | Regulatory Manufacturer |
| [ ] | Sales Order Item | `custom_regulatory_manufacturer_country` | Regulatory Manufacturer Country |
| [ ] | Sales Order Item | `custom_regulatory_batch_no` | Regulatory Batch No. |
| [ ] | Sales Order Item | `custom_regulatory_serial_no` | Regulatory Serial No. |
| [ ] | Sales Order Item | `custom_regulatory_product_expiry_date` | Product Expiry Date |
| [ ] | Sales Order Item | `custom_regulatory_reporting_uom` | Regulatory Reporting UOM |
| [ ] | Sales Order Item | `custom_regulatory_reporting_qty` | Regulatory Reporting Quantity |
| [ ] | Sales Order Item | `custom_regulatory_override` | Regulatory Override |
| [ ] | Delivery Note Item | `custom_regulatory_snapshot_section` | Medical Device Regulatory Snapshot |
| [ ] | Delivery Note Item | `custom_regulatory_registration` | Registration |
| [ ] | Delivery Note Item | `custom_regulatory_newcode` | FDA NEWCODE |
| [ ] | Delivery Note Item | `custom_regulatory_identifier` | Identifier |
| [ ] | Delivery Note Item | `custom_regulatory_manufacturer` | Regulatory Manufacturer |
| [ ] | Delivery Note Item | `custom_regulatory_manufacturer_country` | Regulatory Manufacturer Country |
| [ ] | Delivery Note Item | `custom_regulatory_batch_no` | Regulatory Batch No. |
| [ ] | Delivery Note Item | `custom_regulatory_serial_no` | Regulatory Serial No. |
| [ ] | Delivery Note Item | `custom_regulatory_product_expiry_date` | Product Expiry Date |
| [ ] | Delivery Note Item | `custom_regulatory_reporting_uom` | Regulatory Reporting UOM |
| [ ] | Delivery Note Item | `custom_regulatory_reporting_qty` | Regulatory Reporting Quantity |
| [ ] | Delivery Note Item | `custom_regulatory_override` | Regulatory Override |
| [ ] | Sales Invoice Item | `custom_regulatory_snapshot_section` | Medical Device Regulatory Snapshot |
| [ ] | Sales Invoice Item | `custom_regulatory_registration` | Registration |
| [ ] | Sales Invoice Item | `custom_regulatory_newcode` | FDA NEWCODE |
| [ ] | Sales Invoice Item | `custom_regulatory_identifier` | Identifier |
| [ ] | Sales Invoice Item | `custom_regulatory_manufacturer` | Regulatory Manufacturer |
| [ ] | Sales Invoice Item | `custom_regulatory_manufacturer_country` | Regulatory Manufacturer Country |
| [ ] | Sales Invoice Item | `custom_regulatory_batch_no` | Regulatory Batch No. |
| [ ] | Sales Invoice Item | `custom_regulatory_serial_no` | Regulatory Serial No. |
| [ ] | Sales Invoice Item | `custom_regulatory_product_expiry_date` | Product Expiry Date |
| [ ] | Sales Invoice Item | `custom_regulatory_reporting_uom` | Regulatory Reporting UOM |
| [ ] | Sales Invoice Item | `custom_regulatory_reporting_qty` | Regulatory Reporting Quantity |
| [ ] | Sales Invoice Item | `custom_regulatory_override` | Regulatory Override |
-->

### UI property setters

The only permitted Property Setters are native Select `options` setters for
Shipment `pickup_from_type` and `delivery_to_type`, preserving native options and
appending Employee. Address/Contact visibility and mandatory behavior belongs to
the server/client Shipment adapter and must not be implemented with setters. No
other Property Setter (hidden, mandatory, default, depends-on, collapsible,
list-view, or print-format) may be added for this domain.
## Historical work notes

### 1. Item Request design (superseded by v11 record)

- [ ] Confirm the business purpose and lifecycle of `Item Request`.
- [ ] Define the parent/child relationship and the `Item Request Item` table.
- [ ] Decide which standard ERPNext transaction, if any, it creates or links
  to (for example, Material Request or Stock Entry).
- [ ] For every field, approve the fieldname, label, fieldtype, options,
  mandatory status, default, read-only rule, and placement.
- [x] Implement only the approved v11 design in the app-owned DocTypes listed above.
- [ ] Add controller logic and tests only after the new behavior is agreed.

Do not copy fields from the retired Loan/Dispatch implementation into this
design.

### 2. Add a field to a standard ERPNext DocType

Use this process only when the new requirement genuinely needs a field on a
standard ERPNext DocType:

- [ ] Record the target DocType and the business reason.
- [ ] Open **Customize Form** and select that DocType.
- [ ] Add the field through the UI with a `custom_` fieldname.
- [ ] Set the fieldtype, label, options, placement, mandatory/default rules,
  read-only rules, and permissions in the UI.
- [ ] Save and verify the form in Desk.
- [ ] Use **Actions → Export Customizations**.
- [ ] Select the intended app module as the export destination.
- [ ] Confirm the generated `custom/<doctype>.json` is under that module.
- [ ] Do not copy the same field into `setup/*.py`.
- [ ] Repeat this for every approved field in the inventory above.

### 3. Verify the export

- [ ] The exported fieldname starts with `custom_`.
- [ ] There is no duplicate field in the DocType JSON or another module.
- [ ] No `department` or `territory` custom field was exported.
- [ ] The export contains only the intended fields and property setters.
- [ ] Install/sync the app on a fresh DEV site and verify the form, list view,
  permissions, and document lifecycle.
- [ ] Run the relevant tests and review the diff before committing.

## Scope boundary

This checklist covers the Stock/Loan reset. Existing non-Stock domains such as
Regulatory, Accounting, Payroll, HR, Procurement, Sales, and DKSH remain
outside this reset. When one of those domains is migrated away from setup,
prepare its own approved field inventory and follow the same Customize Form
export process.
