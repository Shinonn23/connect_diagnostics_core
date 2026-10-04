# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Retire the app-owned Material Request borrowing and demo feature."""

from __future__ import annotations

import frappe
from frappe.model.document import Document

APP_DOCTYPES = (
    "Demo Return Inspection Check",
    "Borrowed Asset Return Inspection Check",
    "Borrowed Item Resolution Item",
    "Dispatch Transfer",
    "Demo Return Inspection",
    "Borrowed Asset Return Inspection",
    "Borrowed Item Resolution",
    "Dispatch",
)

APP_TABLES = tuple(f"tab{doctype}" for doctype in APP_DOCTYPES)

STANDARD_FIELDS = {
    "Material Request": (
        "purchase_reason",
        "supporting_document_complete",
        "request_usage",
        "destination_type",
        "responsible_employee",
        "destination_customer",
        "destination_address",
        "asset_location",
        "expected_return_date",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
        "submit_by",
        "submit_at",
        "submit_signature",
        "checked_by",
        "checked_at",
        "checked_signature",
        "custom_approver_employee",
        "custom_approver_name",
        "custom_approver_signature",
        "custom_column_break_tgrjm",
        "custom_print_signature",
    ),
    "Material Request Item": ("fulfillment_route", "allocated_asset", "unit_cost_ex_vat", "cost_source"),
    "Employee": ("borrow_warehouse",),
    "Company": (
        "borrow_in_transit_warehouse",
        "return_qa_hold_warehouse",
        "return_repair_warehouse",
        "return_qa_hold_location",
        "return_repair_location",
    ),
    "Asset Movement": ("material_request", "return_dispatch_transfer", "borrowed_item_resolution"),
    "Asset Capitalization": ("material_request",),
    "Quality Inspection": (
        "material_request",
        "return_dispatch_transfer",
        "return_disposition",
        "release_stock_entry",
        "repair_stock_entry",
    ),
    "Stock Entry": ("return_dispatch_transfer", "borrowed_item_resolution"),
}

WORKFLOW_STATES = (
    "Material Request Draft",
    "Material Request Pending Review",
    "Material Request Approved",
    "Material Request Rejected",
    "Material Request Submitted",
    "Material Request Cancelled",
)
WORKFLOW_ACTIONS = (
    "Submit Material Request for Review",
    "Approve Material Request",
    "Reject Material Request",
    "Post Material Request",
    "Cancel Material Request",
)
MATERIAL_REQUEST_PURPOSE_OPTIONS = (
    "Purchase",
    "Material Transfer",
    "Asset Transfer",
    "Material Issue",
    "Manufacture",
    "Subcontracting",
    "Customer Provided",
)
PRINT_FORMATS = (
    "Material Request",
    "Dispatch",
    "Demo Asset Label",
    "Borrowed Asset Return Inspection",
    "Demo Return Inspection",
)
FIELD_ORDER_RETIRED_FIELDS = (
    "custom_print_signature",
    "custom_approver_employee",
    "custom_approver_name",
    "custom_column_break_tgrjm",
    "custom_approver_signature",
)
PERMISSION_FIELDS = (
    "read",
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "report",
    "export",
    "import",
    "share",
    "print",
    "email",
    "select",
    "mask",
)
APPROVAL_PERMISSION_GRANTS = {
    ("C-Level Approver", 0): {"read", "write", "submit", "report", "print", "email"},
    ("Accounts User", 0): {"read", "write", "report", "print", "email"},
    ("Accounts User", 1): {"read", "write"},
}


def execute() -> None:
    """Delete only the approved borrowing/demo schema and its stored records."""
    _delete_material_request_workflow()
    _delete_pending_workflow_actions()
    _delete_workflow_masters()
    _restore_material_request_permissions()
    removed_workflow_state = _delete_retired_workflow_state_field()
    _delete_print_formats()
    _delete_report()
    _delete_material_request_property_setters(removed_workflow_state)
    _delete_fields()
    _remove_retired_navigation_links()
    _delete_doctypes()
    _drop_standard_columns()
    _drop_app_tables()
    frappe.clear_cache()


def _delete_doctypes() -> None:
    for doctype in APP_DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)


def _remove_retired_navigation_links() -> None:
    """Remove existing workspace links before their linked DocTypes are deleted."""
    retired_links = {
        "Dispatch",
        "Borrowed Asset Return Inspection",
        "Borrowed Item Resolution",
        "Outstanding Borrowed Items",
    }
    for doctype, table_field in (("Workspace", "links"), ("Workspace Sidebar", "items")):
        for name in frappe.get_all(doctype, pluck="name"):
            doc = frappe.get_doc(doctype, name)
            rows = doc.get(table_field) or []
            retained_rows = [row for row in rows if row.get("link_to") not in retired_links]
            if len(retained_rows) != len(rows):
                doc.set(table_field, retained_rows)
                previous_in_import = frappe.flags.in_import
                frappe.flags.in_import = True
                try:
                    doc.save(ignore_permissions=True)
                finally:
                    frappe.flags.in_import = previous_in_import


def _delete_fields() -> None:
    for doctype, fieldnames in STANDARD_FIELDS.items():
        for fieldname in fieldnames:
            name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
            if name:
                frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
    for name in frappe.get_all("Custom Field", filters={"dt": ["in", APP_DOCTYPES]}, pluck="name"):
        frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
    for name in frappe.get_all("Property Setter", filters={"doc_type": ["in", APP_DOCTYPES]}, pluck="name"):
        frappe.delete_doc("Property Setter", name, force=True, ignore_permissions=True)


