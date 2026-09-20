# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


def validate_material_request(doc: Document, _method: str | None = None) -> None:
    if not doc.get("purchase_reason"):
        frappe.throw(_("Request Reason is required."))
