app_name = "connect_diagnostics_core"
app_title = "Connect Diagnostics Core"
app_publisher = "Siwat Sroisuwan"
app_description = "Custom app for Connect Diagnostics to manage and implement company-specific business logic, workflows, and processes on ERPNext."
app_email = "siwat61719@gmail.com"
app_license = "bsl-1.0"

# Apps
# ------------------

required_apps = ["erpnext", "erpnext_thailand", "hrms"]

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
page_js = {"print": "public/js/custom/print/doctype.js"}

# include js in doctype views
doctype_js = {
    "Address": "public/js/custom/address/doctype.js",
    "Customer": "public/js/custom/customer/doctype.js",
    "Delivery Note": "public/js/custom/delivery_note/doctype.js",
    "Material Request": "public/js/custom/material_request/doctype.js",
    "Payment Entry": "public/js/custom/payment_entry/doctype.js",
    "Purchase Order": "public/js/custom/purchase_order/doctype.js",
    "Quotation": "public/js/custom/quotation/doctype.js",
    "Sales Invoice": "public/js/custom/sales_invoice/doctype.js",
    "Sales Order": "public/js/custom/sales_order/doctype.js",
    "Stock Entry": "public/js/custom/stock_entry/doctype.js",
}
doctype_list_js = {
    "Customer": "public/js/custom/customer/list_view.js",
    "Item": "public/js/custom/item/list_view.js",
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
        "connect_diagnostics_core.api.erpnext.sales_invoice.get_sales_invoice_print_context",
        "connect_diagnostics_core.api.erpnext.quotation.get_quotation_print_context",
        "connect_diagnostics_core.api.frappe.print_log.register_print",
    ],
    # "filters": "connect_diagnostics_core.utils.jinja_filters"
}

# Installation
# ------------

# before_install = "connect_diagnostics_core.install.before_install"
after_install = "connect_diagnostics_core.setup.after_install"
after_sync = "connect_diagnostics_core.setup.after_sync"
after_migrate = "connect_diagnostics_core.setup.after_migrate"

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
    "YY-BE": "connect_diagnostics_core.api.erpnext.employee.parse_buddhist_era_naming_series_variable",
}

# Document Events
# ---------------
# Hook on document methods and events