def _delete_material_request_workflow() -> None:
    if frappe.db.exists("Workflow", "Connect Material Request Blueprint"):
        frappe.delete_doc(
            "Workflow", "Connect Material Request Blueprint", force=True, ignore_permissions=True
        )


def _delete_workflow_masters() -> None:
    for doctype, names in (("Workflow State", WORKFLOW_STATES), ("Workflow Action Master", WORKFLOW_ACTIONS)):
        for name in names:
            if frappe.db.exists(doctype, name):
                frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)


def _delete_pending_workflow_actions() -> None:
    filters = {
        "reference_doctype": "Material Request",
        "workflow_state": ["in", WORKFLOW_STATES],
    }
    for name in frappe.get_all("Workflow Action", filters=filters, pluck="name"):
        frappe.delete_doc("Workflow Action", name, force=True, ignore_permissions=True)


def _restore_material_request_permissions() -> None:
    for (role, permlevel), app_grants in APPROVAL_PERMISSION_GRANTS.items():
        filters = {
            "parent": "Material Request",
            "role": role,
            "permlevel": permlevel,
            "if_owner": 0,
        }
        custom_name = frappe.db.get_value("Custom DocPerm", filters, "name")
        if not custom_name:
            continue
        permission = frappe.get_doc("Custom DocPerm", custom_name)

        native_permissions = frappe.db.get_value(
            "DocPerm",
            {"parent": "Material Request", "role": role, "permlevel": permlevel, "if_owner": 0},
            list(PERMISSION_FIELDS),
            as_dict=True,
        )
        if not native_permissions:
            if _matches_app_permission_grants(permission, app_grants):
                frappe.delete_doc("Custom DocPerm", custom_name, force=True, ignore_permissions=True)
            continue

        changed = False
        for fieldname in app_grants:
            if int(permission.get(fieldname) or 0) != 1:
                continue
            value = native_permissions.get(fieldname)
            if permission.get(fieldname) != value:
                permission.set(fieldname, value)
                changed = True
        if changed:
            permission.save(ignore_permissions=True)


def _matches_app_permission_grants(permission: Document, app_grants: set[str]) -> bool:
    meta = frappe.get_meta("Custom DocPerm")
    for fieldname in PERMISSION_FIELDS:
        default = meta.get_field(fieldname).default or 0
        expected = 1 if fieldname in app_grants else int(default)
        if int(permission.get(fieldname) or 0) != expected:
            return False
    return True


def _delete_retired_workflow_state_field() -> bool:
    remaining_workflows = frappe.get_all(
        "Workflow",
        filters={"document_type": "Material Request"},
        pluck="name",
        limit=1,
    )
    if remaining_workflows:
        return False

    custom_field_name = "Material Request-workflow_state"
    if not frappe.db.exists("Custom Field", custom_field_name):
        return not frappe.db.has_column("Material Request", "workflow_state")

    custom_field = frappe.get_doc("Custom Field", custom_field_name)
    if not (
        custom_field.fieldtype == "Link"
        and custom_field.options == "Workflow State"
        and custom_field.hidden
        and custom_field.allow_on_submit
        and custom_field.no_copy
    ):
        return False

    frappe.delete_doc("Custom Field", custom_field_name, force=True, ignore_permissions=True)
    if frappe.db.has_column("Material Request", "workflow_state"):
        frappe.db.sql_ddl("ALTER TABLE `tabMaterial Request` DROP COLUMN `workflow_state`")
    return True


def _delete_print_formats() -> None:
    for name in PRINT_FORMATS:
        if frappe.db.exists("Print Format", name):
            frappe.delete_doc("Print Format", name, force=True, ignore_permissions=True)


def _delete_report() -> None:
    if frappe.db.exists("Report", "Outstanding Borrowed Items"):
        frappe.delete_doc("Report", "Outstanding Borrowed Items", force=True, ignore_permissions=True)


def _delete_material_request_property_setters(removed_workflow_state: bool) -> None:
    name = "Material Request-main-material_request_type"
    if frappe.db.exists("Property Setter", name):
        setter = frappe.get_doc("Property Setter", name)
        if (
            setter.doc_type == "Material Request"
            and setter.field_name == "material_request_type"
            and setter.property == "options"
            and setter.property_type in {"Select", "Text"}
        ):
            setter.value = "\n".join(MATERIAL_REQUEST_PURPOSE_OPTIONS)
            setter.save(ignore_permissions=True)

    field_order_name = "Material Request-main-field_order"
    if not frappe.db.exists("Property Setter", field_order_name):
        return
    setter = frappe.get_doc("Property Setter", field_order_name)
    try:
        field_order = frappe.parse_json(setter.value or "[]")
    except (TypeError, ValueError):
        return
    if not isinstance(field_order, list):
        return
    retired_fields = set(FIELD_ORDER_RETIRED_FIELDS)
    if removed_workflow_state:
        retired_fields.add("workflow_state")
    updated = [fieldname for fieldname in field_order if fieldname not in retired_fields]
    if updated != field_order:
        setter.value = frappe.as_json(updated)
        setter.save(ignore_permissions=True)


def _drop_standard_columns() -> None:
    for doctype, fieldnames in STANDARD_FIELDS.items():
        for fieldname in fieldnames:
            if frappe.db.has_column(doctype, fieldname):
                frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{fieldname}`")


def _drop_app_tables() -> None:
    for table in APP_TABLES:
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table}`")
