# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Customer Borrow stock transfers and Employee-owned warehouse controls."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

BORROW_TYPE = "Customer Borrow"
REVIEW_STATES = frozenset(
    {
        "Stock Transfer Pending Approval",
        "Stock Transfer Approved",
        "Emergency Stock Movement Pending Review",
        "Emergency Stock Movement Approved",
    }
)
REVIEW_HEADER_FIELDS = (
    "borrow_material_request",
    "company",
    "purpose",
    "stock_entry_type",
    "from_warehouse",
    "to_warehouse",
    "add_to_transit",
    "outgoing_stock_entry",
    "posting_date",
    "posting_time",
    "set_posting_time",
    "freeze_exception",
    "freeze_exception_reason",
    "apply_putaway_rule",
)
REVIEW_ROW_FIELDS = (
    "name",
    "item_code",
    "item_name",
    "description",
    "qty",
    "uom",
    "stock_uom",
    "conversion_factor",
    "transfer_qty",
    "s_warehouse",
    "t_warehouse",
    "material_request",
    "material_request_item",
    "batch_no",
    "serial_no",
    "serial_and_batch_bundle",
    "use_serial_batch_fields",
    "allow_zero_valuation_rate",
    "basic_rate",
    "is_finished_item",
)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _employee(
    employee: str, company: str, *, check_permission: bool = False, for_update: bool = False
) -> Any:
    if check_permission:
        permission = "select" if frappe.only_has_select_perm("Employee") else "read"
        frappe.has_permission("Employee", permission, employee, throw=True)
    record = frappe.db.get_value(
        "Employee",
        employee,
        ["company", "status", "customer_borrow_warehouse"],
        as_dict=True,
        for_update=for_update,
    )
    if not record or record.company != company or record.status != "Active":
        frappe.throw(_("Select an active Employee in the Material Request company."))
    return record


def _warehouse(warehouse: str, company: str, *, group: bool) -> Any:
    record = frappe.db.get_value(
        "Warehouse", warehouse, ["company", "is_group", "disabled", "parent_warehouse"], as_dict=True
    )
    if not record or record.company != company or bool(record.is_group) != group or record.disabled:
        frappe.throw(_("Borrow Warehouse must be an enabled warehouse in the selected company."))
    return record


def _company_root(company: str) -> str:
    roots = frappe.get_all(
        "Warehouse",
        filters={"company": company, "parent_warehouse": ["is", "not set"], "is_group": 1, "disabled": 0},
        pluck="name",
        limit_page_length=2,
    )
    if len(roots) != 1:
        frappe.throw(
            _("Company must have exactly one enabled root Warehouse before creating a Borrow Warehouse.")
        )
    return cast(str, roots[0])


def _warehouse_name(label: str, company: str) -> str:
    abbr = frappe.db.get_value("Company", company, "abbr")
    if not abbr:
        frappe.throw(_("Company abbreviation is required to create a Borrow Warehouse."))
    return f"{label} - {abbr}"


def _ensure_warehouse(employee: str, company: str, *, may_create: bool) -> str:
    # Stable ordering also serializes concurrent creators for the same employee.
    frappe.db.get_value("Company", company, "name", for_update=True)
    employee_record = _employee(employee, company, for_update=True)
    mapped = _text(employee_record.customer_borrow_warehouse)
    if mapped:
        _warehouse(mapped, company, group=False)
        other = frappe.db.exists("Employee", {"customer_borrow_warehouse": mapped, "name": ["!=", employee]})
        if other:
            frappe.throw(_("Borrow Warehouse is already assigned to another Employee."))
        return mapped
    if not may_create:
        frappe.throw(_("Create the Employee's Borrow Warehouse before submitting this request."))

    frappe.has_permission("Warehouse", "create", throw=True)
    root = _company_root(company)
    group_name = _warehouse_name("Borrow", company)
    group = frappe.db.get_value(
        "Warehouse", group_name, ["company", "is_group", "disabled", "parent_warehouse"], as_dict=True
    )
    if group:
        if group.company != company or not group.is_group or group.disabled or group.parent_warehouse != root:
            frappe.throw(_("The Borrow Warehouse group name is already used by an incompatible Warehouse."))
    else:
        frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": "Borrow",
                "company": company,
                "parent_warehouse": root,
                "is_group": 1,
            }
        ).insert()

    label = f"Customer Borrow - {employee}"
    name = _warehouse_name(label, company)
    if frappe.db.exists("Warehouse", name):
        frappe.throw(
            _("A Borrow Warehouse with this Employee name already exists without an ownership mapping.")
        )
    warehouse = frappe.get_doc(
        {
            "doctype": "Warehouse",
            "warehouse_name": label,
            "company": company,
            "parent_warehouse": group_name,
            "is_group": 0,
        }
    ).insert()
    # The API authorizes this narrow assignment; Employee's ordinary HR fields stay untouched.
    frappe.db.set_value("Employee", employee, "customer_borrow_warehouse", warehouse.name)
    return cast(str, warehouse.name)


