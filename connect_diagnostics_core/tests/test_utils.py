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
    _seed_thai_tax_settings("_Test Company")
    frappe.db.commit()


def _seed_thai_tax_settings(company: str) -> None:
    """Seed a minimal Thai Tax Settings row for the test company.

    erpnext_thailand registers a GL Entry ``after_insert`` hook
    (``create_tax_invoice_on_gl_tax``) that calls ``get_thai_tax_settings(company)``
    *before* its voucher-type guard, so any GL Entry on a company without a matching
    row throws — including the opening-stock entries erpnext creates while building its
    test records on Frappe v16. The account links on the row are optional; only the
    company match is needed to clear the guard.
    """
    if not frappe.db.exists("DocType", "Thai Tax Settings"):
        return
    settings = frappe.get_single("Thai Tax Settings")
    if any(row.company == company for row in settings.company_accounts):
        return
    settings.append("company_accounts", {"company": company})
    settings.save(ignore_permissions=True)
