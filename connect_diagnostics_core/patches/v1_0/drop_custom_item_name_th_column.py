"""Drop the orphan ``custom_item_name_th`` column from Item.

remove_custom_item_name_th_field deleted the Custom Field doc, but Frappe leaves the
underlying DB column in place, so the data (Thai item names) still sits in tabItem even
though the field is gone. The values were already migrated into Item Alternative Name
(label "Thai") by migrate_item_name_th_to_alternative_name.

This patch makes a final safety pass — copying any not-yet-migrated value into Item
Alternative Name — then drops the orphan column. Idempotent / no-op once dropped.
"""

import frappe


def execute():
    if not frappe.db.has_column("Item", "custom_item_name_th"):
        return  # already dropped

    # Safety: migrate any stragglers before dropping (parentfield matches the renamed
    # Table field "alternative_names"). The MD5 name + NOT EXISTS guard keep it idempotent.
    # Skip the copy when Item Alternative Name has already been retired (table dropped);
    # the orphan column is still dropped below.
    if frappe.db.table_exists("Item Alternative Name", cached=False):
        frappe.db.sql(
            """
            INSERT INTO `tabItem Alternative Name`
                (name, parent, parenttype, parentfield, idx,
                 name_value, name_label, creation, modified, modified_by, owner)
            SELECT
                MD5(CONCAT(i.name, i.custom_item_name_th)),
                i.name, 'Item', 'alternative_names', 1,
                i.custom_item_name_th, 'Thai',
                NOW(), NOW(), 'Administrator', 'Administrator'
            FROM tabItem i
            WHERE i.custom_item_name_th IS NOT NULL
              AND i.custom_item_name_th != ''
              AND NOT EXISTS (
                  SELECT 1 FROM `tabItem Alternative Name` ian
                  WHERE ian.parent = i.name
                    AND ian.name_value = i.custom_item_name_th
              )
            """
        )

    # Clean up the Custom Field doc too, in case it still lingers on some site.
    if frappe.db.exists("Custom Field", "Item-custom_item_name_th"):
        frappe.delete_doc("Custom Field", "Item-custom_item_name_th", force=True)

    frappe.db.sql_ddl("ALTER TABLE `tabItem` DROP COLUMN `custom_item_name_th`")
    frappe.db.commit()
