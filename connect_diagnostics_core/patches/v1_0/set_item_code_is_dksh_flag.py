import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
    # post_model_sync patches run before the setup hook (after_migrate) creates the app's
    # custom fields, so ensure the column exists before backfilling. This creates the legacy
    # custom_* field on purpose; the later strip_custom_prefix_from_field_names patch renames
    # it to item_code_is_dksh_code.
    if not frappe.db.has_column("Item", "custom_item_code_is_dksh_code"):
        create_custom_field(
            "Item",
            {
                "fieldname": "custom_item_code_is_dksh_code",
                "label": "Item Code is DKSH Code",
                "fieldtype": "Check",
                "insert_after": "custom_has_dksh_code",
                "default": "0",
            },
        )

    # OPTI / DKSH-only items: item_code (= name) already equals the DKSH code.
    frappe.db.sql(
        """
        UPDATE `tabItem`
        SET custom_item_code_is_dksh_code = 1
        WHERE custom_has_dksh_code = 1
          AND custom_dksh_item_code = name
        """
    )

    # These items derive their DKSH code from item_code, so don't keep a copy in
    # custom_dksh_item_code — it duplicates the value a CD-coded item may map to and
    # would clash with the field's unique constraint.
    frappe.db.sql(
        """
        UPDATE `tabItem`
        SET custom_dksh_item_code = NULL
        WHERE custom_item_code_is_dksh_code = 1
        """
    )
    frappe.db.commit()
