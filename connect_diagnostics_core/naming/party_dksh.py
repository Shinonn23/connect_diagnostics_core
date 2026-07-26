# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Legacy DKSH-code naming logic retained for Supplier only.

Customer naming is now controlled by the Customer Code and Customer Channel
model in ``naming.customer``. Supplier behavior remains unchanged for backward
compatibility.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.naming import make_autoname, revert_series_if_last

_DKSH_FIELD = {"Supplier": "dksh_supplier_code"}
_IS_DKSH_FLAG = {"Supplier": "supplier_code_is_dksh_code"}


def set_name_from_dksh_code(doc: Any, method: str | None = None) -> None:
    """Autoname hook: when a Supplier DKSH code is its ID, use it as ``name``.

    Runs after the controller's naming-series autoname (``Document.run_method``
    composes hooked handlers after the controller method), so it overrides the
    series-assigned name and reverts the just-consumed series counter to avoid
    burning a CD-code number.
    """
    if doc.doctype != "Supplier":
        return
    field = _DKSH_FIELD[doc.doctype]
    flag = _IS_DKSH_FLAG[doc.doctype]
    if not (doc.get("has_dksh_code") and doc.get(flag)):
        return

    dksh_value = (doc.get(field) or "").strip()
    if not dksh_value:
        frappe.throw(_("DKSH code is required when it is used as the {0} ID.").format(_(doc.doctype)))

    if doc.get("naming_series") and doc.name:
        revert_series_if_last(doc.naming_series, doc.name, doc)
    doc.name = dksh_value


def validate(doc: Any, method: str | None = None) -> None:
    """Validate Supplier legacy DKSH fields (mirrors item.validate).

    Also detects a DKSH-only → CD conversion (the ``*_code_is_dksh_code`` flag was
    unticked while ``has_dksh_code`` stays on) and preserves the DKSH value so
    ``issue_cd_code_on_update`` can rename the record to a fresh CD code.
    """
    if doc.doctype != "Supplier":
        return
    field = _DKSH_FIELD[doc.doctype]
    flag = _IS_DKSH_FLAG[doc.doctype]

    before = doc.get_doc_before_save()
    converting = bool(before and before.get(flag) and not doc.get(flag) and doc.get("has_dksh_code"))
    if converting and not (doc.get(field) or "").strip():
        # The DKSH value currently lives in the record name; keep it in the field
        # before the new CD code becomes the name in on_update.
        doc.set(field, doc.name)
        doc.flags.cd_issue_from_dksh = True

    if doc.get("has_dksh_code"):
        if doc.get(flag):
            # DKSH-only: the name itself is the DKSH code. Don't keep a duplicate in
            # the field or it trips the unique constraint (matches item.validate).
            doc.set(field, None)
        elif not (doc.get(field) or "").strip():
            frappe.throw(_("DKSH code is required when 'Has DKSH Code' is ticked."))
    else:
        doc.set(flag, 0)
        doc.set(field, None)


def issue_cd_code_on_update(doc: Any, method: str | None = None) -> None:
    """Finish a Supplier DKSH-only → CD conversion by renaming its record."""
    if doc.doctype != "Supplier":
        return
    if not doc.flags.get("cd_issue_from_dksh"):
        return
    doc.flags.cd_issue_from_dksh = False

    new_name = make_autoname(_cd_series(doc), doc.doctype, doc)
    frappe.rename_doc(doc.doctype, doc.name, new_name, force=True)
    doc.name = new_name


def _cd_series(doc: Any) -> str:
    return doc.get("naming_series") or "5B.###"
