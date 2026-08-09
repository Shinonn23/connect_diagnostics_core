# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Shared foundation for DKSH reference masters.

A DKSH reference master (``DKSH Item``, ``DKSH Customer``, …) is a standalone
DocType autonamed by its DKSH code and carrying an **optional** link to the CD
master it references. Two behaviours are common to every one of them, so they live
here rather than being re-implemented per DocType:

* :func:`validate_reference` — trim the code fields and reject a second reference
  of the same DocType that points at the same CD master.
* :func:`inject_connection` — surface the reference under the linked master form's
  Connections, via ``override_doctype_dashboards``.

This is reference data only: no reference master controls the CD master's
lifecycle or transaction eligibility.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document


def validate_reference(
    doc: Document,
    *,
    code_fields: Sequence[str],
    link_field: str,
    master_doctype: str,
) -> None:
    """Trim the code fields and reject a duplicate reference to the same master.

    ``code_fields`` are the free-text DKSH codes carried by the reference master;
    ``link_field`` is its optional Link to the CD master (``master_doctype``). When
    the link is set, a second record of the same DocType pointing at that master is
    rejected — the code stays unique through naming, but nothing else stops two
    codes claiming one CD master.
    """
    _trim_codes(doc, code_fields)
    _reject_duplicate_master(doc, link_field=link_field, master_doctype=master_doctype)


def inject_connection(
    data: dict[str, Any],
    *,
    reference_doctype: str,
    link_field: str,
    group_label: str,
) -> dict[str, Any]:
    """Surface ``reference_doctype`` under the linked master form's Connections.

    A reference master links to the CD master through ``link_field`` (for example
    ``item``), not the fieldname the master's dashboard keys on, so it is
    registered in ``non_standard_fieldnames`` and added to the ``group_label``
    Connections group. Idempotent: re-running never duplicates the entry.
    """
    non_standard = data.setdefault("non_standard_fieldnames", {})
    non_standard[reference_doctype] = link_field

    transactions = data.setdefault("transactions", [])
    for group in transactions:
        if group.get("label") == group_label:
            if reference_doctype not in group["items"]:
                group["items"].append(reference_doctype)
            break
    else:
        transactions.append({"label": group_label, "items": [reference_doctype]})

    return data


def _trim_codes(doc: Document, code_fields: Sequence[str]) -> None:
    for fieldname in code_fields:
        value = doc.get(fieldname)
        if isinstance(value, str):
            doc.set(fieldname, value.strip())


def _reject_duplicate_master(doc: Document, *, link_field: str, master_doctype: str) -> None:
    master = doc.get(link_field)
    if not master:
        return
    existing = frappe.db.get_value(
        doc.doctype,
        {link_field: master, "name": ["!=", doc.name]},
        "name",
    )
    if existing:
        frappe.throw(
            _("{0} {1} already has {2} {3}.").format(master_doctype, master, doc.doctype, existing),
            title=_("{0} already mapped").format(master_doctype),
        )
