# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Protected parent of an exact-location physical stock count."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.connect_diagnostics_stock.doctype.storage_location.storage_location import (
    require_operational_warehouse,
)

_PROTECTED = frozenset(
    {
        "description",
        "reason",
        "source_emergency_stock_entry",
        "workflow_state",
        "locations",
        "items",
        "cutoff_datetime",
        "frozen_at",
        "evidence_revision",
        "snapshot_digest",
        "approved_digest",
        "count_complete",
        "has_variance",
        "evidence_invalidated",
        "invalidation_reason",
        "invalidation_stock_entry",
        "invalidation_at",
        "posting_policy",
        "posting_date",
        "posting_time",
        "posted_at",
        "closed_at",
        "cancelled_at",
        "accounting_review_required",
        "accounting_predicate_revision",
        "accounting_settings_digest",
        "accounting_candidate_digest",
        "accounting_reviewed_digest",
        "cancel_accounting_required",
        "cancel_request_user",
        "cancel_request_at",
        "cancel_reason",
        "cancel_gl_digest",
        "cancel_accounts_user",
        "cancel_accounts_employee",
        "cancel_accounts_at",
        "cancel_accounts_digest",
        "decision_reason",
        "decision_actor",
        "decision_at",
        "pending_reason_action",
        "pending_reason_actor",
        "pending_reason_state",
        "pending_reason_revision",
        "pending_reason_digest",
        "pending_reason_text",
        "pending_reason_at",
        "terminal_reason",
    }
    | {
        f"{actor}_{suffix}"
        for actor in ("maker", "checker", "stock_approver", "accounts_approver")
        for suffix in ("user", "employee", "at")
    }
)


