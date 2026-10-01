app_name = "connect_diagnostics_core"
app_title = "Connect Diagnostics Core"
app_publisher = "Siwat Sroisuwan"
app_description = "Custom app for Connect Diagnostics to manage and implement company-specific business logic, workflows, and processes on ERPNext."
app_email = "siwat61719@gmail.com"
app_license = "bsl-1.0"

# Apps
# ------------------

required_apps = ["erpnext", "erpnext_thailand", "hrms"]

extend_doctype_class = {
    "Asset": ["connect_diagnostics_core.api.erpnext.asset_movement_workflow.AssetMovementNativeMixin"],
    "Asset Movement": [
        "connect_diagnostics_core.api.erpnext.asset_movement_workflow.AssetMovementWorkflowMixin"
    ],
}

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "connect_diagnostics_core",
# 		"logo": "/assets/connect_diagnostics_core/logo.png",
# 		"title": "Connect Diagnostics Core",
# 		"route": "/connect_diagnostics_core",
# 		"has_permission": "connect_diagnostics_core.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/connect_diagnostics_core/css/connect_diagnostics_core.css"
# app_include_js = "/assets/connect_diagnostics_core/js/connect_diagnostics_core.js"

# include js, css files in header of web template
# web_include_css = "/assets/connect_diagnostics_core/css/connect_diagnostics_core.css"
# web_include_js = "/assets/connect_diagnostics_core/js/connect_diagnostics_core.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "connect_diagnostics_core/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
page_js = {
    "print": [
        "public/js/custom/print/engine.js",
        "public/js/custom/print/providers/print_options.js",
    ]
}

# include js in doctype views
doctype_js = {
    "Address": "public/js/custom/address/doctype.js",
    "Company": "public/js/custom/company/doctype.js",
    "DKSH Customer": "public/js/custom/dksh_customer/doctype.js",
    "Delivery Note": "public/js/custom/delivery_note/doctype.js",
    "Material Request": "public/js/custom/material_request/doctype.js",
    "Payment Entry": "public/js/custom/payment_entry/doctype.js",
    "Purchase Order": "public/js/custom/purchase_order/doctype.js",
    "Quotation": "public/js/custom/quotation/doctype.js",
    "Sales Order": "public/js/custom/sales_order/doctype.js",
}
doctype_list_js = {
    "Customer": "public/js/custom/customer/list_view.js",
    "Sales Order": "public/js/custom/sales_order/list_view.js",
    "Supplier": "public/js/custom/supplier/list_view.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "connect_diagnostics_core/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
    "methods": [
        "connect_diagnostics_core.utils.thai_words.number_to_thai_currency",
        "connect_diagnostics_core.utils.currency.print_currency",
        "connect_diagnostics_core.utils.currency.format_money",
        "connect_diagnostics_core.utils.date.format_date",
        "connect_diagnostics_core.api.erpnext.print_configuration.get_document_print_context",
        "connect_diagnostics_core.api.erpnext.print_configuration.get_print_action_context",
        "connect_diagnostics_core.api.erpnext.print_pagination.get_print_item_pages",
        "connect_diagnostics_core.api.erpnext.print_pagination.get_print_page_metrics",
        "connect_diagnostics_core.api.erpnext.sales_invoice.get_sales_invoice_print_context",
        "connect_diagnostics_core.api.erpnext.quotation.get_quotation_print_context",
        "connect_diagnostics_core.api.erpnext.dispatch.get_dispatch_label_rows",
        "connect_diagnostics_core.utils.qr.get_qr_svg_code",
        "connect_diagnostics_core.api.frappe.print_log.register_print",
    ],
    # "filters": "connect_diagnostics_core.utils.jinja_filters"
}

