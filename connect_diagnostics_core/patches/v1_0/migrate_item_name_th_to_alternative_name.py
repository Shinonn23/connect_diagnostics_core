import frappe


def execute():
    if not frappe.db.table_exists("Item Alternative Name", cached=False):
        return

    frappe.db.sql(
        """
        INSERT INTO `tabItem Alternative Name`
            (name, parent, parenttype, parentfield, idx,
             name_value, name_label, creation, modified, modified_by, owner)
        SELECT
            MD5(CONCAT(i.name, i.custom_item_name_th)),
            i.name,
            'Item',
            'custom_alternative_names',
            1,
            i.custom_item_name_th,
            'Thai',
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
    frappe.db.commit()
    migrated = frappe.db.sql("SELECT ROW_COUNT()")[0][0]
    frappe.logger().info(f"Migrated {migrated} custom_item_name_th values to Item Alternative Name")
