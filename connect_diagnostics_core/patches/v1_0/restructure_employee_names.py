from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields, delete_custom_fields

EMPLOYEE = "Employee"
OLD_TH_FIELDS = (
    "custom_first_name_th",
    "custom_last_name_th",
    "custom_full_name_th",
    "custom_middle_name_th",
)

EMPLOYEE_EN_FIELDS = {
    EMPLOYEE: [
        {
            "fieldname": "custom_first_name_en",
            "fieldtype": "Data",
            "insert_after": "column_break_9",
            "label": "First Name EN",
        },
        {
            "fieldname": "custom_last_name_en",
            "fieldtype": "Data",
            "insert_after": "custom_first_name_en",
            "label": "Last Name EN",
        },
    ]
}


def execute() -> None:
    create_custom_fields(EMPLOYEE_EN_FIELDS, update=True)

    has_first_name_th = _has_column("custom_first_name_th")
    has_last_name_th = _has_column("custom_last_name_th")

    if has_first_name_th and has_last_name_th:
        _validate_all_employees_have_th_names()
        _migrate_employee_name_values()
    elif has_first_name_th or has_last_name_th:
        frappe.throw(_("Employee legacy Thai name columns are incomplete. Cannot migrate safely."))

    delete_custom_fields({EMPLOYEE: list(OLD_TH_FIELDS)}, bypass_hooks=True)
    _delete_middle_name_label_property_setter()
    _drop_old_th_columns()
    frappe.clear_cache(doctype=EMPLOYEE)


def _validate_all_employees_have_th_names() -> None:
    missing_employees = frappe.db.sql(
        """
        SELECT name
        FROM `tabEmployee`
        WHERE COALESCE(custom_first_name_th, '') = ''
            OR COALESCE(custom_last_name_th, '') = ''
        ORDER BY name
        LIMIT 20
        """,
        as_dict=True,
    )

    if not missing_employees:
        return

    employee_names = ", ".join(row["name"] for row in missing_employees)
    frappe.throw(
        _("Employee Thai first and last names are required before migration. Missing records: {0}").format(
            employee_names
        )
    )


def _migrate_employee_name_values() -> None:
    frappe.db.sql(
        """
        UPDATE `tabEmployee`
        SET
            custom_first_name_en = first_name,
            custom_last_name_en = last_name,
            first_name = custom_first_name_th,
            last_name = custom_last_name_th,
            employee_name = TRIM(
                CONCAT_WS(
                    ' ',
                    NULLIF(custom_first_name_th, ''),
                    NULLIF(middle_name, ''),
                    NULLIF(custom_last_name_th, '')
                )
            )
        """
    )


def _delete_middle_name_label_property_setter() -> None:
    frappe.db.delete(
        "Property Setter",
        {
            "doc_type": EMPLOYEE,
            "field_name": "middle_name",
            "property": "label",
        },
    )


def _drop_old_th_columns() -> None:
    for fieldname in OLD_TH_FIELDS:
        if _has_column(fieldname):
            frappe.db.sql_ddl(f"ALTER TABLE `tabEmployee` DROP COLUMN `{fieldname}`")


def _has_column(fieldname: str) -> bool:
    return frappe.db.has_column(EMPLOYEE, fieldname)
