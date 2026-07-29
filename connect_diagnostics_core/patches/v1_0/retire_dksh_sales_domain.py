# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Retire DKSH sales metadata while preserving master and transaction identities.

MariaDB schema DDL commits implicitly, so the physical-column and table removal
cannot be part of one database transaction. The patch is idempotent and performs
all Item-code preservation and Customer-state migration before destructive DDL.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, cast

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.workflow.doctype.workflow_action.workflow_action import (
    clear_workflow_actions,
    process_workflow_actions,
)

from connect_diagnostics_core.setup import customer_onboarding
from connect_diagnostics_core.setup import item as item_setup

_IDENT_RE = re.compile(r"^[A-Za-z0-9_ ]+$")

DKSH_COMPANY = "บริษัท ดีเคเอสเอช (ประเทศไทย) จำกัด"
DKSH_PRICE_LIST = "DKSH Standard Selling"

DKSH_MAPPING_DOCTYPE = "DKSH Item Mapping"
PARTNER_MAPPING_DOCTYPE = "Partner Item Mapping"
DKSH_SETTINGS_DOCTYPE = "DKSH Sales Settings"

DKSH_MAPPING_WORKFLOW = "DKSH Item Mapping Workflow"
PENDING_DKSH_CUSTOMER_STATE = "Customer Pending DKSH SAP Customer Setup"
CHANNEL_CD = "CD"
CHANNEL_BOTH = "CD and DKSH"

DKSH_ROLES = (
    "DKSH Item Coordinator",
    "DKSH Order Admin",
)

DKSH_WORKFLOW_STATES = (
    PENDING_DKSH_CUSTOMER_STATE,
    "DKSH Item Mapping Draft",
    "Pending DKSH Coordinator Review",
    "Awaiting DKSH Code",
    "DKSH Item Mapping Active",
    "DKSH Item Mapping Returned for Correction",
    "DKSH Item Mapping Rejected",
)

DKSH_WORKFLOW_ACTION_MASTERS = (
    "Send for DKSH SAP customer setup",
    "Send for DKSH coordinator review",
    "Resubmit for DKSH coordinator review",
    "Send request to DKSH",
    "Reject DKSH Item Mapping",
    "Activate DKSH Item Mapping",
)

RETIRED_CUSTOM_FIELDS: dict[str, tuple[str, ...]] = {
    "Customer": (
        "customer_channel",
        "dksh_sap_customer_code",
        "has_dksh_code",
        "customer_code_is_dksh_code",
        "dksh_customer_code",
        "custom_customer_channel",
        "custom_dksh_sap_customer_code",
        "custom_has_dksh_code",
        "custom_customer_code_is_dksh_code",
        "custom_dksh_customer_code",
    ),
    "Item": (
        "item_channel",
        "partner_item_mappings_section",
        "partner_item_mappings",
        "has_dksh_code",
        "item_code_is_dksh_code",
        "custom_item_channel",
        "custom_partner_item_mappings_section",
        "custom_partner_item_mappings",
        "custom_has_dksh_code",
        "custom_item_code_is_dksh_code",
    ),
    "Supplier": (
        "has_dksh_code",
        "supplier_code_is_dksh_code",
        "dksh_supplier_code",
        "custom_has_dksh_code",
        "custom_supplier_code_is_dksh_code",
        "custom_dksh_supplier_code",
    ),
    "Warehouse": (
        "dksh_sloc_code",
        "custom_dksh_sloc_code",
    ),
    "Sales Order": (
        "sap_order_section",
        "sap_order_status",
        "sap_order_no",
        "sap_keyed_by",
        "sap_keyed_on",
        "sap_order_correction_reason",
        "custom_sap_order_section",
        "custom_sap_order_status",
        "custom_sap_order_no",
        "custom_sap_keyed_by",
        "custom_sap_keyed_on",
        "custom_sap_order_correction_reason",
    ),
    "Sales Order Item": (
        "dksh_item_mapping",
        "custom_dksh_item_mapping",
    ),
}


