# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Custom field definitions for DKSH Sales Order processing."""

from connect_diagnostics_core.config.dksh import (
    DKSH_COMPANY,
    SAP_KEYED_BY_FIELD,
    SAP_KEYED_ON_FIELD,
    SAP_ORDER_CORRECTION_REASON_FIELD,
    SAP_ORDER_NO_FIELD,
    SAP_ORDER_STATUS_FIELD,
    SAP_ORDER_STATUS_KEYED,
    SAP_ORDER_STATUS_PENDING,
)

DKSH_COMPANY_DEPENDS_ON = f"eval:doc.company=='{DKSH_COMPANY}'"

CUSTOM_FIELDS = {
    "Sales Order": [
        {
            "fieldname": "sap_order_section",
            "label": "SAP Keying",
            "fieldtype": "Section Break",
            "insert_after": "more_info",
            "depends_on": DKSH_COMPANY_DEPENDS_ON,
        },
        {
            "fieldname": SAP_ORDER_STATUS_FIELD,
            "label": "SAP Order Status",
            "fieldtype": "Select",
            "options": f"{SAP_ORDER_STATUS_PENDING}\n{SAP_ORDER_STATUS_KEYED}",
            "insert_after": "sap_order_section",
            "allow_on_submit": 1,
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": SAP_ORDER_NO_FIELD,
            "label": "SAP Order No.",
            "fieldtype": "Data",
            "insert_after": SAP_ORDER_STATUS_FIELD,
            "allow_on_submit": 1,
            "read_only": 1,
            "no_copy": 1,
            "in_list_view": 1,
            "in_standard_filter": 1,
            "search_index": 1,
        },
        {
            "fieldname": SAP_KEYED_BY_FIELD,
            "label": "SAP Keyed By",
            "fieldtype": "Link",
            "options": "User",
            "insert_after": SAP_ORDER_NO_FIELD,
            "allow_on_submit": 1,
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": SAP_KEYED_ON_FIELD,
            "label": "SAP Keyed On",
            "fieldtype": "Datetime",
            "insert_after": SAP_KEYED_BY_FIELD,
            "allow_on_submit": 1,
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": SAP_ORDER_CORRECTION_REASON_FIELD,
            "label": "SAP Order Correction Reason",
            "fieldtype": "Small Text",
            "insert_after": SAP_KEYED_ON_FIELD,
            "allow_on_submit": 1,
            "read_only": 1,
            "no_copy": 1,
            "depends_on": f"eval:doc.{SAP_ORDER_STATUS_FIELD}=='{SAP_ORDER_STATUS_KEYED}'",
        },
    ],
}

PROPERTY_SETTERS: dict[str, list[tuple[str | None, str, str, str]]] = {}
