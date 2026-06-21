"""Drop the ``custom_`` prefix from the app's custom fields.

The field definitions now live in ``connect_diagnostics_core/setup`` under their
stripped names (e.g. ``custom_dksh_item_code`` -> ``dksh_item_code``;
``custom_lenght`` -> ``length``, fixing the typo). This patch migrates existing
data on an upgrading site: it creates the new field, copies the old column's data
across, then removes the old Custom Field / column.

It is idempotent and a no-op on fresh installs (the old columns never exist there;
``after_install`` creates the stripped fields directly). Runs after the DKSH backfill
patches so their flags are set before the rename.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from connect_diagnostics_core import setup as cdc_setup

# (doctype, old fieldname, new fieldname)
RENAMES = [
    ("Account", "custom_account_name_th", "account_name_th"),
    ("Account", "custom_sub_account_type", "sub_account_type"),
    ("Contact", "custom_other_contacts", "other_contacts"),
    ("Currency Exchange", "custom_remark", "remark"),
    ("Customer", "custom_cd_customer_code", "cd_customer_code"),
    ("Customer", "custom_customer_name_th", "customer_name_th"),
    ("Customer", "custom_dksh_customer_code", "dksh_customer_code"),
    ("Employee", "custom_first_name_en", "first_name_en"),
    ("Employee", "custom_last_name_en", "last_name_en"),
    ("Item", "custom_dksh_item_code", "dksh_item_code"),
    ("Item", "custom_height", "height"),
    ("Item", "custom_lenght", "length"),
    ("Item", "custom_width", "width"),
    ("Item", "custom_model", "model"),
    ("Item", "custom_mat_group_code", "mat_group_code"),
    ("Item", "custom_mat_group4_code", "mat_group4_code"),
    ("Item", "custom_material_type_code", "material_type_code"),
    ("Item", "custom_max_storage_days", "max_storage_days"),
    ("Item", "custom_min_remaining_shelf_life", "min_remaining_shelf_life"),
    ("Item", "custom_regulation_class", "regulation_class"),
    ("Item", "custom_storage_condition", "storage_condition"),
    ("Item", "custom_supplier_product_code", "supplier_product_code"),
    ("Item", "custom_has_dksh_code", "has_dksh_code"),
    ("Item", "custom_item_code_is_dksh_code", "item_code_is_dksh_code"),
    ("Item", "custom_alternative_names", "alternative_names"),  # Table field
    ("Item Group", "custom_mat_group_code", "mat_group_code"),
    ("Item Group", "custom_mat_group_desc", "mat_group_desc"),
    ("Item Group", "custom_mat_group4_code", "mat_group4_code"),
    ("Supplier", "custom_cd_supplier_code", "cd_supplier_code"),
    ("Supplier", "custom_dksh_supplier_code", "dksh_supplier_code"),
    ("UOM", "custom_abbr", "abbr"),
    ("Warehouse", "custom_dksh_sloc_code", "dksh_sloc_code"),
]


def execute():
    for doctype, old, new in RENAMES:
        field_def = _field_def(doctype, new)

        if field_def and field_def.get("fieldtype") == "Table":
            _rename_table_field(doctype, old, new, field_def)
            continue

        if not frappe.db.has_column(doctype, old):
            continue  # fresh install or already migrated

        _ensure_new_field(doctype, new, field_def)
        frappe.db.sql(
            f"UPDATE `tab{doctype}` SET `{new}` = `{old}` WHERE `{old}` IS NOT NULL"
        )
        _drop_old(doctype, old)

    frappe.db.commit()


def _field_def(doctype, fieldname):
    """Return the stripped field's definition from setup/ (single source of truth)."""
    for module in cdc_setup._MODULES:
        for dt, fields in getattr(module, "CUSTOM_FIELDS", {}).items():
            if dt != doctype:
                continue
            for field in fields:
                if field["fieldname"] == fieldname:
                    return field
    return None


def _ensure_new_field(doctype, new, field_def):
    if frappe.db.exists("Custom Field", f"{doctype}-{new}"):
        return
    if field_def:
        create_custom_fields({doctype: [field_def]}, ignore_validate=True)


def _rename_table_field(doctype, old, new, field_def):
    child_doctype = field_def.get("options")
    if child_doctype and frappe.db.table_exists(child_doctype):
        frappe.db.sql(
            f"UPDATE `tab{child_doctype}` SET parentfield = %s "
            "WHERE parentfield = %s AND parenttype = %s",
            (new, old, doctype),
        )
    _ensure_new_field(doctype, new, field_def)
    _drop_old(doctype, old)


def _drop_old(doctype, old):
    old_name = f"{doctype}-{old}"
    if frappe.db.exists("Custom Field", old_name):
        # deleting the Custom Field also drops its column (for non-table fields)
        frappe.delete_doc("Custom Field", old_name, ignore_permissions=True, force=True)
    if frappe.db.has_column(doctype, old):
        frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{old}`")
