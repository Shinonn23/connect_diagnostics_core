import frappe

RENAMES = (
    ("GitHub Integration Settings", "GitHub Helpdesk Sync Settings", True),
    ("GitHub Sync Log", "GitHub Helpdesk Sync Log", False),
)


def execute():
    for old, new, is_single in RENAMES:
        _rename_or_drop_old_doctype(old, new, is_single=is_single)
    frappe.clear_cache()
    frappe.db.commit()


def _rename_or_drop_old_doctype(old: str, new: str, *, is_single: bool) -> None:
    old_exists = frappe.db.exists("DocType", old)
    new_exists = frappe.db.exists("DocType", new)
    if old_exists and not new_exists:
        frappe.rename_doc("DocType", old, new, force=True)
        return

    if not old_exists:
        return

    if is_single:
        _move_single_values(old, new)
    else:
        _copy_table_rows(old, new)

    frappe.delete_doc("DocType", old, force=True, ignore_missing=True)


def _move_single_values(old: str, new: str) -> None:
    rows = frappe.db.sql(
        "SELECT field, value FROM `tabSingles` WHERE doctype = %s",
        old,
        as_dict=True,
    )
    for row in rows:
        exists = frappe.db.sql(
            "SELECT 1 FROM `tabSingles` WHERE doctype = %s AND field = %s",
            (new, row.field),
        )
        if exists:
            continue
        frappe.db.sql(
            "INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)",
            (new, row.field, row.value),
        )
    frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = %s", old)


def _copy_table_rows(old: str, new: str) -> None:
    if not frappe.db.table_exists(old) or not frappe.db.table_exists(new):
        return
    old_table = f"tab{old}"
    new_table = f"tab{new}"
    frappe.db.sql(f"INSERT IGNORE INTO `{new_table}` SELECT * FROM `{old_table}`")  # nosemgrep
