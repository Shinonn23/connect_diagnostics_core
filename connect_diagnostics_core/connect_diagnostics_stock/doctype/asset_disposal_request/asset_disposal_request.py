# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.erpnext import asset_disposal_workflow


class AssetDisposalRequest(Document):
    def validate(self) -> None:
        asset_disposal_workflow.validate_request(self)

    def before_submit(self) -> None:
        asset_disposal_workflow.validate_request_submit(self)

    def before_update_after_submit(self) -> None:
        asset_disposal_workflow.validate_submitted_request_update(self)

    def before_cancel(self) -> None:
        frappe.throw(_("An approved Asset Disposal Request cannot be cancelled."))

    def on_trash(self) -> None:
        asset_disposal_workflow.validate_request_delete(self)
