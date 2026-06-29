import frappe


def execute():
    # Items whose item_code (= name) is a bare 9-digit number (e.g. "100170707") are
    # DKSH-only codes: the item_code itself IS the DKSH code. Treat them like the
    # OPTI / DKSH-only items handled in set_item_code_is_dksh_flag — tick both flags
    # and clear custom_dksh_item_code so it doesn't duplicate the value (and trip the
    # field's unique constraint), matching item.validate().
    if not frappe.db.has_column("Item", "custom_has_dksh_code") or not frappe.db.has_column(
        "Item", "custom_item_code_is_dksh_code"
    ):
        return

    frappe.db.sql(
        r"""
        UPDATE `tabItem`
        SET custom_has_dksh_code = 1,
            custom_item_code_is_dksh_code = 1,
            custom_dksh_item_code = NULL
        WHERE name REGEXP '^[0-9]{9}$'
        """
    )
    frappe.db.commit()
