# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class MedicalDeviceRegulatoryDocument(Document):
    """Versioned supporting evidence; expiry is independent from registration expiry."""

    def validate(self) -> None:
        issue_date = getdate(cast(str, self.get("issue_date") or ""))
        expiry_date = getdate(cast(str, self.get("expiry_date") or ""))
        if issue_date and expiry_date and expiry_date < issue_date:
            frappe.throw(_("Document Expiry Date must be on or after Issue Date."))
        if self.get("verification_status") == "Verified":
            self.set("verified_by", frappe.session.user)
            self.set("verified_on", today())
        else:
            self.set("verified_by", None)
            self.set("verified_on", None)
