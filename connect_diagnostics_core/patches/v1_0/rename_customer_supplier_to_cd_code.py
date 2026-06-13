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
    rows = frappe.db.sql(
        f"""
        SELECT name, `{cd_field}` AS cd_code
        FROM `tab{doctype}`
        WHERE `{cd_field}` IS NOT NULL
          AND `{cd_field}` != ''
          AND name = `{dksh_field}`
          AND name != `{cd_field}`
        """,
        as_dict=True,
    )

    for row in rows:
        frappe.rename_doc(doctype, row.name, row.cd_code, force=True, merge=False)
        frappe.db.commit()

    frappe.logger().info(f"{doctype}: renamed {len(rows)} records to CD code")