doc_events = {
    "*": {"before_naming": "connect_diagnostics_core.naming.company_prefix.apply_company_abbr_prefix"},
    "Customer": {
        "before_validate": "connect_diagnostics_core.api.erpnext.customer.before_validate",
        "before_naming": "connect_diagnostics_core.naming.customer.set_naming_series",
        "autoname": "connect_diagnostics_core.naming.customer.set_customer_code",
        "validate": "connect_diagnostics_core.api.erpnext.customer.validate",
        "on_update": "connect_diagnostics_core.api.erpnext.customer.on_update",
    },
    "Customer Credit Request": {
        "before_validate": "connect_diagnostics_core.api.erpnext.customer_credit_request.before_validate",
        "validate": "connect_diagnostics_core.api.erpnext.customer_credit_request.validate",
        "before_submit": "connect_diagnostics_core.api.erpnext.customer_credit_request.before_submit",
        "on_submit": "connect_diagnostics_core.api.erpnext.customer_credit_request.on_submit",
    },
    "Address": {
        "after_insert": "connect_diagnostics_core.api.erpnext.customer.refresh_linked_customer_readiness",
        "on_update": "connect_diagnostics_core.api.erpnext.customer.refresh_linked_customer_readiness",
        "after_delete": "connect_diagnostics_core.api.erpnext.customer.refresh_linked_customer_readiness",
    },
    "Contact": {
        "after_insert": "connect_diagnostics_core.api.erpnext.customer.refresh_linked_customer_readiness",
        "on_update": "connect_diagnostics_core.api.erpnext.customer.refresh_linked_customer_readiness",
        "after_delete": "connect_diagnostics_core.api.erpnext.customer.refresh_linked_customer_readiness",
    },
    "Supplier": {
        "before_validate": "connect_diagnostics_core.api.erpnext.supplier.before_validate",
        "validate": "connect_diagnostics_core.api.erpnext.supplier.validate",
    },
    "Company": {
        "on_update": "connect_diagnostics_core.api.erpnext.company.create_default_accounting_department",
    },
    "Sales Order": {
        "validate": "connect_diagnostics_core.api.erpnext.sales_requirements.validate",
    },
    "Sales Invoice": {
        "validate": "connect_diagnostics_core.api.erpnext.sales_requirements.validate",
    },
    "Payment Entry": {
        "before_submit": (
            "connect_diagnostics_core.api.erpnext.payment_approval.validate_payment_entry_before_submit"
        ),
        "validate": "connect_diagnostics_core.api.erpnext.payment_entry.validate",
    },
    "Bank Account": {
        "validate": "connect_diagnostics_core.api.erpnext.supplier.validate_bank_account",
    },
    "Supplier Bank Change Request": {
        "before_validate": "connect_diagnostics_core.api.erpnext.supplier.before_validate_bank_change_request",
        "validate": "connect_diagnostics_core.api.erpnext.supplier.validate_bank_change_request",
        "on_submit": "connect_diagnostics_core.api.erpnext.supplier.on_submit_bank_change_request",
        "on_cancel": "connect_diagnostics_core.api.erpnext.supplier.on_cancel_bank_change_request",
    },
    "Material Request": {
        "before_validate": "connect_diagnostics_core.api.erpnext.procure_to_pay.before_validate",
        "validate": "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_material_request",
        "before_submit": "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_before_submit",
    },
    "Purchase Order": {
        "before_validate": "connect_diagnostics_core.api.erpnext.procure_to_pay.before_validate",
        "validate": "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_purchase_order",
        "before_submit": "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_before_submit",
    },
    "Purchase Receipt": {
        "before_validate": "connect_diagnostics_core.api.erpnext.procure_to_pay.before_validate",
        "validate": "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_purchase_receipt",
        "before_submit": "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_before_submit",
    },
    "Purchase Invoice": {
        "before_validate": "connect_diagnostics_core.api.erpnext.procure_to_pay.before_validate",
        "validate": "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_purchase_invoice",
        "before_submit": "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_before_submit",
    },
    "Payment Request": {
        "before_save": [
            "connect_diagnostics_core.api.erpnext.payment_approval.validate_payment_request_transition",
            "connect_diagnostics_core.api.erpnext.payment_approval.clear_completed_workflow_actions_for_next_state",
        ],
        "before_cancel": "connect_diagnostics_core.api.erpnext.payment_approval.set_cancelled_workflow_state",
        "before_discard": "connect_diagnostics_core.api.erpnext.payment_approval.validate_before_discard",
        "before_submit": (
            "connect_diagnostics_core.api.erpnext.payment_approval.validate_payment_request_before_submit"
        ),
    },
    "Item": {
        "validate": "connect_diagnostics_core.api.erpnext.item.validate",
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
company_data_to_be_ignored = ["Accounting Department"]

# Scheduled Tasks
# ---------------

scheduler_events = {
    "cron": {
        # Runs hourly; the handler self-throttles to Backup Settings.backup_interval_hours.
        "0 * * * *": [
            "connect_diagnostics_core.connect_diagnostics_core.doctype.backup_settings.backup_settings.run_scheduled_backup"
        ],
    }
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
}

# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "connect_diagnostics_core.task.get_dashboard_data"
# }

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
    {
        "doctype": "Workflow",
        "filters": [
            [
                "name",
                "in",
                [
                    "Payment Request Approval",
                    "Supplier Onboarding",
                    "Supplier Bank Change Approval",
                    "Material Request Approval",
                    "Purchase Order Approval",
                    "Purchase Receipt Inspection",
                    "Purchase Invoice Verification",
                ],
            ]
        ],
    },
    {
        "doctype": "Workflow State",
        "filters": [
            [
                "workflow_state_name",
                "in",
                [
                    "Payment Request Draft",
                    "Payment Request Submitted",
                    "Pending Payment Request AP Review",
                    "Pending Executive Payment Request Approval",
                    "Payment Request Approved",
                    "Payment Request Rejected",
                    "Payment Request Cancelled",
                    "Supplier Draft",
                    "Pending Supplier Verification",
                    "Pending Supplier Activation",
                    "Supplier Active",
                    "Supplier Active (Legacy)",
                    "Supplier Bank Change Draft",
                    "Pending Supplier Bank Verification",
                    "Pending Supplier Bank Approval",
                    "Supplier Bank Verified",
                    "Supplier Bank Change Rejected",
                    "Material Request Draft",
                    "Pending Material Request Approval",
                    "Material Request Approved",
                    "Material Request Rejected",
                    "Purchase Order Draft",
                    "Pending Purchase Order Finance Review",
                    "Pending Purchase Order Exception Approval",
                    "Purchase Order Approved",
                    "Purchase Order Rejected",
                    "Purchase Receipt Draft",
                    "Pending Goods Inspection",
                    "Purchase Receipt Accepted",
                    "Purchase Invoice Draft",
                    "Pending Purchase Invoice Verification",
                    "Pending Purchase Invoice Exception Approval",
                    "Purchase Invoice Verified",
                    "Purchase Invoice Rejected",
                ],
            ]
        ],
    },
    {
        "doctype": "Workflow Action Master",
        "filters": [
            [
                "workflow_action_name",
                "in",
                [
                    "Request Payment Approval",
                    "Complete Payment Request AP Review",
                    "Approve Payment Request",
                    "Reject Payment Request",
                    "Revise Payment Request",
                    "Submit Payment Request",
                    "Request supplier verification",
                    "Verify supplier",
                    "Activate supplier",
                    "Request bank verification",
                    "Verify bank details",
                    "Approve bank change",
                    "Request approval",
                    "Approve material request",
                    "Request finance review",
                    "Approve purchase order",
                    "Request goods inspection",
                    "Accept goods",
                    "Request AP verification",
                    "Verify purchase invoice",
                    "Return supplier",
                    "Return bank change",
                    "Reject bank change",
                    "Reject material request",
                    "Revise material request",
                    "Request exception approval",
                    "Approve purchase order exception",
                    "Reject purchase order",
                    "Revise purchase order",
                    "Return receipt",
                    "Request invoice exception approval",
                    "Approve purchase invoice exception",
                    "Reject purchase invoice",
                    "Revise purchase invoice",
                ],
            ]
        ],
    },
    {"doctype": "Property Setter", "filters": [["module", "=", "Connect Diagnostics Core"]]},
    {"doctype": "Address Template", "filters": [["name", "=", "Thailand"]]},
    {"doctype": "Terms and Conditions"},
    {
        "doctype": "Email Template",
        "filters": [
            [
                "name",
                "in",
                ["Leave Approval Notification", "Leave Status Notification"],
            ]
        ],
    },
]
