# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

from frappe import _

DKSH_ITEM_DOCTYPE = "DKSH Item"


def get_item_dashboard_data(data: dict[str, Any]) -> dict[str, Any]:
    """Surface the linked DKSH Item under the Item form's Connections.

    ``DKSH Item`` links to Item through its ``item`` field, not the ``item_code``
    the Item dashboard keys on, so it is registered in ``non_standard_fieldnames``.
    """
    non_standard = data.setdefault("non_standard_fieldnames", {})
    non_standard[DKSH_ITEM_DOCTYPE] = "item"

    transactions = data.setdefault("transactions", [])
    for group in transactions:
        if group.get("label") == _("Reference"):
            if DKSH_ITEM_DOCTYPE not in group["items"]:
                group["items"].append(DKSH_ITEM_DOCTYPE)
            break
    else:
        transactions.append({"label": _("Reference"), "items": [DKSH_ITEM_DOCTYPE]})

    return data
