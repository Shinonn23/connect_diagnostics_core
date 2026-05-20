# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from frappe import _


def get_data() -> dict:
    return {
        "fieldname": "department",
        "reports": [{"label": _("Reports"), "items": ["General Ledger"]}],
    }
