"""Drop the ``customer_name_th`` field/column from Customer.

The values were migrated into Customer Alternative Name by
migrate_customer_name_th_to_alternative_name. This makes a final safety pass —
copying any not-yet-migrated value — then deletes the Custom Field and drops the
orphan column. Idempotent / no-op once dropped (mirrors drop_custom_item_name_th_column).
"""

import frappe


def execute():
    if not frappe.db.has_column("Customer", "customer_name_th"):
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

    if frappe.db.exists("Custom Field", "Customer-customer_name_th"):
        frappe.delete_doc("Custom Field", "Customer-customer_name_th", force=True)

    frappe.db.sql_ddl("ALTER TABLE `tabCustomer` DROP COLUMN `customer_name_th`")
    frappe.db.commit()
