# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Request-only sidebar settings owned by the Quotation Print Format."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from connect_diagnostics_core.api.erpnext import company as company_api
from connect_diagnostics_core.connect_diagnostics_print.print_format.settings import (
    GENERIC_COPIES,
    PrintDocument,
    SidebarExtension,
)
from connect_diagnostics_core.setup import quotation as quotation_setup


def quotation_sidebar_extension(docname: str) -> SidebarExtension:
    """Return Quotation-only signatory controls for one print request."""
    quotation_values = (
        frappe.db.get_value("Quotation", docname, ["company", "quotation_signatory_type"], as_dict=True) or {}
    )
    signatory_type = str(quotation_values.get("quotation_signatory_type") or "").strip()
    manager_signatories = tuple(
        company_api.get_quotation_authorized_signatories(str(quotation_values.get("company") or "").strip())
    )
    fields: tuple[dict[str, Any], ...] = (
        {
            "fieldname": "quotation_signatory_type",
            "label": _("Signatory"),
            "fieldtype": "Select",
            "options": "\n".join(quotation_setup.SIGNATORY_TYPES),
        },
        {
            "fieldname": "manager_signatory_employee",
            "label": _("Manager Signatory"),
            "fieldtype": "Select",
            "options": "\n"
            + "\n".join(
                str(row.get("employee") or "").strip() for row in manager_signatories if row.get("employee")
            ),
            "option_labels": {
                str(row.get("employee") or "").strip(): str(
                    row.get("name") or row.get("employee") or ""
                ).strip()
                for row in manager_signatories
                if row.get("employee")
            },
            "depends_on": "eval:cd_quotation_signatory_type=='Managing Director'",
            "mandatory_depends_on": "eval:cd_quotation_signatory_type=='Managing Director'",
            "description": _("Only Employees in this Company's authorized signatory list can be selected."),
        },
    )
    values: dict[str, Any] = {}
    if signatory_type:
        values["quotation_signatory_type"] = signatory_type
    return SidebarExtension(fields=fields, values=values, manager_signatories=manager_signatories)


PRINT_DOCUMENT = PrintDocument(
    key="quotation",
    label="Quotation",
    print_formats=("ใบเสนอราคา",),
    doctypes=("Quotation",),
    language_selectable=True,
    offers_batch_serial=False,
    copies=GENERIC_COPIES,
    defaults={
        "customer_print_name": "",
        "quotation_signatory_type": quotation_setup.SIGNATORY_SALES_REPRESENTATIVE,
        "manager_signatory_employee": "",
        "edit_validity_text": 0,
        "validity_text": "",
        "quotation_delivery_terms": "",
    },
    extra_fields=("quotation_signatory_type", "manager_signatory_employee"),
    document_fields=(
        "quotation_signatory_type",
        "sales_representative_employee",
        "edit_validity_text",
        "validity_text",
        "quotation_delivery_terms",
    ),
    sidebar_extension=quotation_sidebar_extension,
)
