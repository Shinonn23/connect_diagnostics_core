import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
    # post_model_sync patches run before the setup hook (after_migrate) creates the app's
    # custom fields, so the column may not exist yet on the first migrate. Ensure it exists
    # before backfilling. This creates the legacy custom_* field on purpose; the later
    # strip_custom_prefix_from_field_names patch renames it to has_dksh_code.
    if not frappe.db.has_column("Item", "custom_has_dksh_code"):
        create_custom_field(
            "Item",
            {
                "fieldname": "custom_has_dksh_code",
                "label": "Has DKSH Code",
                "fieldtype": "Check",
                "insert_after": "item_code",
                "default": "0",
            },
        )

    # Existing items that already carry a DKSH code should keep the field visible:
    # tick the new "Has DKSH Code" flag for them.
    frappe.db.sql(
        """
        UPDATE `tabItem`
        SET custom_has_dksh_code = 1
        WHERE custom_dksh_item_code IS NOT NULL
          AND custom_dksh_item_code != ''
        """
    )
    frappe.db.commit()
