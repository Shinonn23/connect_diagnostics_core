# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core.setup.payment_approval import (
    CUSTOM_FIELDS,
    assign_payment_approvers,
    ensure_configuration,
)


def execute() -> None:
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
    ensure_configuration()
    assign_payment_approvers()
    frappe.clear_cache()
