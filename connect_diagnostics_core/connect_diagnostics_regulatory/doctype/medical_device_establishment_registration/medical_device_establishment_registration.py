# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class MedicalDeviceEstablishmentRegistration(Document):
    """Company establishment registration used by product registrations."""

    def validate(self) -> None:
        issue_date = getdate(cast(str, self.get("issue_date") or ""))
        expiry_date = getdate(cast(str, self.get("expiry_date") or ""))
        if issue_date and expiry_date and expiry_date < issue_date:
            frappe.throw(_("Expiry Date must be on or after Issue Date."))