# Native Workflow owns transition state. These registered tasks only capture
# revision-bound evidence or authorize the immediately following native effect.
_normalized_workflow_methods = {
    "Connect Stock Transfer Maker Snapshot": "connect_diagnostics_core.api.erpnext.stock_entry_workflow.capture_maker_snapshot",
    "Connect Stock Transfer Review Snapshot": "connect_diagnostics_core.api.erpnext.stock_entry_workflow.capture_review_snapshot",
    "Connect Stock Transfer Approval Snapshot": "connect_diagnostics_core.api.erpnext.stock_entry_workflow.capture_approval_snapshot",
    "Connect Stock Transfer Approval Reset": "connect_diagnostics_core.api.erpnext.stock_entry_workflow.reset_approval",
    "Connect Stock Transfer Submit Execution": "connect_diagnostics_core.api.erpnext.stock_entry_workflow.authorize_submit_execution",
    "Connect Stock Transfer Cancel Execution": "connect_diagnostics_core.api.erpnext.stock_entry_workflow.authorize_cancel_execution",
    "Connect Stock Reconciliation Capture Maker": "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.capture_maker",
    "Connect Stock Reconciliation Capture Review": "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.capture_review",
    "Connect Stock Reconciliation Capture Approval": "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.capture_approval",
    "Connect Stock Reconciliation Clear Approval": "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.clear_approval",
    "Connect Stock Reconciliation Submit Execution": "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.authorize_submit_execution",
    "Connect Stock Reconciliation Cancel Execution": "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.authorize_cancel_execution",
    "Connect Asset Movement Maker Snapshot": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.capture_maker",
    "Connect Asset Movement Review Snapshot": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.capture_review",
    "Connect Asset Movement Approval Snapshot": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.capture_approval",
    "Connect Asset Movement Approval Reset": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.reset_approval",
    "Connect Asset Movement Submit Authorization": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.authorize_submit_transition",
    "Connect Asset Movement Cancel Authorization": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.authorize_cancel_transition",
    "Connect Journal Entry Capture Maker": "connect_diagnostics_core.api.erpnext.journal_entry_workflow.capture_maker_snapshot",
    "Connect Journal Entry Capture Checker": "connect_diagnostics_core.api.erpnext.journal_entry_workflow.capture_checker_snapshot",
    "Connect Journal Entry Capture Approver": "connect_diagnostics_core.api.erpnext.journal_entry_workflow.capture_approver_snapshot",
    "Connect Journal Entry Clear Approval": "connect_diagnostics_core.api.erpnext.journal_entry_workflow.clear_approval_snapshots",
    "Connect Journal Entry Submit Execution": "connect_diagnostics_core.api.erpnext.journal_entry_workflow.authorize_submit_transition",
    "Connect Journal Entry Cancel Execution": "connect_diagnostics_core.api.erpnext.journal_entry_workflow.authorize_cancel_transition",
    "Connect Sales Order Capture Maker": "connect_diagnostics_core.api.erpnext.sales_order_workflow.capture_sales_order_maker",
    "Connect Sales Order Capture Review": "connect_diagnostics_core.api.erpnext.sales_order_workflow.capture_sales_order_review",
    "Connect Sales Order Capture Approval": "connect_diagnostics_core.api.erpnext.sales_order_workflow.capture_sales_order_final_approval",
    "Connect Sales Order Clear Approval": "connect_diagnostics_core.api.erpnext.sales_order_workflow.clear_sales_order_approval",
    "Connect Sales Order Submit Execution": "connect_diagnostics_core.api.erpnext.sales_order_workflow.authorize_sales_order_submission",
    "Connect Sales Order Cancel Execution": "connect_diagnostics_core.api.erpnext.sales_order_workflow.authorize_sales_order_cancellation",
    "Connect Sales Invoice Credit Send": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.capture_maker",
    "Connect Sales Invoice Credit Resubmit": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.capture_maker",
    "Connect Sales Invoice Credit Review": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.capture_review",
    "Connect Sales Invoice Credit Return": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.clear_on_return",
    "Connect Sales Invoice Credit Approve": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.capture_approval",
    "Connect Sales Invoice Credit Reject": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.clear_on_reject",
    "Connect Sales Invoice Credit Post": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.authorize_submit_transition",
    "Connect Purchase Order Maker": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.capture_maker_snapshot",
    "Connect Purchase Order Review": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.capture_review_snapshot",
    "Connect Purchase Order Approval": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.capture_authorization_snapshot",
    "Connect Purchase Order Approval Reset": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.clear_approval_snapshots",
    "Connect Purchase Order Submit": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.authorize_submit_execution",
    "Connect Purchase Order Cancel": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.authorize_cancel_execution",
    "Connect Purchase Invoice Maker": "connect_diagnostics_core.api.erpnext.purchase_invoice_workflow.capture_maker_snapshot",
    "Connect Purchase Invoice Source Verification": "connect_diagnostics_core.api.erpnext.purchase_invoice_workflow.capture_source_verification_snapshot",
    "Connect Purchase Invoice Accounting Approval": "connect_diagnostics_core.api.erpnext.purchase_invoice_workflow.capture_accounting_approval_snapshot",
    "Connect Purchase Invoice Approval Reset": "connect_diagnostics_core.api.erpnext.purchase_invoice_workflow.clear_approval_snapshots",
    "Connect Purchase Invoice Submit": "connect_diagnostics_core.api.erpnext.purchase_invoice_workflow.authorize_submit_execution",
    "Connect Purchase Invoice Cancel": "connect_diagnostics_core.api.erpnext.purchase_invoice_workflow.authorize_cancel_execution",
    "Connect Payment Entry Capture Maker": "connect_diagnostics_core.api.erpnext.payment_entry_workflow.capture_maker_snapshot",
    "Connect Payment Entry Capture Checker": "connect_diagnostics_core.api.erpnext.payment_entry_workflow.capture_checker_snapshot",
    "Connect Payment Entry Capture Approver": "connect_diagnostics_core.api.erpnext.payment_entry_workflow.capture_approver_snapshot",
    "Connect Payment Entry Clear Approval": "connect_diagnostics_core.api.erpnext.payment_entry_workflow.clear_approval_snapshots",
    "Connect Payment Entry Submit Execution": "connect_diagnostics_core.api.erpnext.payment_entry_workflow.authorize_submit_transition",
    "Connect Payment Entry Cancel Execution": "connect_diagnostics_core.api.erpnext.payment_entry_workflow.authorize_cancel_transition",
    "Connect Payroll Entry Capture Maker": "connect_diagnostics_core.api.hrms.payroll_entry_workflow.capture_maker_snapshot",
    "Connect Payroll Entry Capture Review": "connect_diagnostics_core.api.hrms.payroll_entry_workflow.capture_review_snapshot",
    "Connect Payroll Entry Capture Approval": "connect_diagnostics_core.api.hrms.payroll_entry_workflow.capture_authorization_snapshot",
    "Connect Payroll Entry Clear Approval": "connect_diagnostics_core.api.hrms.payroll_entry_workflow.clear_approval_snapshots",
    "Connect Payroll Entry Submit Execution": "connect_diagnostics_core.api.hrms.payroll_entry_workflow.authorize_submit_transition",
}

