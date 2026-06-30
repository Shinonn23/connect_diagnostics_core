"""Tick ``has_dksh_code`` on Customers that already carry a DKSH code.

post_model_sync patches run before the setup hook (after_migrate) creates the app's
custom fields, so materialise them first via apply_all(), then backfill the flag.
Mirrors set_item_has_dksh_code_flag.
"""

import frappe

from connect_diagnostics_core.setup import apply_all


def execute():
    apply_all()

    frappe.db.sql(
        """
        UPDATE `tabCustomer`
        SET has_dksh_code = 1
        WHERE dksh_customer_code IS NOT NULL
          AND dksh_customer_code != ''
        """
    )
    frappe.db.commit()
