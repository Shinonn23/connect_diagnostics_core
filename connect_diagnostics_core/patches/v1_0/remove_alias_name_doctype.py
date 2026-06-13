import frappe


def execute():
    for doctype in ("Alias Name", "Alias Supported DocType"):
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)
            frappe.db.commit()
