"""Tick ``has_dksh_code`` on Suppliers that already carry a DKSH code.

Ensures the app custom fields exist first (apply_all is idempotent and may already
have run for the Customer backfill), then backfills the flag. Mirrors
set_customer_has_dksh_code_flag.
"""

import frappe

from connect_diagnostics_core.setup import apply_all


def execute():
    if not frappe.db.has_column("Supplier", "has_dksh_code"):
        apply_all()

    frappe.db.sql(
        """
        UPDATE `tabSupplier`
        SET has_dksh_code = 1
        WHERE dksh_supplier_code IS NOT NULL
          AND dksh_supplier_code != ''
        """
    )
    frappe.db.commit()