workflow_methods = [
    {"name": name, "method": method} for name, method in _normalized_workflow_methods.items()
] + [
    {
        "name": "Capture Asset Movement Maker",
        "method": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.capture_maker",
    },
    {
        "name": "Capture Asset Movement Review",
        "method": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.capture_review",
    },
    {
        "name": "Capture Asset Movement Approval",
        "method": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.capture_approval",
    },
    {
        "name": "Reset Asset Movement Approval",
        "method": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.reset_approval",
    },
    {
        "name": "Authorize Asset Movement Submit Transition",
        "method": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.authorize_submit_transition",
    },
    {
        "name": "Authorize Asset Movement Cancel Transition",
        "method": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.authorize_cancel_transition",
    },
    {
        "name": "Capture Sales Order Demo Maker",
        "method": "connect_diagnostics_core.api.erpnext.sales_order_workflow.capture_sales_order_demo_maker",
    },
    {
        "name": "Capture Sales Order Demo Review",
        "method": "connect_diagnostics_core.api.erpnext.sales_order_workflow.capture_sales_order_demo_review",
    },
    {
        "name": "Capture Sales Order Demo Final Approval",
        "method": "connect_diagnostics_core.api.erpnext.sales_order_workflow.capture_sales_order_demo_final_approval",
    },
    {
        "name": "Clear Sales Order Demo Approval",
        "method": "connect_diagnostics_core.api.erpnext.sales_order_workflow.clear_sales_order_demo_approval",
    },
    {
        "name": "Authorize Sales Order Demo Submission",
        "method": "connect_diagnostics_core.api.erpnext.sales_order_workflow.authorize_sales_order_demo_submission",
    },
    {
        "name": "Capture Freeze Exception Approval Scope",
        "method": "connect_diagnostics_core.api.erpnext.stock_entry_workflow.capture_freeze_exception_approval_scope",
    },
    {
        "name": "Authorize Freeze Exception Execution",
        "method": "connect_diagnostics_core.api.erpnext.stock_entry_workflow.authorize_freeze_exception_execution",
    },
    {
        "name": "Clear Purchase Order Approval Snapshots",
        "method": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.clear_approval_snapshots",
    },
    {
        "name": "Authorize Purchase Order Submit",
        "method": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.authorize_submit_execution",
    },
    {
        "name": "Authorize Purchase Order Cancel",
        "method": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.authorize_cancel_execution",
    },
    {
        "name": "Capture Print Action: Submit",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_submit_action",
    },
    {
        "name": "Capture Print Action: Received",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_received_action",
    },
    {
        "name": "Capture Print Action: Delivered",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_delivered_action",
    },
    {
        "name": "Capture Print Action: Prepared",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_prepared_action",
    },
    {
        "name": "Capture Print Action: Ordered",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_ordered_action",
    },
    {
        "name": "Capture Print Action: Checked",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_checked_action",
    },
    {
        "name": "Capture Print Action: Authorized",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_authorized_action",
    },
    {
        "name": "Capture Print Action: Return Received",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_return_received_action",
    },
    {
        "name": "Capture Print Action: Warehouse Checked",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_warehouse_checked_action",
    },
    {
        "name": "Capture Print Action: Signatory",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_signatory_action",
    },
    {
        "name": "Capture Print Action: Signed",
        "method": "connect_diagnostics_core.api.erpnext.print_actions.capture_signed_action",
    },
    {
        "name": "Validate Material Request: Submit for Approval",
        "method": "connect_diagnostics_core.api.erpnext.material_request.validate_submit_for_approval",
    },
    {
        "name": "Validate Material Request: Close",
        "method": "connect_diagnostics_core.api.erpnext.material_request.validate_close",
    },
    {
        "name": "Capture Sales Invoice Credit Maker",
        "method": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.capture_maker",
    },
    {
        "name": "Capture Sales Invoice Credit Review",
        "method": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.capture_review",
    },
    {
        "name": "Clear Sales Invoice Credit Return",
        "method": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.clear_on_return",
    },
    {
        "name": "Capture Sales Invoice Credit Approval",
        "method": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.capture_approval",
    },
    {
        "name": "Clear Sales Invoice Credit Reject",
        "method": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.clear_on_reject",
    },
    {
        "name": "Authorize Sales Invoice Credit Post",
        "method": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.authorize_submit_transition",
    },
    {
        "name": "Authorize Sales Invoice Credit Cancel",
        "method": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.authorize_cancel_transition",
    },
]

