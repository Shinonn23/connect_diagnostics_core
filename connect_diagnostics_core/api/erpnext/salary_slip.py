# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Submission guard restricting Salary Slip submission to Payroll Entry."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.hrms import payroll_output_review as output


def validate_creation(doc: Document, _method: str | None = None) -> None:
    """Recheck the approved batch before queued workers create draft slips."""
    payroll_entry = str(doc.get("payroll_entry") or "")
    if not payroll_entry:
        return
    from connect_diagnostics_core.api.hrms.payroll_entry_workflow import (
        validate_downstream_operation,
    )

    pe = validate_downstream_operation(payroll_entry)
    if pe.get("workflow_state") != output.SUBMITTED:
        raise frappe.PermissionError(
            _("Salary Slip creation requires the unreviewed submitted Payroll Entry.")
        )
    output.require_native_operation(payroll_entry, "create")


def validate_calculated_save(doc: Document, _method: str | None = None) -> None:
    """Keep reviewed native calculation immutable through save and update."""
    del _method
    payroll_entry = str(doc.get("payroll_entry") or "")
    if not payroll_entry:
        return
    pe = output.locked_payroll_entry(payroll_entry)
    if pe.get("workflow_state") == output.SUBMITTED:
        return
    if pe.get("workflow_state") == output.CANCELLED and int(pe.docstatus or 0) == 2:
        return
    if pe.get("workflow_state") not in {output.REVIEWED, output.CLOSED}:
        raise frappe.PermissionError(_("Salary Slip Payroll Entry state is invalid."))
    if pe.get("workflow_state") == output.CLOSED:
        raise frappe.PermissionError(_("Closed payroll Salary Slips cannot be edited."))
    previous = frappe.get_doc("Salary Slip", doc.name)
    dimensions = sorted(str(field) for field in output.get_accounting_dimensions())
    if output._slip_payload(doc, dimensions) != output._slip_payload(previous, dimensions):
        raise frappe.PermissionError(_("Reviewed payroll calculated output cannot be edited."))
    output.require_output_review(pe)


def validate_submission(doc: Document, _method: str | None = None) -> None:
    """Allow Salary Slip submission only through a Payroll Entry batch."""
    if not frappe.flags.via_payroll_entry:
        frappe.throw(
            _("Salary Slips can only be submitted from Payroll Entry."),
            title=_("Submit from Payroll Entry"),
        )
    payroll_entry = str(doc.get("payroll_entry") or "")
    if not payroll_entry:
        frappe.throw(_("Salary Slip submission requires its approved Payroll Entry."))
    from connect_diagnostics_core.api.hrms.payroll_entry_workflow import (
        validate_downstream_operation,
    )

    output.require_native_operation(payroll_entry, "submit")
    pe = validate_downstream_operation(payroll_entry, require_current_digest=False)
    if pe.get("workflow_state") != output.REVIEWED:
        raise frappe.PermissionError(_("Salary Slip submission requires reviewed calculated payroll."))
    active = output.require_output_review(pe, allow_queued=True)
    candidates = [doc if slip.name == doc.name else slip for slip in active]
    if not any(slip.name == doc.name for slip in active):
        raise frappe.PermissionError(_("Salary Slip is outside the reviewed payroll roster."))
    if output.output_digest(pe, candidates) != pe.get("output_review_digest"):
        raise frappe.PermissionError(
            _("Salary Slip native recalculation changed the reviewed payroll output.")
        )


def validate_cancel_or_delete(doc: Document, _method: str | None = None) -> None:
    """Native Payroll Entry cancellation is the only linked Slip removal route."""
    del _method
    payroll_entry = str(doc.get("payroll_entry") or "")
    if not payroll_entry:
        return
    row = frappe.db.get_value(
        "Payroll Entry",
        payroll_entry,
        ["docstatus", "workflow_state"],
        as_dict=True,
        for_update=True,
        wait=False,
    )
    if not row or int(row.docstatus or 0) != 2 or row.workflow_state != output.CANCELLED:
        raise frappe.PermissionError(
            _("Linked Salary Slips may only be removed by Payroll Entry cancellation.")
        )