@frappe.whitelist(methods=["POST"])
def ensure_employee_borrow_warehouse(
    employee: str, company: str, material_request: str | None = None
) -> dict[str, Any]:
    employee = _text(employee)
    company = _text(company)
    material_request = _text(material_request)
    if not employee or not company:
        frappe.throw(_("Employee and Company are required."))
    frappe.has_permission("Company", "read", company, throw=True)
    if material_request:
        frappe.has_permission("Material Request", "read", material_request, throw=True)
        frappe.has_permission("Material Request", "write", material_request, throw=True)
        request = frappe.db.get_value(
            "Material Request",
            material_request,
            ["company", "docstatus", "material_request_type"],
            as_dict=True,
        )
        if (
            not request
            or request.company != company
            or request.docstatus != 0
            or request.material_request_type != BORROW_TYPE
        ):
            frappe.throw(_("Select a draft Customer Borrow Material Request in the same company."))
    else:
        frappe.has_permission("Material Request", "create", throw=True)
    _employee(employee, company, check_permission=True)
    warehouse = _ensure_warehouse(employee, company, may_create=True)
    return {"data": {"warehouse": warehouse}, "message": _("Borrow Warehouse is ready.")}


def validate_employee(doc: Document, method: str) -> None:
    del method
    if doc.is_new():
        if doc.get("customer_borrow_warehouse"):
            frappe.throw(_("Borrow Warehouse is assigned through the Customer Borrow action."))
        return
    saved = frappe.db.get_value("Employee", doc.name, ["customer_borrow_warehouse", "company"], as_dict=True)
    if not saved:
        return
    if _text(doc.get("customer_borrow_warehouse")) != _text(saved.customer_borrow_warehouse):
        frappe.throw(_("Borrow Warehouse cannot be changed on the Employee form."))
    if saved.customer_borrow_warehouse and doc.get("company") != saved.company:
        frappe.throw(_("Employee company cannot change while a Borrow Warehouse is assigned."))


def before_validate_material_request(doc: Document, method: str) -> None:
    del method
    if doc.get("material_request_type") != BORROW_TYPE:
        return
    target = _text(doc.get("borrow_warehouse"))
    if target:
        if not doc.get("set_warehouse"):
            doc.set("set_warehouse", target)
        for row in doc.get("items") or []:
            if not row.get("warehouse"):
                row.set("warehouse", target)


def _validate_request_snapshot(doc: Document) -> None:
    previous = doc.get_doc_before_save()
    if not previous or previous.docstatus != 1:
        return
    fields = (
        "material_request_type",
        "company",
        "borrow_customer",
        "borrow_employee",
        "borrow_warehouse",
        "borrow_expected_return_date",
        "borrow_fulfillment_status",
        "set_from_warehouse",
        "set_warehouse",
    )
    if any(previous.get(field) != doc.get(field) for field in fields):
        frappe.throw(_("Submitted Customer Borrow request details cannot be changed."))
    rows = (
        "name",
        "item_code",
        "qty",
        "uom",
        "stock_uom",
        "conversion_factor",
        "stock_qty",
        "warehouse",
        "from_warehouse",
    )
    if [tuple(row.get(field) for field in rows) for row in previous.get("items") or []] != [
        tuple(row.get(field) for field in rows) for row in doc.get("items") or []
    ]:
        frappe.throw(_("Submitted Customer Borrow items cannot be changed."))