# Installation
# ------------

# before_install = "connect_diagnostics_core.install.before_install"
after_install = [
    "connect_diagnostics_core.setup.after_install",
    "connect_diagnostics_core.setup.employee.ensure_configuration",
    "connect_diagnostics_core.setup.print_action_fields.apply_configuration",
    "connect_diagnostics_core.setup.tds.apply_configuration",
]
after_sync = "connect_diagnostics_core.setup.after_sync"
before_migrate = "connect_diagnostics_core.setup.before_migrate"
after_migrate = [
    "connect_diagnostics_core.setup.after_migrate",
    "connect_diagnostics_core.setup.employee.ensure_configuration",
    "connect_diagnostics_core.setup.print_action_fields.apply_configuration",
    "connect_diagnostics_core.setup.tds.apply_configuration",
    "connect_diagnostics_core.patches.v1_0.configure_purchase_order_approval_boundary.validate_installed_configuration",
]

# Uninstallation
# ------------

# before_uninstall = "connect_diagnostics_core.uninstall.before_uninstall"
# after_uninstall = "connect_diagnostics_core.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "connect_diagnostics_core.utils.before_app_install"
# after_app_install = "connect_diagnostics_core.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "connect_diagnostics_core.utils.before_app_uninstall"
# after_app_uninstall = "connect_diagnostics_core.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "connect_diagnostics_core.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

naming_series_variables = {
    "YYYY-BE": "connect_diagnostics_core.api.erpnext.employee.parse_buddhist_era_naming_series_variable",
}

extend_doctype_class = {
    "Asset": ["connect_diagnostics_core.api.erpnext.asset_movement_workflow.AssetMovementNativeMixin"],
    "Asset Movement": [
        "connect_diagnostics_core.api.erpnext.asset_movement_workflow.AssetMovementWorkflowMixin"
    ],
}

# Document Events
# ---------------
# Hook on document methods and events


