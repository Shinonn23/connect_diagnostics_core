# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from typing import cast

import frappe
from frappe import _
from frappe.model.document import Document


class MedicalDeviceRegistrationAction(Document):
    """Renewal, variation, and amendment history without overwriting registration data."""

    def validate(self) -> None:
        current_stage = cast(str, self.get("current_stage") or "")
        if current_stage == "FDA Query" and not self.get("response_due_date"):
            frappe.throw(_("FDA Query stage requires a Response Due Date."))
        if current_stage == "Approved" and not self.get("approval_date"):
            frappe.throw(_("Approved stage requires an Approval Date."))
        if current_stage == "Approved" and not (
            self.get("resulting_registration") or self.get("new_expiry_date")
        ):
            frappe.throw(_("Approved stage requires a Resulting Registration or New Expiry Date."))
        resulting_registration = cast(str, self.get("resulting_registration") or "")
        if current_stage == "Approved" and resulting_registration:
            previous_registration = cast(
                str,
                frappe.db.get_value(
                    "Medical Device Product Registration", resulting_registration, "previous_registration"
                )
                or "",
            )
            if previous_registration and previous_registration != self.get("registration"):
                frappe.throw(
                    _("The resulting registration is already linked to a different previous registration.")
                )

    def on_update(self) -> None:
        """Link an approved successor without replacing the historical registration record."""
        if self.get("current_stage") != "Approved" or not self.get("resulting_registration"):
            return
        resulting_registration = cast(str, self.get("resulting_registration"))
        registration = cast(str, self.get("registration"))
        frappe.db.set_value(
            "Medical Device Product Registration",
            resulting_registration,
            "previous_registration",
            registration,
            update_modified=False,
        )
        frappe.db.set_value(
            "Medical Device Product Registration",
            registration,
            "superseded_by",
            resulting_registration,
            update_modified=False,
        )