def validate_material_request(doc: Document, method: str) -> None:
    del method
    if doc.get("material_request_type") != BORROW_TYPE:
        if any(
            doc.get(field)
            for field in (
                "borrow_customer",
                "borrow_employee",
                "borrow_warehouse",
                "borrow_expected_return_date",
            )
        ):
            frappe.throw(_("Customer Borrow fields require a Customer Borrow Material Request."))
        return
    company = _text(doc.get("company"))
    customer = _text(doc.get("borrow_customer"))
    employee = _text(doc.get("borrow_employee"))
    target = _text(doc.get("borrow_warehouse"))
    if not company or not customer or not employee or not target:
        frappe.throw(_("Company, Customer, Employee, and Borrow Warehouse are required."))
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Select an existing Customer."))
    frappe.has_permission("Customer", "read", customer, throw=True)
    employee_record = _employee(employee, company, check_permission=True)
    if employee_record.customer_borrow_warehouse != target:
        frappe.throw(_("Borrow Warehouse must match the selected Employee's mapped warehouse."))
    _warehouse(target, company, group=False)
    frappe.has_permission("Warehouse", "read", target, throw=True)
    if doc.get("set_warehouse") != target:
        frappe.throw(_("Target Warehouse must match the Employee Borrow Warehouse."))
    items = doc.get("items") or []
    if not items:
        frappe.throw(_("Add at least one Stock Item to the Customer Borrow request."))
    stock_items = frappe.get_all(
        "Item",
        filters={"name": ["in", [row.get("item_code") for row in items]]},
        fields=["name", "is_stock_item", "stock_uom"],
        limit_page_length=len(items),
    )
    stock_by_code = {item.name: item for item in stock_items}
    for row in items:
        item = stock_by_code.get(row.get("item_code"))
        if not item or not item.is_stock_item or row.get("stock_uom") != item.stock_uom:
            frappe.throw(_("Every Customer Borrow row must contain a valid Stock Item and Stock UOM."))
        source = _text(row.get("from_warehouse") or doc.get("set_from_warehouse"))
        if not source or source == target or row.get("warehouse") != target:
            frappe.throw(
                _("Every row needs a different Source Warehouse and the Employee Borrow Warehouse as Target.")
            )
        _warehouse(source, company, group=False)
        frappe.has_permission("Warehouse", "read", source, throw=True)
        frappe.has_permission("Item", "read", row.get("item_code"), throw=True)
        if (
            flt(row.get("qty")) <= 0
            or flt(row.get("conversion_factor")) <= 0
            or flt(row.get("stock_qty")) <= 0
        ):
            frappe.throw(_("Customer Borrow quantity and UOM conversion must be positive."))
        if (
            abs(flt(row.get("qty")) * flt(row.get("conversion_factor")) - flt(row.get("stock_qty")))
            > 0.000001
        ):
            frappe.throw(_("Customer Borrow Stock Qty must match the UOM conversion."))
    _validate_request_snapshot(doc)


def before_update_after_submit_material_request(doc: Document, method: str) -> None:
    del method
    if doc.get("material_request_type") == BORROW_TYPE:
        _validate_request_snapshot(doc)


def on_submit_material_request(doc: Document, method: str) -> None:
    del method
    if doc.get("material_request_type") == BORROW_TYPE:
        frappe.db.set_value(
            "Material Request", doc.name, "borrow_fulfillment_status", "Not Sent", update_modified=False
        )


def before_cancel_material_request(doc: Document, method: str) -> None:
    del method
    if doc.get("material_request_type") != BORROW_TYPE:
        return
    frappe.db.get_value("Material Request", doc.name, "name", for_update=True)
    if frappe.db.exists("Stock Entry", {"borrow_material_request": doc.name, "docstatus": 1}):
        frappe.throw(_("Cancel submitted Customer Borrow Stock Entries before cancelling the request."))


def _request_for_stock_entry(doc: Document) -> Document | None:
    names = {_text(doc.get("borrow_material_request"))}
    names.update(_text(row.get("material_request")) for row in doc.get("items") or [])
    if doc.name and not doc.is_new():
        names.add(_text(frappe.db.get_value("Stock Entry", doc.name, "borrow_material_request")))
    names.discard("")
    if not names:
        return None
    types = frappe.get_all(
        "Material Request",
        filters={"name": ["in", list(names)]},
        fields=["name", "material_request_type"],
        limit_page_length=len(names),
    )
    borrow = {row.name for row in types if row.material_request_type == BORROW_TYPE}
    if not borrow:
        return None
    for name in borrow:
        frappe.has_permission("Material Request", "read", name, throw=True)
    if len(borrow) != 1 or names != borrow:
        frappe.throw(
            _("A Customer Borrow Stock Entry must reference exactly one Customer Borrow Material Request.")
        )
    return frappe.get_doc("Material Request", borrow.pop())


def _review_snapshot(doc: Document) -> tuple[Any, ...]:
    return (
        tuple(doc.get(field) for field in REVIEW_HEADER_FIELDS),
        tuple(tuple(row.get(field) for field in REVIEW_ROW_FIELDS) for row in doc.get("items") or []),
    )


