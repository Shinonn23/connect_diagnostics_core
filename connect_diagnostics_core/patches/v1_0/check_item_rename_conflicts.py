import frappe


def execute():
    conflicts = frappe.db.sql(
        """
        SELECT i.name AS current_name, i.custom_cd_item_code AS target_name
        FROM tabItem i
        WHERE i.name != i.custom_cd_item_code
          AND i.custom_cd_item_code IS NOT NULL
          AND i.custom_cd_item_code != ''
          AND EXISTS (
              SELECT 1 FROM tabItem i2
              WHERE i2.name = i.custom_cd_item_code
                AND i2.name != i.name
          )
        """,
        as_dict=True,
    )
    if conflicts:
        frappe.log_error(str(conflicts), "Item Rename Conflicts — ดูก่อน run rename patch")
        frappe.throw(
            f"พบ item_code conflict {len(conflicts)} รายการ — ดู Error Log แล้วแก้ข้อมูลก่อน"
        )