def get_retirement_preview() -> dict[str, Any]:
    """Return read-only counts for every allowlisted retirement target."""
    item_updates, item_conflicts = _plan_item_dksh_code_updates()
    retired_field_records = 0
    retired_columns = 0
    for doctype, fieldnames in RETIRED_CUSTOM_FIELDS.items():
        retired_field_records += frappe.db.count(
            "Custom Field",
            filters={"dt": doctype, "fieldname": ["in", fieldnames]},
        )
        retired_columns += sum(
            int(frappe.db.has_column(doctype, fieldname)) for fieldname in fieldnames
        )

    mapping_records = {
        doctype: frappe.db.count(doctype) if frappe.db.table_exists(doctype) else 0
        for doctype in (DKSH_MAPPING_DOCTYPE, PARTNER_MAPPING_DOCTYPE)
    }
    doctype_metadata = {
        doctype: int(bool(frappe.db.exists("DocType", doctype)))
        for doctype in (
            DKSH_MAPPING_DOCTYPE,
            PARTNER_MAPPING_DOCTYPE,
            DKSH_SETTINGS_DOCTYPE,
        )
    }
    user_settings = _sales_order_grid_settings()

    return {
        "item_codes_to_backfill": len(item_updates),
        "item_code_conflicts": item_conflicts,
        "pending_customers_to_move": _count_if_column(
            "Customer",
            "customer_onboarding_state",
            {"customer_onboarding_state": PENDING_DKSH_CUSTOMER_STATE},
        ),
        "workflow_actions_to_delete": (
            frappe.db.count(
                "Workflow Action",
                filters={"reference_doctype": DKSH_MAPPING_DOCTYPE},
            )
            + frappe.db.count(
                "Workflow Action",
                filters={
                    "reference_doctype": "Customer",
                    "workflow_state": PENDING_DKSH_CUSTOMER_STATE,
                },
            )
        ),
        "workflow_records_to_delete": {
            "workflows": int(bool(frappe.db.exists("Workflow", DKSH_MAPPING_WORKFLOW))),
            "action_masters": sum(
                int(bool(frappe.db.exists("Workflow Action Master", name)))
                for name in DKSH_WORKFLOW_ACTION_MASTERS
            ),
            "states": sum(
                int(bool(frappe.db.exists("Workflow State", name)))
                for name in DKSH_WORKFLOW_STATES
            ),
        },
        "permission_records_to_delete": {
            "custom_docperms": frappe.db.count(
                "Custom DocPerm",
                filters={"role": ["in", DKSH_ROLES]},
            ),
            "role_assignments": frappe.db.count(
                "Has Role",
                filters={"role": ["in", DKSH_ROLES]},
            ),
            "roles": sum(int(bool(frappe.db.exists("Role", name))) for name in DKSH_ROLES),
        },
        "price_list_records_to_delete": {
            "price_lists": int(bool(frappe.db.exists("Price List", DKSH_PRICE_LIST))),
            "item_prices": frappe.db.count(
                "Item Price",
                filters={"price_list": DKSH_PRICE_LIST},
            ),
        },
        "custom_fields_to_delete": retired_field_records,
        "custom_columns_to_drop": retired_columns,
        "mapping_records_to_delete": mapping_records,
        "doctype_metadata_to_delete": doctype_metadata,
        "settings_rows_to_delete": frappe.db.count(
            "Singles",
            filters={"doctype": DKSH_SETTINGS_DOCTYPE},
        ),
        "sales_order_grid_settings_to_reset": len(user_settings),
    }


def execute() -> None:
    """Preserve retained data, then remove the retired DKSH sales domain."""
    _ensure_item_dksh_code_field()
    _backfill_item_dksh_codes()
    customer_onboarding.ensure_configuration()
    _migrate_pending_customers()
    _remove_dksh_workflow_actions()
    _remove_dksh_workflow_configuration()
    _remove_dksh_price_list()
    _remove_dksh_permissions_and_roles()
    _reset_sales_order_item_grid_settings()
    _remove_retired_custom_fields_and_columns()
    _remove_retired_doctypes()
    frappe.clear_cache()


def _ensure_item_dksh_code_field() -> None:
    field = next(
        field
        for field in item_setup.CUSTOM_FIELDS["Item"]
        if field.get("fieldname") == "dksh_item_code"
    )
    create_custom_fields({"Item": [field]}, ignore_validate=True)


def _backfill_item_dksh_codes() -> None:
    for item_name, code in _item_dksh_code_updates().items():
        frappe.db.set_value("Item", item_name, "dksh_item_code", code, update_modified=False)


def _item_dksh_code_updates() -> dict[str, str]:
    planned_updates, conflicts = _plan_item_dksh_code_updates()
    if conflicts:
        conflict_details = "\n".join(f"- {conflict}" for conflict in conflicts)
        frappe.throw(
            _("DKSH Item Code preservation conflicts must be resolved before retirement: {0}").format(
                conflict_details
            ),
            title=_("DKSH sales retirement blocked"),
        )
    return planned_updates


