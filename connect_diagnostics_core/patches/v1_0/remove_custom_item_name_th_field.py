import frappe


def execute():
    if frappe.db.exists("Custom Field", "Item-custom_item_name_th"):
        frappe.delete_doc("Custom Field", "Item-custom_item_name_th", force=True)
        frappe.db.commit()