def _validate_stock_entry_rows(doc: Document, request: Document) -> None:
    if request.docstatus != 1 or request.get("status") in {"Stopped", "Cancelled"}:
        frappe.throw(_("Customer Borrow Material Request must be submitted and active."))
    employee = _employee(_text(request.get("borrow_employee")), _text(request.get("company")))
    target = _text(request.get("borrow_warehouse"))
    if employee.customer_borrow_warehouse != target:
        frappe.throw(_("Employee Borrow Warehouse mapping changed after this request was submitted."))
    if (
        doc.get("borrow_material_request") != request.name
        or doc.get("company") != request.get("company")
        or doc.get("purpose") != "Material Transfer"
        or doc.get("stock_entry_type") != "Material Transfer"
        or doc.get("add_to_transit")
        or doc.get("outgoing_stock_entry")
        or doc.get("to_warehouse") != target
    ):
        frappe.throw(
            _("Customer Borrow requires a direct Material Transfer to the Employee Borrow Warehouse.")
        )
    request_rows = {row.name: row for row in request.get("items") or []}
    rows = doc.get("items") or []
    if not rows:
        frappe.throw(_("Add at least one Customer Borrow Stock Entry row."))
    for row in rows:
        request_row = request_rows.get(row.get("material_request_item"))
        source = (
            (request_row.get("from_warehouse") or request.get("set_from_warehouse")) if request_row else None
        )
        if (
            not request_row
            or row.get("material_request") != request.name
            or row.get("item_code") != request_row.get("item_code")
            or row.get("s_warehouse") != source
            or row.get("t_warehouse") != target
            or not source
            or source == target
            or row.get("uom") != request_row.get("uom")
            or abs(flt(row.get("conversion_factor")) - flt(request_row.get("conversion_factor"))) > 0.000001
            or flt(row.get("qty")) <= 0
            or flt(row.get("conversion_factor")) <= 0
            or abs(flt(row.get("transfer_qty")) - flt(row.get("qty")) * flt(row.get("conversion_factor")))
            > 0.000001
            or row.get("stock_uom") != request_row.get("stock_uom")
        ):
            frappe.throw(_("Customer Borrow Stock Entry row does not match the submitted request."))


def validate_stock_entry(doc: Document, method: str) -> None:
    del method
    request = _request_for_stock_entry(doc)
    if not request:
        if doc.get("borrow_material_request"):
            frappe.throw(_("Borrow Material Request must be a Customer Borrow request."))
        return
    previous = doc.get_doc_before_save()
    if (
        previous
        and previous.get("workflow_state") in REVIEW_STATES
        and _review_snapshot(doc) != _review_snapshot(previous)
    ):
        frappe.throw(_("Customer Borrow Stock Entry details cannot change after review starts."))
    _validate_stock_entry_rows(doc, request)


def _submitted_quantities(
    material_request: str, *, exclude_entry: str | None = None, for_update: bool = False
) -> dict[str, float]:
    conditions = "and se.name != %(exclude_entry)s" if exclude_entry else ""
    lock = " for update" if for_update else ""
    records = frappe.db.sql(
        "select sed.material_request_item, sed.transfer_qty "
        "from `tabStock Entry Detail` sed join `tabStock Entry` se on se.name = sed.parent "
        "where se.borrow_material_request = %(material_request)s and se.docstatus = 1 "
        "and sed.material_request = %(material_request)s " + conditions + lock,
        {"material_request": material_request, "exclude_entry": exclude_entry},
        as_dict=True,
    )
    totals: dict[str, float] = defaultdict(float)
    for row in records:
        totals[row.material_request_item] += flt(row.transfer_qty)
    return dict(totals)


def before_submit_stock_entry(doc: Document, method: str) -> None:
    del method
    request = _request_for_stock_entry(doc)
    if not request:
        return
    current = frappe.db.get_value(
        "Material Request",
        request.name,
        ["docstatus", "status", "material_request_type"],
        as_dict=True,
        for_update=True,
    )
    if (
        not current
        or current.docstatus != 1
        or current.status in {"Stopped", "Cancelled"}
        or current.material_request_type != BORROW_TYPE
    ):
        frappe.throw(_("Customer Borrow Material Request must be submitted and active."))
    request = frappe.get_doc("Material Request", request.name)
    _validate_stock_entry_rows(doc, request)
    totals = defaultdict(float, _submitted_quantities(request.name, exclude_entry=doc.name, for_update=True))
    for row in doc.get("items") or []:
        totals[row.get("material_request_item")] += flt(row.get("transfer_qty"))
    for row in request.get("items") or []:
        if totals[row.name] > flt(row.get("stock_qty")) + 0.000001:
            frappe.throw(_("Customer Borrow transfer exceeds the requested Stock Qty."))