def _plan_item_dksh_code_updates() -> tuple[dict[str, str], list[str]]:
    if not frappe.db.has_column("Item", "dksh_item_code"):
        return {}, []

    item_fields = ["name", "dksh_item_code"]
    has_item_channel = frappe.db.has_column("Item", "item_channel")
    if has_item_channel:
        item_fields.append("item_channel")
    items = cast(
        list[dict[str, Any]],
        frappe.get_all("Item", fields=item_fields, order_by="name asc"),
    )
    current_by_item = {str(row["name"]): _text(row.get("dksh_item_code")) for row in items}
    eligible_item_names = (
        {
            str(row["name"])
            for row in items
            if _text(row.get("item_channel")) in {CHANNEL_CD, CHANNEL_BOTH}
        }
        if has_item_channel
        else None
    )
    claimed_codes: dict[str, tuple[str, str]] = {}
    candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)
    planned_updates: dict[str, str] = {}
    conflicts: list[str] = []

    for item_name, code in current_by_item.items():
        if not code:
            continue
        code_key = code.casefold()
        claimed = claimed_codes.get(code_key)
        if claimed and claimed[0] != item_name:
            conflicts.append(
                f"DKSH Item Code {code} belongs to both Item {claimed[0]} and Item {item_name}"
            )
            continue
        claimed_codes[code_key] = (item_name, code)

    _collect_master_mapping_candidates(candidates, eligible_item_names)
    _collect_partner_mapping_candidates(candidates, eligible_item_names)

    for item_name in sorted(candidates):
        if item_name not in current_by_item or current_by_item[item_name]:
            continue
        item_candidates = {(source, code) for source, code in candidates[item_name] if code}
        candidate_codes = {code.casefold(): code for _, code in item_candidates}
        if len(candidate_codes) != 1:
            conflicts.append(
                f"Item {item_name} has conflicting retired DKSH codes: "
                f"{', '.join(sorted(candidate_codes.values())) or '(blank)'}"
            )
            continue

        code_key, code = next(iter(candidate_codes.items()))
        claimed = claimed_codes.get(code_key)
        if claimed and claimed[0] != item_name:
            conflicts.append(
                f"DKSH Item Code {code} belongs to both Item {claimed[0]} and Item {item_name}"
            )
            continue

        planned_updates[item_name] = code
        current_by_item[item_name] = code
        claimed_codes[code_key] = (item_name, code)

    return planned_updates, conflicts


def _collect_master_mapping_candidates(
    candidates: dict[str, list[tuple[str, str]]],
    eligible_item_names: set[str] | None,
) -> None:
    if not frappe.db.table_exists(DKSH_MAPPING_DOCTYPE):
        return
    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            DKSH_MAPPING_DOCTYPE,
            fields=["item", "item_channel", "dksh_item_code"],
            order_by="item asc, name asc",
        ),
    )
    for row in rows:
        item_name = _text(row.get("item"))
        code = _text(row.get("dksh_item_code"))
        mapping_channel = _text(row.get("item_channel"))
        if (
            item_name
            and code
            and mapping_channel == CHANNEL_BOTH
            and (eligible_item_names is None or item_name in eligible_item_names)
        ):
            candidates[item_name].append((DKSH_MAPPING_DOCTYPE, code))


def _collect_partner_mapping_candidates(
    candidates: dict[str, list[tuple[str, str]]],
    eligible_item_names: set[str] | None,
) -> None:
    if eligible_item_names is None or not frappe.db.table_exists(PARTNER_MAPPING_DOCTYPE):
        return
    rows = cast(
        list[dict[str, Any]],
        frappe.get_all(
            PARTNER_MAPPING_DOCTYPE,
            filters={"partner_company": DKSH_COMPANY, "active": 1},
            fields=["parent", "external_item_code"],
            order_by="parent asc, name asc",
        ),
    )
    for row in rows:
        item_name = _text(row.get("parent"))
        code = _text(row.get("external_item_code"))
        if item_name in eligible_item_names and code:
            candidates[item_name].append((PARTNER_MAPPING_DOCTYPE, code))


def _migrate_pending_customers() -> None:
    if not frappe.db.has_column("Customer", "customer_onboarding_state"):
        return
    customer_names = cast(
        list[str],
        frappe.get_all(
            "Customer",
            filters={"customer_onboarding_state": PENDING_DKSH_CUSTOMER_STATE},
            pluck="name",
            order_by="name asc",
        ),
    )
    for customer_name in customer_names:
        clear_workflow_actions("Customer", customer_name)
        frappe.db.set_value(
            "Customer",
            customer_name,
            "customer_onboarding_state",
            customer_onboarding.PENDING_ACCOUNTING_STATE,
            update_modified=False,
        )
        customer = frappe.get_doc("Customer", customer_name)
        process_workflow_actions(customer, "on_update")


def _remove_dksh_workflow_actions() -> None:
    frappe.db.delete(
        "Workflow Action",
        {"reference_doctype": DKSH_MAPPING_DOCTYPE},
    )
    frappe.db.delete(
        "Workflow Action",
        {
            "reference_doctype": "Customer",
            "workflow_state": PENDING_DKSH_CUSTOMER_STATE,
        },
    )


