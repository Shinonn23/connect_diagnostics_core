import frappe


def execute():
    if frappe.db.exists("Custom Field", "Item-custom_cd_item_code"):
        frappe.delete_doc("Custom Field", "Item-custom_cd_item_code", force=True)
        frappe.db.commit()
