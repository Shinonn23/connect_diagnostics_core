"""Copy Customer ``customer_name_th`` values into the Customer Alternative Name table.

Mirrors migrate_item_name_th_to_alternative_name. The MD5 name + NOT EXISTS guard
keep it idempotent. The field itself is dropped later by remove_customer_name_th_field.
"""

import frappe


def execute():
    if not frappe.db.has_column("Customer", "customer_name_th"):
        return

    if not frappe.db.table_exists("Customer Alternative Name", cached=False):
        return

    frappe.db.sql(
        """
        INSERT INTO `tabCustomer Alternative Name`
            (name, parent, parenttype, parentfield, idx,
             name_value, creation, modified, modified_by, owner)
        SELECT
            MD5(CONCAT(c.name, c.customer_name_th)),
            c.name, 'Customer', 'alternative_names', 1,
            c.customer_name_th,
            NOW(), NOW(), 'Administrator', 'Administrator'
        FROM tabCustomer c
        WHERE c.customer_name_th IS NOT NULL
          AND c.customer_name_th != ''
          AND NOT EXISTS (
              SELECT 1 FROM `tabCustomer Alternative Name` can
              WHERE can.parent = c.name
                AND can.name_value = c.customer_name_th
          )
        """
    )
    frappe.db.commit()
    migrated = frappe.db.sql("SELECT ROW_COUNT()")[0][0]
    frappe.logger().info(f"Migrated {migrated} customer_name_th values to Customer Alternative Name")
