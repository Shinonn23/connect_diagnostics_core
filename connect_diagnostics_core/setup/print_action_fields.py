# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Code-managed workflow-action snapshot fields rendered by print formats.

The workflow transition task writes the Employee, action time, and the
Employee's signature snapshot atomically on the transaction. Print formats read
the snapshot from the transaction and never use the Employee's current
signature, so reprinting an old document keeps the original evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


@dataclass(frozen=True)
class PrintAction:
    """One workflow action that can be shown on a print format."""

    key: str
    employee_field: str
    datetime_field: str
    signature_field: str
    required_signature: bool = False
    protected: bool = False
    ignore_employee_user_permissions: bool = True


PRINT_ACTIONS: dict[str, tuple[PrintAction, ...]] = {
    "Sales Invoice": (
        PrintAction("submit", "submit_by", "submit_at", "submit_signature"),
        PrintAction("received", "received_by", "received_at", "received_signature"),
        PrintAction("delivered", "delivered_by", "delivered_at", "delivered_signature"),
        PrintAction("authorized", "authorized_by", "authorized_at", "authorized_signature", True, True),
        PrintAction("checked", "checked_by", "checked_at", "checked_signature"),
        PrintAction(
            "return_received",
            "return_received_by",
            "return_received_at",
            "return_received_signature",
        ),
        PrintAction(
            "warehouse_checked",
            "warehouse_checked_by",
            "warehouse_checked_at",
            "warehouse_checked_signature",
        ),
    ),
    "Payment Entry": (
        PrintAction("submit", "submit_by", "submit_at", "submit_signature"),
        PrintAction("received", "received_by", "received_at", "received_signature"),
        PrintAction("delivered", "delivered_by", "delivered_at", "delivered_signature"),
        PrintAction(
            "authorized",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
            True,
            True,
            ignore_employee_user_permissions=True,
        ),
        PrintAction(
            "checked",
            "checked_by",
            "checked_at",
            "checked_signature",
            True,
            True,
            ignore_employee_user_permissions=True,
        ),
    ),
    "Sales Order": (
        PrintAction(
            "submit",
            "submit_by",
            "submit_at",
            "submit_signature",
            ignore_employee_user_permissions=True,
        ),
        PrintAction(
            "prepared",
            "prepared_by",
            "prepared_at",
            "prepared_signature",
            ignore_employee_user_permissions=True,
        ),
        PrintAction(
            "checked",
            "checked_by",
            "checked_at",
            "checked_signature",
            ignore_employee_user_permissions=True,
        ),
        PrintAction(
            "authorized",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
            True,
            True,
            ignore_employee_user_permissions=True,
        ),
    ),
    "Purchase Order": (
        PrintAction("submit", "submit_by", "submit_at", "submit_signature"),
        PrintAction("ordered", "ordered_by", "ordered_at", "ordered_signature"),
        PrintAction("checked", "checked_by", "checked_at", "checked_signature", True, True),
        PrintAction("authorized", "authorized_by", "authorized_at", "authorized_signature", True, True),
    ),
    "Purchase Receipt": (
        PrintAction("submit", "submit_by", "submit_at", "submit_signature"),
        PrintAction("received", "received_by", "received_at", "received_signature"),
        PrintAction("checked", "checked_by", "checked_at", "checked_signature"),
        PrintAction("authorized", "authorized_by", "authorized_at", "authorized_signature"),
    ),
    "Purchase Invoice": (
        PrintAction(
            "checked",
            "checked_by",
            "checked_at",
            "checked_signature",
            ignore_employee_user_permissions=True,
        ),
        PrintAction(
            "authorized",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
            True,
            True,
            ignore_employee_user_permissions=True,
        ),
    ),
    "Quotation": (PrintAction("signatory", "signatory_by", "signatory_at", "signatory_signature"),),
    "Material Request": (
        PrintAction("authorized", "authorized_by", "authorized_at", "authorized_signature", True, True),
    ),
    "Stock Reconciliation": (
        PrintAction("checked", "checked_by", "checked_at", "checked_signature", True, True),
        PrintAction("authorized", "authorized_by", "authorized_at", "authorized_signature", True, True),
    ),
    "Asset Movement": (
        PrintAction(
            "checked",
            "checked_by",
            "checked_at",
            "checked_signature",
            ignore_employee_user_permissions=True,
        ),
        PrintAction(
            "authorized",
            "authorized_by",
            "authorized_at",
            "authorized_signature",
            True,
            True,
            ignore_employee_user_permissions=True,
        ),
    ),
    "Journal Entry": (
        PrintAction("checked", "checked_by", "checked_at", "checked_signature"),
        PrintAction("authorized", "authorized_by", "authorized_at", "authorized_signature", True, True),
    ),
    "Asset Capitalization": (
        PrintAction("authorized", "authorized_by", "authorized_at", "authorized_signature"),
    ),
    "Stock Entry": (
        PrintAction("submit", "submit_by", "submit_at", "submit_signature"),
        PrintAction("checked", "checked_by", "checked_at", "checked_signature", True, True),
        PrintAction("authorized", "authorized_by", "authorized_at", "authorized_signature", True, True),
    ),
    "Payroll Entry": (
        PrintAction("checked", "checked_by", "checked_at", "checked_signature"),
        PrintAction("authorized", "authorized_by", "authorized_at", "authorized_signature", True, True),
    ),
    "Withholding Tax Cert": (PrintAction("signed", "signed_by", "signed_at", "signed_signature"),),
}

DEFAULT_PRINT_FORMATS = {
    "Sales Order": "Sales Order",
    "Withholding Tax Cert": "Withholding Tax Cert",
}


def get_actions(doctype: str) -> tuple[PrintAction, ...]:
    """Return the registered print actions for a DocType."""
    return PRINT_ACTIONS.get(doctype, ())


def _field(
    fieldname: str,
    fieldtype: str,
    label: str,
    **extra: int | str,
) -> dict[str, int | str]:
    return {
        "fieldname": fieldname,
        "label": label,
        "fieldtype": fieldtype,
        "hidden": 1,
        "read_only": 1,
        "allow_on_submit": 1,
        "no_copy": 1,
        "is_system_generated": 1,
        **extra,
    }


def _fields_for_action(
    action: PrintAction,
) -> tuple[
    dict[str, int | str],
    dict[str, int | str],
    dict[str, int | str],
]:
    """Build the hidden Employee, Datetime, and Signature fields for one action."""
    label = action.key.replace("_", " ").title()
    return (
        _field(
            action.employee_field,
            "Link",
            f"Print Action: {label} By",
            options="Employee",
            ignore_user_permissions=int(action.ignore_employee_user_permissions),
        ),
        _field(
            action.datetime_field,
            "Datetime",
            f"Print Action: {label} At",
        ),
        _field(
            action.signature_field,
            "Signature",
            f"Print Action: {label} Signature",
        ),
    )


CUSTOM_FIELDS = {
    doctype: [field for action in actions for field in _fields_for_action(action)]
    for doctype, actions in PRINT_ACTIONS.items()
}
for _field_definition in CUSTOM_FIELDS["Payroll Entry"]:
    if _field_definition["fieldtype"] == "Link":
        _field_definition["ignore_user_permissions"] = 1


def apply_configuration() -> None:
    """Create or update the hidden fields and print defaults during install and migrate."""
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
    for doctype, print_format in DEFAULT_PRINT_FORMATS.items():
        make_property_setter(
            doctype,
            None,
            "default_print_format",
            print_format,
            "Data",
            for_doctype=True,
            validate_fields_for_doctype=False,
        )
        frappe.clear_cache(doctype=doctype)
