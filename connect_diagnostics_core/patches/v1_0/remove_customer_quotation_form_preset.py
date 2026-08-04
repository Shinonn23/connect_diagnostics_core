# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Remove the retired Customer Quotation Form Preset custom field."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields

RETIRED_CUSTOMER_FIELDS = ("quotation_form_preset",)


def execute() -> None:
    """Delete the legacy preset field after the Template schema has synchronized."""
    delete_custom_fields({"Customer": list(RETIRED_CUSTOMER_FIELDS)}, bypass_hooks=True)
    frappe.clear_cache()
