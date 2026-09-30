# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import hashlib
from typing import Any

import frappe


class ProcessDeferredAccountingWorkflowMixin:
    """Keep native deferred processing while converting generated JE submits to drafts."""

    def on_submit(self: Any) -> None:
        frappe.db.get_value(self.doctype, self.name, "name", for_update=True)
        operation_base_id = hashlib.sha256(f"{self.doctype}:{self.name}".encode()).hexdigest()
        frappe.flags.journal_entry_draft_context = {
            "source_doctype": self.doctype,
            "source_name": self.name,
            "source_action": "process_deferred_accounting",
            "operation_base_id": operation_base_id,
        }
        try:
            super().on_submit()
        finally:
            frappe.flags.pop("journal_entry_draft_context", None)
