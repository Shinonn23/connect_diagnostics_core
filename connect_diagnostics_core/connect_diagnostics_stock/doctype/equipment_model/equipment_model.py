# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import frappe
from frappe import _
from frappe.model.document import Document


class EquipmentModel(Document):
    """Map one business model to its Stock and fixed-asset Item records."""

    if TYPE_CHECKING:
        from frappe.types import DF

        allow_demo: DF.Check
        allow_stock_to_asset_conversion: DF.Check
        company: DF.Link | None
        default_asset_category: DF.Link | None
        description: DF.SmallText | None
        disabled: DF.Check
        fixed_asset_item: DF.Link
        model_code: DF.Data
        model_name: DF.Data
        stock_item: DF.Link

    def validate(self) -> None:
        if self.stock_item == self.fixed_asset_item:
            frappe.throw(_("Stock Item and Fixed Asset Item must be different records."))

        items = self._lock_mapped_items()
        stock_item = items[self.stock_item]
        fixed_asset_item = items[self.fixed_asset_item]
        if not stock_item.is_stock_item or stock_item.is_fixed_asset:
            frappe.throw(_("Stock Item must be a stock Item and must not be a fixed-asset Item."))
        if fixed_asset_item.is_stock_item or not fixed_asset_item.is_fixed_asset:
            frappe.throw(_("Fixed Asset Item must be a non-stock fixed-asset Item."))

        if (self.allow_demo or self.allow_stock_to_asset_conversion) and (
            stock_item.disabled or fixed_asset_item.disabled
        ):
            frappe.throw(_("Demo and conversion capabilities require both mapped Items to be enabled."))

        self._lock_and_validate_active_mappings()

    def _lock_mapped_items(self) -> dict[str, frappe._dict]:
        """Serialize competing mappings on stable Item rows before checking conflicts."""

        items: dict[str, frappe._dict] = {}
        for item_code in sorted((self.stock_item, self.fixed_asset_item)):
            item = frappe.db.get_value(
                "Item",
                item_code,
                ["name", "is_stock_item", "is_fixed_asset", "disabled"],
                as_dict=True,
                for_update=True,
            )
            if not item:
                frappe.throw(_("Item {0} does not exist.").format(frappe.bold(item_code)))
            items[item_code] = cast(frappe._dict, item)
        return items

    def _lock_and_validate_active_mappings(self) -> None:
        if self.disabled:
            return

        identities = sorted(
            (("fixed_asset_item", self.fixed_asset_item), ("stock_item", self.stock_item)),
            key=lambda identity: (identity[0], identity[1]),
        )
        for fieldname, item_code in identities:
            conflict = frappe.db.get_value(
                "Equipment Model",
                {
                    fieldname: item_code,
                    "disabled": 0,
                    "name": ["!=", self.name or ""],
                },
                "name",
                for_update=True,
            )
            if conflict:
                label = _("Fixed Asset Item") if fieldname == "fixed_asset_item" else _("Stock Item")
                frappe.throw(
                    _("Active Equipment Model {0} already uses {1} {2}.").format(
                        frappe.bold(conflict), label, frappe.bold(item_code)
                    )
                )


def get_eligible_demo_stock_items(company: str | None = None) -> list[str]:
    """Return Item identifiers only; mapping configuration remains server-internal."""

    return cast(
        list[str],
        frappe.db.sql(
            """
            SELECT DISTINCT em.stock_item
            FROM `tabEquipment Model` em
            INNER JOIN `tabItem` item ON item.name = em.stock_item
            WHERE em.disabled = 0
                AND em.allow_demo = 1
                AND item.disabled = 0
                AND item.is_stock_item = 1
                AND item.is_fixed_asset = 0
                AND (
                    %(company)s IS NULL
                    OR em.company IS NULL
                    OR em.company = ''
                    OR em.company = %(company)s
                )
            ORDER BY em.stock_item
            """,
            {"company": company},
            pluck=True,
        ),
    )
