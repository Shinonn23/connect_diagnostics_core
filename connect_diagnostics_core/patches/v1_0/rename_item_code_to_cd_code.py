import frappe


def execute():
    items = frappe.db.get_all(
        "Item",
        filters={"custom_cd_item_code": ["not in", ["", None]]},
        fields=["name", "custom_cd_item_code"],
        order_by="name",
    )
    renamed = 0
    for item in items:
        if item.name != item.custom_cd_item_code:
            frappe.rename_doc(
                "Item",
                item.name,
                item.custom_cd_item_code,
                force=True,
                merge=False,
            )
            frappe.db.commit()
            renamed += 1

    frappe.logger().info(f"Item Code rename complete: {renamed} items renamed")