doc_events = {
    "*": {"before_naming": "connect_diagnostics_core.setup.document_naming.set_operational_naming_series"},
    "Customer": {
        "before_validate": [
            "connect_diagnostics_core.api.erpnext.customer.before_validate",
            "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
        ],
        "before_naming": "connect_diagnostics_core.naming.customer.set_naming_series",
        "autoname": "connect_diagnostics_core.naming.customer.set_customer_code",
        "validate": "connect_diagnostics_core.api.erpnext.customer.validate",
        "on_update": "connect_diagnostics_core.api.erpnext.customer.on_update",
        "after_insert": "connect_diagnostics_core.api.erpnext.customer.link_source_dksh_customer",
    },
    "Supplier": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
    },
    "Customer Credit Request": {
        "before_validate": "connect_diagnostics_core.api.erpnext.customer_credit_request.before_validate",
        "validate": "connect_diagnostics_core.api.erpnext.customer_credit_request.validate",
        "on_submit": "connect_diagnostics_core.api.erpnext.customer_credit_request.on_submit",
    },
    "Company": {
        "validate": [
            "connect_diagnostics_core.api.erpnext.company.validate_quotation_authorized_signatories",
            "connect_diagnostics_core.api.erpnext.company.validate_borrow_configuration",
        ],
    },
    "Quotation": {
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.quotation.validate_signatory_before_submit",
            "connect_diagnostics_core.api.erpnext.quotation.validate_delivery_terms_before_submit",
        ],
    },
    "Sales Order": {
        "validate": [
            "connect_diagnostics_core.api.erpnext.sales_requirements.validate",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_warning_transaction",
            "connect_diagnostics_core.api.erpnext.sales_order_workflow.validate_sales_order_demo",
        ],
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.sales_order_workflow.validate_sales_order_demo_before_submit",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
        ],
        "before_cancel": "connect_diagnostics_core.api.erpnext.sales_order_workflow.validate_sales_order_demo_before_cancel",
    },
    "Sales Invoice": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
        "validate": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.validate_approval_fields",
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.validate_before_submit",
            "connect_diagnostics_core.api.erpnext.sales_invoice.validate_tax_invoice_readiness",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_transaction",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
            "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
        ],
        "before_cancel": "connect_diagnostics_core.api.erpnext.sales_invoice_credit_workflow.validate_before_cancel",
    },
    "Payment Entry": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
        "validate": [
            "connect_diagnostics_core.api.erpnext.payment_entry.validate",
            "connect_diagnostics_core.api.erpnext.payment_entry_workflow.validate_workflow",
        ],
        "before_submit": "connect_diagnostics_core.api.erpnext.payment_entry_workflow.validate_before_submit",
        "before_cancel": "connect_diagnostics_core.api.erpnext.payment_entry_workflow.validate_before_cancel",
    },
    "Salary Slip": {
        "before_submit": "connect_diagnostics_core.api.erpnext.salary_slip.validate_submission",
    },
    "Supplier Bank Change Request": {
        "validate": "connect_diagnostics_core.api.erpnext.supplier.validate_bank_change_request",
        "on_submit": "connect_diagnostics_core.api.erpnext.supplier.on_submit_bank_change_request",
        "on_cancel": "connect_diagnostics_core.api.erpnext.supplier.on_cancel_bank_change_request",
    },
    "Material Request": {
        "validate": [
            "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_material_request",
            "connect_diagnostics_core.api.erpnext.material_request.validate",
        ],
        "before_cancel": "connect_diagnostics_core.api.erpnext.material_request.before_cancel",
    },
    "Asset Movement": {
        "before_validate": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.lock_assets_before_submit",
        "validate": [
            "connect_diagnostics_core.api.erpnext.material_request.validate_asset_movement",
            "connect_diagnostics_core.api.erpnext.asset_movement_workflow.validate_workflow",
        ],
        "before_submit": "connect_diagnostics_core.api.erpnext.asset_movement_workflow.validate_before_submit",
        "before_cancel": [
            "connect_diagnostics_core.api.erpnext.asset_movement_workflow.validate_before_cancel",
            "connect_diagnostics_core.api.erpnext.material_request.before_cancel_movement",
        ],
    },
    "Quality Inspection": {
        "validate": "connect_diagnostics_core.api.erpnext.material_request.validate_quality_inspection",
        "before_submit": "connect_diagnostics_core.api.erpnext.material_request.before_submit_quality_inspection",
        "on_submit": "connect_diagnostics_core.api.erpnext.material_request.on_submit_quality_inspection",
    },
    "Purchase Order": {
        "validate": [
            "connect_diagnostics_core.api.erpnext.purchase_order_workflow.validate_workflow",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_warning_transaction",
            "connect_diagnostics_core.api.erpnext.purchase_order_workflow.validate_workflow",
        ],
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.purchase_order_workflow.validate_before_submit",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
        ],
        "before_cancel": "connect_diagnostics_core.api.erpnext.purchase_order_workflow.validate_before_cancel",
    },
    "Purchase Receipt": {
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_transaction",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
            "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
        ],
    },
    "Stock Entry": {
        "validate": [
            "connect_diagnostics_core.api.erpnext.material_request.validate_stock_entry",
            "connect_diagnostics_core.api.erpnext.stock_entry_workflow.validate_workflow",
        ],
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.stock_entry_workflow.validate_before_submit",
            "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_transaction",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
        ],
        "before_cancel": [
            "connect_diagnostics_core.api.erpnext.stock_entry_workflow.validate_before_cancel",
            "connect_diagnostics_core.api.erpnext.material_request.before_cancel_movement",
        ],
    },
    "Delivery Note": {
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_transaction",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
            "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
        ],
    },
    "Purchase Invoice": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
        "validate": "connect_diagnostics_core.api.erpnext.purchase_invoice_workflow.validate_workflow",
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.purchase_invoice_workflow.validate_before_submit",
            "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
        ],
        "before_cancel": "connect_diagnostics_core.api.erpnext.purchase_invoice_workflow.validate_before_cancel",
    },
    "Purchase Invoice Item": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
    },
    "Sales Invoice Item": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
    },
    "Journal Entry": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
        "validate": "connect_diagnostics_core.api.erpnext.journal_entry_workflow.validate_workflow",
        "before_submit": "connect_diagnostics_core.api.erpnext.journal_entry_workflow.validate_before_submit",
        "before_cancel": "connect_diagnostics_core.api.erpnext.journal_entry_workflow.validate_before_cancel",
    },
    "Stock Reconciliation": {
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_before_submit",
            "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
        ],
        "before_cancel": "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_before_cancel",
    },
    "Payroll Entry": {
        "validate": "connect_diagnostics_core.api.hrms.payroll_entry_workflow.validate_workflow",
        "before_submit": "connect_diagnostics_core.api.hrms.payroll_entry_workflow.validate_before_submit",
    },
    "Pick List": {
        "before_submit": "connect_diagnostics_core.api.erpnext.stock_reconciliation_freeze.validate_transaction",
    },
    "Item": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
        "validate": "connect_diagnostics_core.api.erpnext.item.validate",
    },
    "Lower Deduction Certificate": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_tds",
    },
    "Tax Withholding Category": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_doctype",
        "before_insert": "connect_diagnostics_core.api.erpnext.tds_guard.block_doctype",
    },
    "Tax Withholding Group": {
        "before_validate": "connect_diagnostics_core.api.erpnext.tds_guard.block_doctype",
        "before_insert": "connect_diagnostics_core.api.erpnext.tds_guard.block_doctype",
    },
    "Employee": {
        "validate": [
            "connect_diagnostics_core.api.erpnext.employee.normalize_national_id",
            "connect_diagnostics_core.api.erpnext.employee.validate_borrow_warehouse",
        ],
    },
    "File": {
        "after_insert": "connect_diagnostics_core.api.frappe.file.mirror_file_on_upload",
    },
}

