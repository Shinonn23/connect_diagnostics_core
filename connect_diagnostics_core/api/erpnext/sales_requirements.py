# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Enforce what a Customer requires before a sale can proceed.

A Customer records two process requirements of its own (see
:mod:`connect_diagnostics_core.setup.customer`):

``quotation_required``
    the order must come from a Quotation, so a Sales Order with no linked
    Quotation is rejected

``source_purchase_order_copy_required``
    the tax invoice must carry a copy of the Purchase Order we placed with our
    supplier, so a Sales Invoice must either link that Purchase Order or attach
    the file for one raised before ERPNext

Both are gates, not print settings: they say what has to exist, while
:mod:`connect_diagnostics_core.api.erpnext.print_configuration` says how the
resulting documents print. A user holding
:data:`~connect_diagnostics_core.setup.sales_requirements.OVERRIDE_ROLE` may
proceed anyway by writing a reason, which stays on the document as the audit
trail.

Every evaluator takes a ``Document`` or a plain mapping so the same rules serve
one form and a whole report page without a query per row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from connect_diagnostics_core.setup.sales_requirements import OVERRIDE_ROLE

REQUIREMENT_FIELDS = ("quotation_required", "source_purchase_order_copy_required")

GATED_DOCTYPES = ("Sales Order", "Sales Invoice")


def get_customer_requirements(customer: str) -> dict[str, int]:
    """Return one Customer's requirements, defaulting to none required."""
    return get_customer_requirements_map([customer]).get(customer, _no_requirements())


def get_customer_requirements_map(customers: Sequence[str]) -> dict[str, dict[str, int]]:
    """Return requirements for many Customers in a single query.

    A deployment can serve requests after the app code updates but before
    migration creates the Customer fields; restricting the query to installed
    fields keeps those requests on "nothing required" instead of erroring.
    """
    names = sorted({name for name in customers if name})
    if not names:
        return {}

    available = _available_requirement_fields()
    if not available:
        return {name: _no_requirements() for name in names}

    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            "Customer",
            filters={"name": ["in", names]},
            fields=["name", *available],
        ),
    )
    requirements = {name: _no_requirements() for name in names}
    for row in rows:
        requirements[cast(str, row["name"])] = {
            fieldname: cint(row.get(fieldname)) for fieldname in REQUIREMENT_FIELDS
        }
    return requirements


def evaluate_sales_order(
    doc: Document | Mapping[str, Any],
    requirements: Mapping[str, int] | None = None,
) -> list[str]:
    """Return what a Sales Order still needs for this Customer."""
    resolved = requirements if requirements is not None else _requirements_for(doc)
    if not cint(resolved.get("quotation_required")):
        return []
    if _has_linked_quotation(doc):
        return []
    return [_("a Quotation this order was raised from")]


def evaluate_sales_invoice(
    doc: Document | Mapping[str, Any],
    requirements: Mapping[str, int] | None = None,
) -> list[str]:
    """Return what a Sales Invoice still needs for this Customer."""
    resolved = requirements if requirements is not None else _requirements_for(doc)
    if not cint(resolved.get("source_purchase_order_copy_required")):
        return []
    if _text(doc.get("source_purchase_order")) or _text(doc.get("source_purchase_order_file")):
        return []
    return [_("the source Purchase Order, either linked or attached as a file")]


def evaluate(doc: Document | Mapping[str, Any]) -> list[str]:
    """Return the gaps for whichever gated DocType this is."""
    doctype = _text(doc.get("doctype"))
    if doctype == "Sales Order":
        return evaluate_sales_order(doc)
    if doctype == "Sales Invoice":
        return evaluate_sales_invoice(doc)
    return []


def validate(doc: Document, method: str | None = None) -> None:
    """Block a document that skips what its Customer requires.

    A holder of the override Role may proceed after writing a reason. Anyone
    else is stopped with the list of what is missing.
    """
    gaps = evaluate(doc)
    if not gaps:
        doc.set("requirement_override_reason", None)
        return

    missing = ", ".join(gaps)
    if OVERRIDE_ROLE not in frappe.get_roles():
        frappe.throw(
            _("{0} requires {1}.").format(_customer_label(doc), missing),
            title=_("Customer requirement not met"),
        )

    if not _text(doc.get("requirement_override_reason")):
        frappe.throw(
            _("{0} requires {1}. Enter a Requirement Override Reason to proceed without it.").format(
                _customer_label(doc), missing
            ),
            title=_("Requirement override reason needed"),
        )

    frappe.msgprint(
        _("Proceeding without {0}, which {1} requires.").format(missing, _customer_label(doc)),
        title=_("Customer requirement overridden"),
        indicator="orange",
    )


@frappe.whitelist()
def get_transaction_requirements(doc: str | dict[str, Any]) -> dict[str, Any]:
    """Return what a document still needs, for the form to show before saving.

    Takes the form's document rather than a name so an unsaved Sales Order shows
    the requirement while it can still be met, instead of only meeting the gate
    as a save error. The requirements themselves are read from the Customer, so a
    doctored payload can only mislead whoever sent it.
    """
    values = cast(dict[str, Any], frappe.parse_json(doc) if isinstance(doc, str) else doc)
    doctype = _text(values.get("doctype"))
    if doctype not in GATED_DOCTYPES:
        return {"data": {"gaps": [], "can_override": False}}

    frappe.has_permission(doctype, "read", throw=True)
    gaps = evaluate(values)
    return {
        "data": {
            "gaps": gaps,
            "can_override": OVERRIDE_ROLE in frappe.get_roles(),
        },
        "message": _("{0} requires {1}.").format(_customer_label(values), ", ".join(gaps))
        if gaps
        else "",
    }


def _requirements_for(doc: Document | Mapping[str, Any]) -> dict[str, int]:
    customer = _text(doc.get("customer"))
    return get_customer_requirements(customer) if customer else _no_requirements()


def _has_linked_quotation(doc: Document | Mapping[str, Any]) -> bool:
    """Report whether any order line came from a Quotation.

    ``prevdoc_docname`` is the standard ERPNext link a Sales Order Item keeps to
    the Quotation it was mapped from.
    """
    items = cast(Sequence[Any], doc.get("items") or ())
    return any(_text(_row_value(item, "prevdoc_docname")) for item in items)


def _row_value(row: Any, fieldname: str) -> Any:
    getter = getattr(row, "get", None)
    return getter(fieldname) if callable(getter) else getattr(row, fieldname, None)


def _customer_label(doc: Document | Mapping[str, Any]) -> str:
    return _text(doc.get("customer_name")) or _text(doc.get("customer")) or _("This Customer")


def _available_requirement_fields() -> list[str]:
    customer_meta = frappe.get_meta("Customer")
    return [fieldname for fieldname in REQUIREMENT_FIELDS if customer_meta.has_field(fieldname)]


def _no_requirements() -> dict[str, int]:
    return dict.fromkeys(REQUIREMENT_FIELDS, 0)


def _text(value: Any) -> str:
    return str(value or "").strip()
