from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

REFERENCE_DOCTYPES = frozenset(("Purchase Invoice", "Sales Invoice"))
BUILT_IN_DIMENSION_FIELDS = ("cost_center", "project")


@dataclass(frozen=True)
class DimensionField:
    fieldname: str
    label: str


def validate(doc: Document, _method: Any) -> None:
    validate_reference_dimensions(doc)


def validate_reference_dimensions(doc: Document) -> None:
    dimensions = get_payment_entry_dimension_fields(doc)
    references = get_allocated_invoice_references(doc)
    if not dimensions or not references:
        return

    target_dimensions: dict[str, str | None] | None = None
    target_reference: Any | None = None
    reference_dimensions_by_name: dict[tuple[str, str], dict[str, str | None]] = {}

    for reference in references:
        reference_dimensions = get_reference_dimensions(reference, dimensions)
        if not reference_dimensions:
            continue

        reference_key = (reference.reference_doctype, reference.reference_name)
        reference_dimensions_by_name[reference_key] = reference_dimensions

        if target_dimensions is None:
            target_dimensions = reference_dimensions
            target_reference = reference
            continue

        if reference_dimensions != target_dimensions:
            throw_mixed_reference_dimensions(target_reference, reference)

    if not target_dimensions:
        return

    sync_missing_payment_entry_dimensions(doc, dimensions, target_dimensions)
    validate_payment_entry_dimensions(doc, dimensions, references, reference_dimensions_by_name)


def get_payment_entry_dimension_fields(doc: Document) -> list[DimensionField]:
    fieldnames = [*get_active_accounting_dimension_fieldnames(), *BUILT_IN_DIMENSION_FIELDS]
    return [
        DimensionField(fieldname=fieldname, label=get_field_label(doc.doctype, fieldname))
        for fieldname in dict.fromkeys(fieldnames)
        if has_field(doc.doctype, fieldname)
    ]


def get_active_accounting_dimension_fieldnames() -> list[str]:
    from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
        get_accounting_dimensions,
    )

    return list(get_accounting_dimensions())


def get_allocated_invoice_references(doc: Document) -> list[Any]:
    return [
        reference
        for reference in doc.get("references", [])
        if reference.reference_doctype in REFERENCE_DOCTYPES
        and reference.reference_name
        and flt(reference.get("allocated_amount")) != 0
    ]


def get_reference_dimensions(reference: Any, dimensions: list[DimensionField]) -> dict[str, str | None]:
    reference_fields = [
        dimension.fieldname
        for dimension in dimensions
        if has_field(reference.reference_doctype, dimension.fieldname)
    ]
    if not reference_fields:
        return {}

    values = frappe.db.get_value(
        reference.reference_doctype,
        reference.reference_name,
        reference_fields,
        as_dict=True,
    )
    return {fieldname: values.get(fieldname) for fieldname in reference_fields}


def sync_missing_payment_entry_dimensions(
    doc: Document,
    dimensions: list[DimensionField],
    target_dimensions: dict[str, str | None],
) -> None:
    for dimension in dimensions:
        if dimension.fieldname not in target_dimensions:
            continue
        if not doc.get(dimension.fieldname) and target_dimensions[dimension.fieldname]:
            doc.set(dimension.fieldname, target_dimensions[dimension.fieldname])


def validate_payment_entry_dimensions(
    doc: Document,
    dimensions: list[DimensionField],
    references: list[Any],
    reference_dimensions_by_name: dict[tuple[str, str], dict[str, str | None]],
) -> None:
    for reference in references:
        reference_dimensions = reference_dimensions_by_name.get(
            (reference.reference_doctype, reference.reference_name), {}
        )
        for dimension in dimensions:
            if dimension.fieldname not in reference_dimensions:
                continue

            payment_entry_value = doc.get(dimension.fieldname)
            reference_value = reference_dimensions[dimension.fieldname]
            if payment_entry_value != reference_value:
                throw_dimension_mismatch(dimension, payment_entry_value, reference_value, reference)


def has_field(doctype: str, fieldname: str) -> bool:
    return bool(frappe.get_meta(doctype).has_field(fieldname))


def get_field_label(doctype: str, fieldname: str) -> str:
    field = frappe.get_meta(doctype).get_field(fieldname)
    return field.label if field and field.label else frappe.unscrub(fieldname)


def throw_mixed_reference_dimensions(first_reference: Any, second_reference: Any) -> None:
    frappe.throw(
        _(
            "Payment Entry cannot allocate invoices with different accounting dimensions. "
            "Please create separate Payment Entries for {0} and {1}."
        ).format(
            frappe.bold(f"{first_reference.reference_doctype} {first_reference.reference_name}"),
            frappe.bold(f"{second_reference.reference_doctype} {second_reference.reference_name}"),
        ),
        title=_("Accounting Dimension Mismatch"),
    )


def throw_dimension_mismatch(
    dimension: DimensionField,
    payment_entry_value: str | None,
    reference_value: str | None,
    reference: Any,
) -> None:
    frappe.throw(
        _("{0} on Payment Entry must match {1} {2}. Expected {3}, found {4}.").format(
            frappe.bold(dimension.label),
            reference.reference_doctype,
            frappe.bold(reference.reference_name),
            frappe.bold(reference_value or _("empty")),
            frappe.bold(payment_entry_value or _("empty")),
        ),
        title=_("Accounting Dimension Mismatch"),
    )
