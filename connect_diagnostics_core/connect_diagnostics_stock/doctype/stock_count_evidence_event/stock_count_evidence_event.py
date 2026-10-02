# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Immutable Count revision and decision audit event."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext.stock_count_session_workflow import (
    validate_append_only_evidence,
)


class StockCountEvidenceEvent(Document):
    def before_insert(self) -> None:
        validate_append_only_evidence(self, "before_insert")

    def validate(self) -> None:
        if not self.is_new():
            frappe.throw(_("Count evidence events cannot be edited."))

    def on_trash(self) -> None:
        frappe.throw(_("Count evidence events cannot be deleted."))