# Standard link-search queries (override the default link search per doctype).
standard_queries = {
    "Customer": "connect_diagnostics_core.api.erpnext.customer.customer_query",
    "Supplier": "connect_diagnostics_core.api.erpnext.supplier.supplier_query",
}

# Exclude master doctypes from ERPNext's Transaction Deletion tool
company_data_to_be_ignored = []

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": ["connect_diagnostics_core.api.erpnext.regulatory_alerts.run_daily_expiry_processing"],
    "weekly": ["connect_diagnostics_core.api.erpnext.regulatory_alerts.send_weekly_regulatory_digest"],
    "cron": {
        # Runs hourly; the handler self-throttles to Backup Settings.backup_interval_hours.
        "0 * * * *": [
            "connect_diagnostics_core.connect_diagnostics_core.doctype.backup_settings.backup_settings.run_scheduled_backup"
        ],
    },
}

# Testing
# -------

before_tests = "connect_diagnostics_core.tests.test_utils.before_tests"

# Overriding Methods
# ------------------------------
#
# The PDF download is the one print channel Frappe routes through /api/method,
# so wrapping it here records every downloaded document without the client being
# able to skip it. The Print button uses the /printview route instead and is
# recorded from the template by api.frappe.print_log.register_print.
override_whitelisted_methods = {
    "frappe.utils.print_format.download_pdf": ("connect_diagnostics_core.api.frappe.print_log.download_pdf"),
    "erpnext_thailand.utils.get_address_by_tax_id": (
        "connect_diagnostics_core.api.frappe.address.get_address_by_tax_id"
    ),
}

# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
    "Item": "connect_diagnostics_core.api.erpnext.item.get_item_dashboard_data",
    "Customer": "connect_diagnostics_core.api.erpnext.customer.get_customer_dashboard_data",
    "Material Request": "connect_diagnostics_core.api.erpnext.material_request.get_dashboard_data",
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["connect_diagnostics_core.utils.before_request"]
# after_request = ["connect_diagnostics_core.utils.after_request"]

# Job Events
# ----------
# before_job = ["connect_diagnostics_core.utils.before_job"]
# after_job = ["connect_diagnostics_core.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"connect_diagnostics_core.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