def _remove_dksh_workflow_configuration() -> None:
    _delete_doc_if_exists("Workflow", DKSH_MAPPING_WORKFLOW)
    for action_name in DKSH_WORKFLOW_ACTION_MASTERS:
        _delete_doc_if_exists("Workflow Action Master", action_name)
    for state_name in DKSH_WORKFLOW_STATES:
        _delete_doc_if_exists("Workflow State", state_name)


def _remove_dksh_price_list() -> None:
    frappe.db.delete("Item Price", {"price_list": DKSH_PRICE_LIST})
    _delete_doc_if_exists("Price List", DKSH_PRICE_LIST)
    cache = frappe.cache
    if cache is not None:
        cache.hdel("price_list_details", DKSH_PRICE_LIST)


def _remove_dksh_permissions_and_roles() -> None:
    frappe.db.delete("Custom DocPerm", {"role": ["in", DKSH_ROLES]})
    frappe.db.delete("Has Role", {"role": ["in", DKSH_ROLES]})
    for role_name in DKSH_ROLES:
        _delete_doc_if_exists("Role", role_name)


def _reset_sales_order_item_grid_settings() -> None:
    settings = _sales_order_grid_settings()
    for setting in settings:
        user = _text(setting.get("user"))
        data = _parse_user_settings(_text(setting.get("data")))
        grid_view = data.get("GridView")
        if not isinstance(grid_view, dict) or "Sales Order Item" not in grid_view:
            continue
        del grid_view["Sales Order Item"]
        frappe.db.sql(
            "UPDATE `__UserSettings` SET data = %(data)s WHERE user = %(user)s AND doctype = 'Sales Order'",
            {"data": json.dumps(data), "user": user},
        )
        cache = frappe.cache
        if cache is not None:
            cache.hset("_user_settings", f"Sales Order::{user}", None)


def _sales_order_grid_settings() -> list[dict[str, Any]]:
    settings = cast(
        list[dict[str, Any]],
        frappe.db.sql(
            "SELECT user, data FROM `__UserSettings` WHERE doctype = 'Sales Order' ORDER BY user ASC",
            as_dict=True,
        ),
    )
    matching_settings: list[dict[str, Any]] = []
    for setting in settings:
        grid_view = _parse_user_settings(_text(setting.get("data"))).get("GridView")
        if isinstance(grid_view, dict) and "Sales Order Item" in grid_view:
            matching_settings.append(setting)
    return matching_settings


def _remove_retired_custom_fields_and_columns() -> None:
    for doctype, fieldnames in RETIRED_CUSTOM_FIELDS.items():
        for fieldname in fieldnames:
            custom_field_names = cast(
                list[str],
                frappe.get_all(
                    "Custom Field",
                    filters={"dt": doctype, "fieldname": fieldname},
                    pluck="name",
                    order_by="name asc",
                ),
            )
            for custom_field_name in custom_field_names:
                frappe.delete_doc(
                    "Custom Field",
                    custom_field_name,
                    force=True,
                    ignore_permissions=True,
                    delete_permanently=True,
                )
            _drop_column_if_exists(doctype, fieldname)


def _remove_retired_doctypes() -> None:
    frappe.db.delete("Singles", {"doctype": DKSH_SETTINGS_DOCTYPE})
    for doctype in (
        DKSH_MAPPING_DOCTYPE,
        PARTNER_MAPPING_DOCTYPE,
        DKSH_SETTINGS_DOCTYPE,
    ):
        if frappe.db.table_exists(doctype):
            frappe.db.delete(doctype)
        _delete_doc_if_exists("DocType", doctype)
        _drop_table_if_exists(doctype)


def _delete_doc_if_exists(doctype: str, name: str) -> None:
    if not frappe.db.exists(doctype, name):
        return
    frappe.delete_doc(
        doctype,
        name,
        force=True,
        ignore_permissions=True,
        delete_permanently=True,
    )


def _drop_column_if_exists(doctype: str, fieldname: str) -> None:
    if not frappe.db.has_column(doctype, fieldname):
        return
    frappe.db.sql_ddl(
        f"ALTER TABLE `tab{_ident(doctype)}` DROP COLUMN `{_ident(fieldname)}`"
    )


def _drop_table_if_exists(doctype: str) -> None:
    if not frappe.db.table_exists(doctype):
        return
    frappe.db.sql_ddl(f"DROP TABLE `tab{_ident(doctype)}`")


def _parse_user_settings(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _count_if_column(
    doctype: str,
    fieldname: str,
    filters: dict[str, Any],
) -> int:
    if not frappe.db.has_column(doctype, fieldname):
        return 0
    return frappe.db.count(doctype, filters=filters)


def _ident(name: str) -> str:
    """Whitelist a trusted table or column identifier before SQL interpolation."""
    if not _IDENT_RE.fullmatch(name):
        frappe.throw(f"Unsafe SQL identifier: {name!r}")
    return name


def _text(value: object) -> str:
    return str(value or "").strip()
