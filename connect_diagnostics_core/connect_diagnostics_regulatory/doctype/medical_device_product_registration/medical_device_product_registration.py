# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, today

from connect_diagnostics_core.api.erpnext import regulatory
from connect_diagnostics_core.api.erpnext.regulatory import normalize_registration_number


class MedicalDeviceProductRegistration(Document):
    """Source of truth for one FDA product registration and its effective mappings."""

    def validate(self) -> None:
        self._normalize_number()
        self._validate_dates()
        self._validate_successor_links()
        self._validate_registered_product_rows()
        self._validate_effective_mapping_overlaps()
        self._validate_active_certificate()

    def on_update(self) -> None:
        """Refresh stored Item coverage after a master mapping or status changes."""
        previous = self.get_doc_before_save()
        prior_rows = previous.get("registered_products", []) if previous else []
        item_codes = {
            cast(str, row.get("item_code") or "") for row in self.get("registered_products", [])
        } | {cast(str, row.get("item_code") or "") for row in prior_rows}
        regulatory.refresh_item_coverage_for_items({item_code for item_code in item_codes if item_code})

    def on_trash(self) -> None:
        """Protect master facts used by any submitted inventory or sales transaction."""
        transaction_queries = (
            "SELECT child.parent FROM `tabPurchase Order Item` AS child INNER JOIN `tabPurchase Order` AS parent ON parent.name = child.parent WHERE child.regulatory_registration = %(registration)s AND parent.docstatus = 1 LIMIT 1",
            "SELECT child.parent FROM `tabPurchase Receipt Item` AS child INNER JOIN `tabPurchase Receipt` AS parent ON parent.name = child.parent WHERE child.regulatory_registration = %(registration)s AND parent.docstatus = 1 LIMIT 1",
            "SELECT child.parent FROM `tabStock Entry Detail` AS child INNER JOIN `tabStock Entry` AS parent ON parent.name = child.parent WHERE child.regulatory_registration = %(registration)s AND parent.docstatus = 1 LIMIT 1",
            "SELECT child.parent FROM `tabSales Order Item` AS child INNER JOIN `tabSales Order` AS parent ON parent.name = child.parent WHERE child.regulatory_registration = %(registration)s AND parent.docstatus = 1 LIMIT 1",
            "SELECT child.parent FROM `tabDelivery Note Item` AS child INNER JOIN `tabDelivery Note` AS parent ON parent.name = child.parent WHERE child.regulatory_registration = %(registration)s AND parent.docstatus = 1 LIMIT 1",
            "SELECT child.parent FROM `tabSales Invoice Item` AS child INNER JOIN `tabSales Invoice` AS parent ON parent.name = child.parent WHERE child.regulatory_registration = %(registration)s AND parent.docstatus = 1 LIMIT 1",
        )
        for query in transaction_queries:
            used = frappe.db.sql(query, {"registration": self.name})
            if used:
                frappe.throw(_("A registration used by a submitted transaction cannot be deleted."))

    def _normalize_number(self) -> None:
        registration_number = cast(str, self.get("registration_number") or "").strip()
        if not registration_number:
            frappe.throw(_("Registration Number is required."))
        self.registration_number = registration_number
        self.registration_number_normalized = normalize_registration_number(registration_number)

    def _validate_dates(self) -> None:
        issue_date = getdate(cast(str, self.get("issue_date") or ""))
        expiry_date = getdate(cast(str, self.get("expiry_date") or ""))
        if issue_date and expiry_date and expiry_date < issue_date:
            frappe.throw(_("Expiry Date must be on or after Issue Date."))
        self.days_to_expiry = date_diff(expiry_date, today()) if expiry_date else None

    def _validate_successor_links(self) -> None:
        for fieldname in ("previous_registration", "superseded_by"):
            linked_name = cast(str, self.get(fieldname) or "")
            if linked_name and linked_name == self.name:
                frappe.throw(_("A registration cannot reference itself as {0}.").format(fieldname))

    def _validate_registered_product_rows(self) -> None:
        seen_items: set[tuple[str, str, str]] = set()
        for row in self.get("registered_products", []):
            key = (
                cast(str, row.get("item_code") or ""),
                cast(str, row.get("effective_from") or ""),
                cast(str, row.get("effective_to") or ""),
            )
            if key[0] and key in seen_items:
                frappe.throw(_("Item mappings must not duplicate the same effective date range."))
            seen_items.add(key)
            if row.get("line_status") == "Active" and not (row.get("newcode") or row.get("identifier")):
                frappe.throw(_("An Active Registered Product requires a NEWCODE or Identifier."))
            if row.get("item_code"):
                row.item_name_at_registration = frappe.db.get_value("Item", row.item_code, "item_name") or ""
            effective_from = getdate(cast(str, row.get("effective_from") or ""))
            effective_to = getdate(cast(str, row.get("effective_to") or ""))
            if effective_from and effective_to and effective_to < effective_from:
                frappe.throw(_("Registered Product Effective To must be on or after Effective From."))

    def _validate_effective_mapping_overlaps(self) -> None:
        active_rows = [row for row in self.get("registered_products", []) if row.get("item_code") and row.get("line_status") == "Active"]
        for index, row in enumerate(active_rows):
            for other in active_rows[index + 1 :]:
                if row.item_code == other.item_code and _ranges_overlap(row, other):
                    frappe.throw(_("Active Item mappings must not have overlapping effective date ranges."))
        if self.get("official_status") != "Active":
            return
        for row in active_rows:
            external_rows = frappe.db.sql(
                """
                SELECT product.effective_from, product.effective_to
                FROM `tabMedical Device Registered Product` AS product
                INNER JOIN `tabMedical Device Product Registration` AS registration
                    ON registration.name = product.parent
                WHERE product.item_code = %(item_code)s
                  AND product.line_status = 'Active'
                  AND product.parent != %(registration)s
                  AND registration.official_status = 'Active'
                """,
                {"item_code": row.item_code, "registration": self.name},
                as_dict=True,
            )
            if any(_ranges_overlap(row, external) for external in external_rows):
                frappe.throw(
                    _("Item {0} overlaps an effective mapping on another active registration.").format(
                        frappe.bold(row.item_code)
                    )
                )

    def _validate_active_certificate(self) -> None:
        if self.get("official_status") != "Active":
            return
        certificate_exists = frappe.db.exists(
            "Medical Device Regulatory Document",
            {"registration": self.name, "document_type": "Certificate", "verification_status": "Verified"},
        )
        if not certificate_exists:
            frappe.throw(_("An Active registration requires one verified Certificate document."))


def _ranges_overlap(left: Any, right: Any) -> bool:
    """Treat missing endpoints as open ranges and inclusive endpoints as overlapping."""
    left_start = getdate(left.get("effective_from") or "") or date.min
    left_end = getdate(left.get("effective_to") or "") or date.max
    right_start = getdate(right.get("effective_from") or "") or date.min
    right_end = getdate(right.get("effective_to") or "") or date.max
    return left_start <= right_end and right_start <= left_end