fixtures = [
    {"doctype": "Address Template", "filters": [["name", "=", "Thailand"]]},
    {
        "doctype": "Email Template",
        "filters": [["name", "in", ["Leave Approval Notification", "Leave Status Notification"]]],
    },
    {"doctype": "Accounting Dimension"},
    {
        "doctype": "Workflow",
        "filters": [
            [
                "name",
                "in",
                [
                    "Connect Asset Movement Approval",
                    "Connect Journal Entry Approval",
                    "Connect Payment Entry Approval",
                    "Connect Stock Transfer Approval",
                    "Connect Stock Reconciliation Blueprint",
                    "Connect Sales Order Blueprint",
                    "Connect Sales Invoice Credit Blueprint",
                    "Connect Purchase Order Blueprint",
                    "Connect Purchase Invoice Blueprint",
                    "Connect Payroll Entry Blueprint",
                    "Connect Purchase Invoice Blueprint",
                    "Connect Purchase Order Blueprint",
                    "Connect Sales Invoice Credit Blueprint",
                    "Connect Sales Order Blueprint",
                    "Connect Stock Reconciliation Blueprint",
                    "Connect Stock Transfer Approval",
                ],
            ]
        ],
    },
    {
        "doctype": "Workflow State",
        "filters": [
            [
                "name",
                "in",
                [
                    "Asset Movement Approved",
                    "Asset Movement Cancelled",
                    "Asset Movement Draft",
                    "Asset Movement Pending Review",
                    "Asset Movement Pending Approval",
                    "Asset Movement Pending Review",
                    "Asset Movement Rejected",
                    "Asset Movement Submitted",
                    "Journal Entry Approved",
                    "Journal Entry Cancelled",
                    "Journal Entry Draft",
                    "Journal Entry Pending Review",
                    "Journal Entry Rejected",
                    "Journal Entry Returned",
                    "Journal Entry Reviewed",
                    "Journal Entry Submitted",
                    "Payment Entry Approved",
                    "Payment Entry Cancelled",
                    "Stock Transfer Draft",
                    "Stock Transfer Pending Approval",
                    "Stock Transfer Approved",
                    "Stock Transfer Rejected",
                    "Stock Transfer Submitted",
                    "Stock Transfer Cancelled",
                    "Stock Reconciliation Draft",
                    "Stock Reconciliation Pending Review",
                    "Stock Reconciliation Approved",
                    "Stock Reconciliation Rejected",
                    "Stock Reconciliation Submitted",
                    "Stock Reconciliation Cancelled",
                    "Sales Order Draft",
                    "Sales Order Pending Review",
                    "Sales Order Approved",
                    "Sales Order Rejected",
                    "Sales Order Submitted",
                    "Sales Order Cancelled",
                    "Sales Invoice Draft",
                    "Sales Invoice Credit Pending Review",
                    "Sales Invoice Credit Reviewed",
                    "Sales Invoice Credit Returned",
                    "Sales Invoice Credit Approved",
                    "Sales Invoice Credit Rejected",
                    "Sales Invoice Credit Submitted",
                    "Sales Invoice Credit Cancelled",
                    "Purchase Order Draft",
                    "Purchase Order Pending Review",
                    "Purchase Order Pending Approval",
                    "Purchase Order Approved",
                    "Purchase Order Rejected",
                    "Purchase Order Submitted",
                    "Purchase Order Cancelled",
                    "Purchase Invoice Draft",
                    "Purchase Invoice Pending Review",
                    "Purchase Invoice Approved",
                    "Purchase Invoice Rejected",
                    "Purchase Invoice Submitted",
                    "Purchase Invoice Cancelled",
                    "Payroll Entry Draft",
                    "Payroll Entry Pending Review",
                    "Payroll Entry Rejected",
                    "Payroll Entry Returned",
                    "Payroll Entry Reviewed",
                    "Payroll Entry Submitted",
                    "Purchase Invoice Approved",
                    "Purchase Invoice Cancelled",
                    "Purchase Invoice Draft",
                    "Purchase Invoice Pending Accounting Approval",
                    "Purchase Invoice Pending Source Verification",
                    "Purchase Invoice Rejected",
                    "Purchase Invoice Returned",
                    "Purchase Invoice Submitted",
                    "Purchase Order Approved",
                    "Purchase Order Cancelled",
                    "Purchase Order Draft",
                    "Purchase Order Pending Approval",
                    "Purchase Order Pending Review",
                    "Purchase Order Rejected",
                    "Purchase Order Submitted",
                    "Sales Invoice Cancelled",
                    "Sales Invoice Credit Approved",
                    "Sales Invoice Credit Pending Review",
                    "Sales Invoice Credit Returned",
                    "Sales Invoice Credit Reviewed",
                    "Sales Invoice Draft",
                    "Sales Invoice Submitted",
                    "Sales Order Approved",
                    "Sales Order Cancelled",
                    "Sales Order Draft",
                    "Sales Order Pending Review",
                    "Sales Order Rejected",
                    "Sales Order Returned",
                    "Sales Order Reviewed",
                    "Sales Order Submitted",
                    "Stock Entry Cancelled",
                    "Stock Entry Submitted",
                    "Stock Reconciliation Approved",
                    "Stock Reconciliation Cancelled",
                    "Stock Reconciliation Draft",
                    "Stock Reconciliation Pending Review",
                    "Stock Reconciliation Rejected",
                    "Stock Reconciliation Returned",
                    "Stock Reconciliation Reviewed",
                    "Stock Reconciliation Submitted",
                    "Stock Transfer Approved",
                    "Stock Transfer Cancelled",
                    "Stock Transfer Draft",
                    "Stock Transfer Pending Review",
                    "Stock Transfer Rejected",
                    "Stock Transfer Returned",
                    "Stock Transfer Reviewed",
                    "Stock Transfer Submitted",
                ],
            ]
        ],
    },
    {
        "doctype": "Workflow Action Master",
        "filters": [
            [
                "name",
                "in",
                [
                    "Send Asset Movement for Review",
                    "Review Asset Movement",
                    "Return Asset Movement",
                    "Approve Asset Movement",
                    "Reject Asset Movement",
                    "Resubmit Asset Movement",
                    "Submit Asset Movement",
                    "Cancel Asset Movement",
                    "Submit Payment Entry for Approval",
                    "Approve Payment Entry",
                    "Reject Payment Entry",
                    "Post Payment Entry",
                    "Cancel Payment Entry",
                    "Submit Stock Transfer for Approval",
                    "Approve Stock Transfer",
                    "Reject Stock Transfer",
                    "Post Stock Transfer",
                    "Cancel Stock Transfer",
                    "Submit Stock Reconciliation for Review",
                    "Approve Stock Reconciliation",
                    "Reject Stock Reconciliation",
                    "Post Stock Reconciliation",
                    "Cancel Stock Reconciliation",
                    "Submit Sales Order for Review",
                    "Approve Sales Order",
                    "Reject Sales Order",
                    "Post Sales Order",
                    "Cancel Sales Order",
                    "Send Sales Invoice Credit for Review",
                    "Resubmit Sales Invoice Credit for Review",
                    "Review Sales Invoice Credit",
                    "Return Sales Invoice Credit",
                    "Approve Sales Invoice Credit",
                    "Reject Sales Invoice Credit",
                    "Post Sales Invoice Credit",
                    "Cancel Sales Invoice Credit",
                    "Submit Purchase Order for Review",
                    "Review Purchase Order",
                    "Return Purchase Order",
                    "Resubmit Purchase Order",
                    "Approve Purchase Order",
                    "Reject Purchase Order",
                    "Post Purchase Order",
                    "Cancel Purchase Order",
                    "Submit Purchase Invoice for Review",
                    "Approve Purchase Invoice",
                    "Reject Purchase Invoice",
                    "Post Purchase Invoice",
                    "Cancel Purchase Invoice",
                    "Submit Payroll Entry for Review",
                    "Approve Payroll Entry",
                    "Approve Purchase Invoice",
                    "Approve Purchase Order",
                    "Approve Sales Invoice Credit",
                    "Approve Sales Order",
                    "Approve Stock Reconciliation",
                    "Approve Stock Transfer",
                    "Cancel Asset Movement",
                    "Cancel Journal Entry",
                    "Cancel Payment Entry",
                    "Cancel Payroll Entry",
                    "Cancel Purchase Invoice",
                    "Cancel Purchase Order",
                    "Cancel Sales Invoice",
                    "Cancel Sales Invoice Credit",
                    "Cancel Sales Order",
                    "Cancel Stock Entry",
                    "Cancel Stock Reconciliation",
                    "Cancel Stock Transfer",
                    "Post Purchase Invoice",
                    "Post Purchase Order",
                    "Post Sales Invoice Credit",
                    "Reject Asset Movement",
                    "Reject Journal Entry",
                    "Reject Payment Entry",
                    "Reject Payroll Entry",
                    "Reject Purchase Invoice",
                    "Reject Purchase Order",
                    "Reject Sales Invoice Credit",
                    "Reject Sales Order",
                    "Reject Stock Reconciliation",
                    "Reject Stock Transfer",
                    "Resubmit Asset Movement",
                    "Resubmit Journal Entry for Review",
                    "Resubmit Payment Entry for Review",
                    "Resubmit Payroll Entry for Review",
                    "Resubmit Purchase Invoice",
                    "Resubmit Purchase Order",
                    "Resubmit Sales Invoice Credit for Review",
                    "Resubmit Sales Order for Review",
                    "Resubmit Stock Reconciliation for Review",
                    "Resubmit Stock Transfer for Review",
                    "Return Asset Movement",
                    "Return Journal Entry",
                    "Return Payment Entry",
                    "Return Payroll Entry",
                    "Return Purchase Invoice",
                    "Return Purchase Order",
                    "Return Sales Invoice Credit",
                    "Return Sales Order",
                    "Return Stock Reconciliation",
                    "Return Stock Transfer",
                    "Review Asset Movement",
                    "Review Journal Entry",
                    "Review Payment Entry",
                    "Review Payroll Entry",
                    "Review Purchase Order",
                    "Review Sales Invoice Credit",
                    "Review Sales Order",
                    "Review Stock Reconciliation",
                    "Review Stock Transfer",
                    "Send Asset Movement for Review",
                    "Send Journal Entry for Review",
                    "Send Payment Entry for Review",
                    "Send Payroll Entry for Review",
                    "Send Sales Invoice Credit for Review",
                    "Send Sales Order for Review",
                    "Send Stock Reconciliation for Review",
                    "Send Stock Transfer for Review",
                    "Submit Asset Movement",
                    "Submit Journal Entry",
                    "Submit Payment Entry",
                    "Submit Payroll Entry",
                    "Submit Purchase Invoice for Review",
                    "Submit Purchase Order for Review",
                    "Submit Sales Invoice",
                    "Submit Sales Order",
                    "Submit Stock Entry",
                    "Submit Stock Reconciliation",
                    "Submit Stock Transfer",
                    "Verify Purchase Invoice Source",
                ],
            ]
        ],
    },
]
