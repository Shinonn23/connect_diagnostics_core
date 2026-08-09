import frappe


def execute():
    if not frappe.db.exists("DocType", "Alias Name"):
        return

    if not frappe.db.table_exists("Item Alternative Name", cached=False):
        return

    aliases = frappe.db.get_all(
        "Alias Name",
        filters={"documents": "Item"},
        fields=["primary_name", "alias_name"],
    )
    migrated = 0
    for alias in aliases:
        if not frappe.db.exists("Item", alias.primary_name):
            continue
        already = frappe.db.exists(
            "Item Alternative Name",
            {"parent": alias.primary_name, "name_value": alias.alias_name},
        )
        if already:
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Item Alternative Name",
                "name": frappe.generate_hash(length=10),
                "parent": alias.primary_name,
                "parenttype": "Item",
                "parentfield": "custom_alternative_names",
                "idx": 1,
                "name_value": alias.alias_name,
                "name_label": "Other",
            }
        )
        doc.db_insert()
        migrated += 1

    frappe.db.commit()
    frappe.logger().info(f"Migrated {migrated} Alias Name records to Item Alternative Name")
