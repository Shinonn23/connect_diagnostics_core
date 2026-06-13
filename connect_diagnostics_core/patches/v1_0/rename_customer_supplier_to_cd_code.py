import frappe


def execute():
    _rename_to_cd_code(
        doctype="Customer",
        cd_field="custom_cd_customer_code",
        dksh_field="custom_dksh_customer_code",
    )
    _rename_to_cd_code(
        doctype="Supplier",
        cd_field="custom_cd_supplier_code",
        dksh_field="custom_dksh_supplier_code",
    )


def _rename_to_cd_code(doctype: str, cd_field: str, dksh_field: str) -> None:
    rows = frappe.db.get_all(
        doctype,
        filters={cd_field: ["not in", ["", None]]},
        fields=["name", cd_field, dksh_field],
    )

    to_rename = [
        row for row in rows if row[dksh_field] and row.name == row[dksh_field] and row.name != row[cd_field]
    ]

    for row in to_rename:
        frappe.rename_doc(doctype, row.name, row[cd_field], force=True, merge=False)
        frappe.db.commit()

    frappe.logger().info(f"{doctype}: renamed {len(to_rename)} records to CD code")