def _reconcile_status(material_request: str, *, exclude_entry: str | None = None) -> None:
    current = frappe.db.get_value(
        "Material Request",
        material_request,
        ["docstatus", "material_request_type"],
        as_dict=True,
        for_update=True,
    )
    if not current or current.docstatus != 1 or current.material_request_type != BORROW_TYPE:
        return
    request = frappe.get_doc("Material Request", material_request)
    sent = _submitted_quantities(material_request, exclude_entry=exclude_entry, for_update=True)
    rows = request.get("items") or []
    status = (
        "Not Sent"
        if not any(sent.values())
        else (
            "Sent"
            if all(sent.get(row.name, 0) >= flt(row.get("stock_qty")) - 0.000001 for row in rows)
            else "Partially Sent"
        )
    )
    frappe.db.set_value(
        "Material Request", material_request, "borrow_fulfillment_status", status, update_modified=False
    )


def on_submit_stock_entry(doc: Document, method: str) -> None:
    del method
    if doc.get("borrow_material_request"):
        _reconcile_status(_text(doc.get("borrow_material_request")))


def before_cancel_stock_entry(doc: Document, method: str) -> None:
    del method
    if doc.get("borrow_material_request"):
        frappe.db.get_value("Material Request", doc.get("borrow_material_request"), "name", for_update=True)


def on_cancel_stock_entry(doc: Document, method: str) -> None:
    del method
    if doc.get("borrow_material_request"):
        _reconcile_status(_text(doc.get("borrow_material_request")), exclude_entry=doc.name)


@frappe.whitelist(methods=["POST"])
def get_customer_borrow_stock_entry_draft(material_request: str) -> dict[str, Any]:
    material_request = _text(material_request)
    if not material_request:
        frappe.throw(_("Material Request is required."))
    frappe.has_permission("Material Request", "read", material_request, throw=True)
    frappe.has_permission("Stock Entry", "create", throw=True)
    request = frappe.get_doc("Material Request", material_request)
    if (
        request.get("material_request_type") != BORROW_TYPE
        or request.docstatus != 1
        or request.get("status") == "Stopped"
    ):
        frappe.throw(_("Select a submitted and active Customer Borrow Material Request."))
    employee = _employee(
        _text(request.get("borrow_employee")), _text(request.get("company")), check_permission=True
    )
    target = _text(request.get("borrow_warehouse"))
    if employee.customer_borrow_warehouse != target:
        frappe.throw(_("Employee Borrow Warehouse mapping changed after this request was submitted."))
    sent = _submitted_quantities(request.name)
    draft = cast(StockEntry, frappe.new_doc("Stock Entry"))
    draft.set("company", request.get("company"))
    draft.set("purpose", "Material Transfer")
    draft.set("stock_entry_type", "Material Transfer")
    draft.set("borrow_material_request", request.name)
    draft.set("from_warehouse", request.get("set_from_warehouse"))
    draft.set("to_warehouse", target)
    for row in request.get("items") or []:
        remaining = flt(row.get("stock_qty")) - sent.get(row.name, 0)
        if remaining <= 0.000001:
            continue
        source = row.get("from_warehouse") or request.get("set_from_warehouse")
        frappe.has_permission("Item", "read", row.get("item_code"), throw=True)
        frappe.has_permission("Warehouse", "read", source, throw=True)
        frappe.has_permission("Warehouse", "read", target, throw=True)
        draft.append(
            "items",
            {
                "item_code": row.get("item_code"),
                "item_name": row.get("item_name"),
                "description": row.get("description"),
                "qty": remaining / flt(row.get("conversion_factor")),
                "uom": row.get("uom"),
                "stock_uom": row.get("stock_uom"),
                "conversion_factor": row.get("conversion_factor"),
                "transfer_qty": remaining,
                "s_warehouse": source,
                "t_warehouse": target,
                "material_request": request.name,
                "material_request_item": row.name,
            },
        )
    if not draft.get("items"):
        frappe.throw(_("All Customer Borrow quantities have already been sent."))
    draft.set_missing_values()
    return {"data": draft.as_dict(), "message": _("Customer Borrow Stock Entry draft is ready.")}
