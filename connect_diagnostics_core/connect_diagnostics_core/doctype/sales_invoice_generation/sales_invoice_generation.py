# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""System-owned, one-invoice-per-source-group progress record."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from secrets import token_urlsafe

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.types import DF

_IMMUTABLE = frozenset(
    {
        "source_doctype",
        "source_name",
        "sales_order",
        "billing_authority_revision",
        "group_kind",
        "group_key",
        "source_rows_json",
        "source_digest",
        "billing_authority_digest",
        "initiated_by",
        "target_sales_invoice",
    }
)
_PROGRESS = frozenset(
    {
        "expected_invoice_payload_digest",
        "generation_status",
        "attempt_count",
        "last_error",
        "failure_code",
        "target_sales_invoice",
        "generated_at",
    }
)
_PROOF: ContextVar[tuple[int, str, str, bool] | None] = ContextVar(
    "sales_invoice_generation_write", default=None
)


@contextmanager
def _system_write(doc: Document, stage: str) -> Iterator[None]:
    """Bind one generator call to one concrete Document, never a session flag."""
    if stage not in {"insert", "update"}:
        frappe.throw(_("Invalid Sales Invoice Generation write stage."))
    token = _PROOF.set((id(doc), token_urlsafe(24), stage, False))
    prior = doc.flags.get("ignore_permissions")
    try:
        doc.flags.ignore_permissions = True
        yield
    finally:
        doc.flags.ignore_permissions = prior
        _PROOF.reset(token)


def _check(doc: Document, stage: str, *, consume: bool = False) -> None:
    proof = _PROOF.get()
    if proof is None or proof[0] != id(doc) or proof[2] != stage or proof[3]:
        raise frappe.PermissionError(_("Sales Invoice Generation is system-owned."))
    if consume:
        _PROOF.set((proof[0], proof[1], proof[2], True))


class SalesInvoiceGeneration(Document):
    source_doctype: DF.Literal["Sales Order", "Delivery Note"]
    source_name: DF.DynamicLink
    sales_order: DF.Link
    billing_authority_revision: DF.Data
    billing_authority_digest: DF.Data
    group_kind: DF.Literal["SO Service", "DN Stock"]
    source_rows_json: DF.LongText
    source_digest: DF.Data
    generation_status: DF.Literal[
        "Queued",
        "Pending Permission",
        "Failed",
        "Legacy Authority Hold",
        "Generated",
        "Generated SI Cancelled",
    ]
    failure_code: (
        DF.Literal[
            "Allocation Required",
            "Source Authority Mismatch",
            "Cross-route Fixed Pool Unsupported",
            "Legacy Authority Hold",
        ]
        | None
    )
    attempt_count: DF.Int
    last_error: DF.SmallText | None
    target_sales_invoice: DF.Link | None
    generated_at: DF.Datetime | None

    def before_insert(self) -> None:
        _check(self, "insert", consume=True)

    def validate(self) -> None:
        stage = "insert" if self.is_new() else "update"
        # Frappe validates again after before_insert; only the terminal hook consumes.
        proof = _PROOF.get()
        if stage == "insert" and proof and proof[0] == id(self) and proof[3]:
            return
        _check(self, stage)
        if stage == "update":
            previous = self.get_doc_before_save()
            if previous is None:
                frappe.throw(_("Sales Invoice Generation requires current persisted state."))
            for field in _IMMUTABLE - {"target_sales_invoice"}:
                if self.get(field) != previous.get(field):
                    frappe.throw(_("Sales Invoice Generation source authority cannot change."))
            old_target = previous.get("target_sales_invoice")
            if old_target and self.get("target_sales_invoice") != old_target:
                frappe.throw(_("The generated Sales Invoice link is permanent."))
            for field in self.meta.get_valid_columns():
                if field not in _PROGRESS and field not in {"name", "modified", "modified_by"}:
                    if self.get(field) != previous.get(field):
                        frappe.throw(_("Sales Invoice Generation source authority cannot change."))

    def before_save(self) -> None:
        if self.is_new():
            proof = _PROOF.get()
            if proof is None or proof[0] != id(self) or proof[2] != "insert" or not proof[3]:
                frappe.throw(_("Sales Invoice Generation insert proof is missing."), frappe.PermissionError)
            return
        _check(self, "update", consume=True)

    def on_update(self) -> None:
        proof = _PROOF.get()
        if proof is None or proof[0] != id(self) or not proof[3]:
            frappe.throw(_("Sales Invoice Generation write proof was not consumed."), frappe.PermissionError)
