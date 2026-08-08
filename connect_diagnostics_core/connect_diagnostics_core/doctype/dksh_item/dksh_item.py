# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""DKSH Item — DKSH reference codes as their own master, optionally linked to Item.

A DKSH code was previously five Custom Fields on Item, which forced every code to
belong to a CD Item. DKSH also sells stand-alone products with no CD Item, so the
codes now live here with an optional ``item`` link: blank means a DKSH-only
product. The record name is the DKSH Item Code, so uniqueness of the code is
enforced by naming; a second record mapping the same CD Item is rejected in
``validate``.

This is reference data only. It has no workflow, no roles of its own, and does not
control Item lifecycle or transaction eligibility.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class DKSHItem(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        dksh_item_code: DF.Data
        item: DF.Link | None
        item_name: DF.Data | None
        mat_group4_code: DF.Data | None
        mat_group_code: DF.Data | None
        material_type_code: DF.Data | None
        supplier_product_code: DF.Data | None
    # end: auto-generated types

    def validate(self) -> None:
        self._trim_codes()
        self._reject_duplicate_item()

    def _trim_codes(self) -> None:
        for fieldname in (
            "dksh_item_code",
            "supplier_product_code",
            "mat_group_code",
            "mat_group4_code",
            "material_type_code",
        ):
            value = self.get(fieldname)
            if isinstance(value, str):
                self.set(fieldname, value.strip())

    def _reject_duplicate_item(self) -> None:
        if not self.item:
            return
        existing = frappe.db.get_value(
            "DKSH Item",
            {"item": self.item, "name": ["!=", self.name]},
            "name",
        )
        if existing:
            frappe.throw(
                _("Item {0} already has DKSH Item {1}.").format(self.item, existing),
                title=_("Item already mapped"),
            )