class StockCountSession(Document):
    def before_insert(self) -> None:
        if self.docstatus != 0 or self.get("workflow_state") not in (None, "", "Draft"):
            frappe.throw(_("A new Count Session must start in Draft."))
        if any(
            self.get(field)
            for field in _PROTECTED
            if field not in {"posting_policy", "description", "reason"}
        ):
            frappe.throw(_("A new Count Session cannot contain protected evidence."))
        self._validate_draft_scope()
        self.workflow_state = "Draft"

    def validate(self) -> None:
        if self.get("scope_type") not in {"Full", "Cycle"}:
            frappe.throw(_("Choose a Full or Cycle Count scope."))
        if not self.get("company") or not frappe.db.exists("Company", self.get("company")):
            frappe.throw(_("Select an existing Company for the Count Session."))
        if self.get("workflow_state") == "Draft":
            self._validate_draft_scope()
        before = self.get_doc_before_save()
        if before is None:
            return
        grant = getattr(frappe.local, "_stock_count_parent_grant", None)
        permitted: set[str] = (
            {str(field) for field in grant.get("fields") or ()}
            if isinstance(grant, dict) and grant.get("document") is self and not grant.get("consumed")
            else set()
        )
        for field in _PROTECTED | {"scope", "company", "scope_type", "linked_recount_of"}:
            if field in {"scope", "company", "scope_type", "linked_recount_of", "description", "reason"} and (
                before.workflow_state == "Draft" and self.workflow_state == "Draft"
            ):
                continue
            changed = (
                not self.is_child_table_same(field)
                if field in {"scope", "locations", "items"}
                else self.get(field) != before.get(field)
            )
            if changed and field not in permitted:
                frappe.throw(_("Count Session evidence may change only through its approved action."))
        if self.workflow_state != "Draft" and not self.is_child_table_same("scope"):
            if "scope" not in permitted:
                frappe.throw(_("A frozen Count scope cannot be edited."))
        self._validate_table_integrity(before, permitted)
        if permitted:
            assert isinstance(grant, dict)
            grant["consumed"] = True

    def _validate_table_integrity(self, before: Document, permitted: set[str]) -> None:
        immutable: dict[str, frozenset[str]] = {
            "scope": frozenset({"scope_kind", "warehouse", "item_code", "company"}),
            "locations": frozenset(
                {"scope_row", "company", "warehouse", "storage_location", "evidence_revision"}
            ),
            "items": frozenset(
                {
                    "line_key",
                    "item_code",
                    "company",
                    "warehouse",
                    "storage_location",
                    "stock_uom",
                    "batch_no",
                    "serial_no",
                    "evidence_revision",
                    "system_qty",
                    "current_valuation_rate",
                    "snapshot_at",
                    "snapshot_digest",
                    "baseline_source",
                }
            ),
        }
        old_revision = int(before.get("evidence_revision") or 0)
        for table, fixed_fields in immutable.items():
            old_rows = {str(row.name): row for row in before.get(table) or []}
            new_rows = {str(row.name): row for row in self.get(table) or [] if row.name}
            if len(new_rows) != len([row for row in self.get(table) or [] if row.name]):
                frappe.throw(_("Count evidence has duplicate child row identities."))
            if before.get("workflow_state") != "Draft" and not set(old_rows) <= set(new_rows):
                frappe.throw(_("Frozen Count evidence rows cannot be removed."))
            for name, old in old_rows.items():
                new = new_rows.get(name)
                if new is None:
                    continue  # Draft scope selection may remove an unactivated row.
                if any(old.get(field) != new.get(field) for field in fixed_fields):
                    if table != "scope" or before.get("workflow_state") != "Draft":
                        frappe.throw(_("Frozen Count identity and baseline fields are immutable."))
                if table in {"locations", "items"} and int(old.get("evidence_revision") or 0) < old_revision:
                    old_values = old.as_dict(convert_dates_to_str=True)
                    new_values = new.as_dict(convert_dates_to_str=True)
                    for bookkeeping in ("modified", "modified_by", "creation"):
                        old_values.pop(bookkeeping, None)
                        new_values.pop(bookkeeping, None)
                    if old_values != new_values:
                        frappe.throw(_("Earlier Count revision evidence cannot be changed."))
            if table in {"locations", "items"}:
                appended = [row for row in self.get(table) or [] if not row.name]
                if appended and (
                    table not in permitted
                    or any(
                        int(row.get("evidence_revision") or 0) != int(self.get("evidence_revision") or 0)
                        for row in appended
                    )
                ):
                    frappe.throw(_("New Count evidence rows require the current capture action."))

    def _validate_draft_scope(self) -> None:
        company = str(self.get("company") or "")
        if not company:
            frappe.throw(_("Select a Company before entering the Count scope."))
        company_doc = frappe.get_doc("Company", company)
        if not frappe.has_permission("Company", ptype="read", doc=company_doc, user=frappe.session.user):
            raise frappe.PermissionError(_("You cannot count stock for this Company."))
        kind = self.get("scope_type")
        expected = "Warehouse" if kind == "Full" else "Item/Warehouse"
        rows = self.get("scope") or []
        if not rows:
            frappe.throw(_("Add at least one Warehouse to the Count scope."))
        seen: set[tuple[str, str]] = set()
        for row in rows:
            warehouse = str(row.get("warehouse") or "")
            item_code = str(row.get("item_code") or "")
            if row.get("scope_kind") != expected or bool(item_code) != (kind == "Cycle"):
                frappe.throw(_("Count scope kind and Item do not match the selected mode."))
            if row.get("company") not in (None, "", company):
                frappe.throw(_("Count scope Company does not match its Session."))
            row.company = company
            if any(
                row.get(field)
                for field in (
                    "snapshot_revision",
                    "cutoff_datetime",
                    "freeze_active",
                    "activated_at",
                    "released_at",
                )
            ) or row.get("lease_state") not in (None, ""):
                frappe.throw(_("Count lease fields are written only by the server."))
            if not warehouse or (warehouse, item_code) in seen:
                frappe.throw(_("Count Warehouse/Item scope rows must be distinct."))
            seen.add((warehouse, item_code))
            require_operational_warehouse(warehouse)
            warehouse_doc = frappe.get_doc("Warehouse", warehouse)
            if warehouse_doc.get("company") != company:
                frappe.throw(_("Count Warehouse must belong to the selected Company."))
            if not frappe.has_permission(
                "Warehouse", ptype="read", doc=warehouse_doc, user=frappe.session.user
            ):
                raise frappe.PermissionError(_("You cannot count stock in this Warehouse."))
            if item_code:
                item_doc = frappe.get_doc("Item", item_code)
                if not item_doc.get("is_stock_item"):
                    frappe.throw(_("Cycle Count requires a stock Item."))
                if not frappe.has_permission("Item", ptype="read", doc=item_doc, user=frappe.session.user):
                    raise frappe.PermissionError(_("You cannot count this Item."))

    def before_submit(self) -> None:
        self._require_transition("Closed", "submit")

    def before_cancel(self) -> None:
        self._require_transition("Cancelled", "cancel")

    def on_trash(self) -> None:
        if self.get("evidence_revision") or self.get("workflow_state") != "Draft":
            frappe.throw(_("A Count Session with evidence cannot be deleted."))

    def _require_transition(self, state: str, phase: str) -> None:
        proof = getattr(frappe.local, "_stock_count_session_transition_proof", None)
        if (
            self.get("workflow_state") != state
            or not isinstance(proof, dict)
            or proof.get("document") is not self
            or proof.get("phase") != phase
            or proof.get("consumed")
        ):
            frappe.throw(_("Count Session must use its approved native Workflow action."))
        assert isinstance(proof, dict)
        proof["consumed"] = True
