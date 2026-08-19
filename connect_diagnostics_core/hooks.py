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
page_js = {
    "print": [
        "public/js/custom/print/engine.js",
        "public/js/custom/print/providers/print_options.js",
    ]
}

# include js in doctype views
doctype_js = {
    "Address": "public/js/custom/address/doctype.js",
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
before_migrate = "connect_diagnostics_core.setup.before_migrate"
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
    "MM-DOC": "connect_diagnostics_core.setup.document_naming.parse_document_month",
    # Hyphen-free aliases: Frappe's braced-autoname regex cannot match "-" inside
    # {...}, so `format:` autoname strings use these instead of YY-BE/MM-DOC.
    "YYBE": "connect_diagnostics_core.api.erpnext.employee.parse_buddhist_era_naming_series_variable",
    "MMDOC": "connect_diagnostics_core.setup.document_naming.parse_document_month",
}

# Document Events
# ---------------
# Hook on document methods and events


doc_events = {
    "*": {"before_naming": "connect_diagnostics_core.setup.document_naming.set_operational_naming_series"},
    "Customer": {
        "before_validate": "connect_diagnostics_core.api.erpnext.customer.before_validate",
        "before_naming": "connect_diagnostics_core.naming.customer.set_naming_series",
        "autoname": "connect_diagnostics_core.naming.customer.set_customer_code",
        "validate": "connect_diagnostics_core.api.erpnext.customer.validate",
        "on_update": "connect_diagnostics_core.api.erpnext.customer.on_update",
        "after_insert": "connect_diagnostics_core.api.erpnext.customer.link_source_dksh_customer",
    },
    "Customer Credit Request": {
        "before_validate": "connect_diagnostics_core.api.erpnext.customer_credit_request.before_validate",
        "validate": "connect_diagnostics_core.api.erpnext.customer_credit_request.validate",
        "on_submit": "connect_diagnostics_core.api.erpnext.customer_credit_request.on_submit",
    },
    "Company": {
        "on_update": "connect_diagnostics_core.api.erpnext.company.create_default_accounting_department",
    },
    "Sales Order": {
        "validate": [
            "connect_diagnostics_core.api.erpnext.sales_requirements.validate",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_warning_transaction",
        ],
        "before_submit": "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
    },
    "Sales Invoice": {
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.sales_invoice.validate_tax_invoice_readiness",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_transaction",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
        ],
    },
    "Payment Entry": {
        "validate": "connect_diagnostics_core.api.erpnext.payment_entry.validate",
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
        "validate": "connect_diagnostics_core.api.erpnext.procure_to_pay.validate_material_request",
    },
    "Purchase Order": {
        "validate": [
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_warning_transaction",
        ],
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
        ],
    },
    "Purchase Receipt": {
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_transaction",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
        ],
    },
    "Stock Entry": {
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_transaction",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
        ],
    },
    "Delivery Note": {
        "before_submit": [
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.validate_transaction",
            "connect_diagnostics_core.api.erpnext.regulatory_transactions.capture_transaction_snapshot",
        ],
    },
    "Item": {
        "validate": "connect_diagnostics_core.api.erpnext.item.validate",
    },
    "Employee": {
        "validate": "connect_diagnostics_core.api.erpnext.employee.normalize_national_id",
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

extend_doctype_class = {
    "Payroll Entry": [
        "connect_diagnostics_core.api.erpnext.payroll_entry.PayrollEntryAccountingDimensionMixin",
    ],
}

# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
    "Item": "connect_diagnostics_core.api.erpnext.item.get_item_dashboard_data",
    "Customer": "connect_diagnostics_core.api.erpnext.customer.get_customer_dashboard_data",
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
