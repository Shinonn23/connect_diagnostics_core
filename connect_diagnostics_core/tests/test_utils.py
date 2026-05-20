# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from erpnext.setup.utils import enable_all_roles_and_domains
from frappe.utils import now_datetime


def before_tests() -> None:
    frappe.clear_cache()
    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    year = now_datetime().year
    if not frappe.get_list("Company"):
        setup_complete(
            {
                "currency": "THB",
                "full_name": "Test User",
                "company_name": "_Test Company",
                "timezone": "Asia/Bangkok",
                "company_abbr": "_TC",
                "industry": "Manufacturing",
                "country": "Thailand",
                "fy_start_date": f"{year}-01-01",
                "fy_end_date": f"{year}-12-31",
                "language": "english",
                "company_tagline": "Testing",
                "email": "test@erpnext.com",
                "password": "test",
                "chart_of_accounts": "Standard",
            }
        )

    enable_all_roles_and_domains()
    frappe.db.commit()
