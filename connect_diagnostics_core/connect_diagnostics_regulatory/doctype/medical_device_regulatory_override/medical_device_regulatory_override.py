# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from connect_diagnostics_core.setup.regulatory import REGULATORY_APPROVER

TRANSACTION_DOCTYPES = frozenset(
    {"Purchase Order", "Purchase Receipt", "Stock Entry", "Sales Order", "Delivery Note", "Sales Invoice"}
)


class MedicalDeviceRegulatoryOverride(Document):
    """A document-bound exception; approval never changes the original policy snapshot."""

    def validate(self) -> None:
        if self.get("transaction_doctype") not in TRANSACTION_DOCTYPES:
            frappe.throw(
                _("Medical Device Regulatory Override must reference a supported transaction DocType.")
            )
        previous = self.get_doc_before_save()
        previous_status = cast(str, previous.get("status") or "") if previous else ""
        current_status = cast(str, self.get("status") or "")
        if self.is_new():
            self.set("requested_by", frappe.session.user)
            self.set("requested_on", today())
        if current_status != "Approved" or previous_status == "Approved":
            return
        if frappe.session.user != "Administrator" and REGULATORY_APPROVER not in frappe.get_roles():
            frappe.throw(_("Only a Regulatory Approver can approve a medical-device regulatory override."))
        if self.get("requested_by") == frappe.session.user:
            frappe.throw(_("The requester cannot approve the same medical-device regulatory override."))
        self.set("approved_by", frappe.session.user)
        self.set("approved_on", today())
