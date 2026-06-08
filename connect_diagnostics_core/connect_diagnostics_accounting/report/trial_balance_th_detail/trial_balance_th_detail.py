# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters: dict | None = None) -> tuple[list, list]:
    filters = frappe._dict(filters or {})
    _validate_filters(filters)
    columns = _get_columns()
    data = _get_data(filters)
    return columns, data


def _validate_filters(filters: frappe._dict) -> None:
    if not filters.company:
        frappe.throw(_("Company is required"))
    if not filters.from_date or not filters.to_date:
        frappe.throw(_("From Date and To Date are required"))

    from_date_obj = getdate(filters.from_date)
    to_date_obj = getdate(filters.to_date)
    if from_date_obj and to_date_obj and from_date_obj > to_date_obj:
        frappe.throw(_("From Date cannot be greater than To Date"))

    if not filters.get("from_account"):
        filters.from_account = "1000-00"
    if not filters.get("to_account"):
        filters.to_account = "9999-99"


def _get_columns() -> list[dict]:
    return [
        {
            "fieldname": "account_number",
            "label": _("Account Number"),
            "fieldtype": "Data",
            "width": 110,
            "align": "left",
        },
        {
            "fieldname": "department",
            "label": _("Accounting Department"),
            "fieldtype": "Link",
            "options": "Accounting Department",
            "width": 130,
            "align": "left",
        },
        {
            "fieldname": "account_name",
            "label": _("Account Name"),
            "fieldtype": "Data",
            "width": 260,
            "align": "left",
        },
        {"fieldname": "opening_debit", "label": _("Opening Debit"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "opening_credit", "label": _("Opening Credit"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "movement_debit", "label": _("Movement Debit"), "fieldtype": "Currency", "width": 150},
        {
            "fieldname": "movement_credit",
            "label": _("Movement Credit"),
            "fieldtype": "Currency",
            "width": 150,
        },
        {"fieldname": "closing_debit", "label": _("Closing Debit"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "closing_credit", "label": _("Closing Credit"), "fieldtype": "Currency", "width": 150},
    ]


def _build_department_condition(filters: frappe._dict, params: dict) -> str:
    departments = filters.get("department") or []
    if isinstance(departments, str):
        departments = [d.strip() for d in departments.split(",") if d.strip()]

    if departments:
        params["accounting_departments"] = tuple(departments)
        return " AND gle.department IN %(accounting_departments)s"
    return ""


def _get_opening_balances(filters: frappe._dict) -> dict[tuple[str, str], dict]:
    params: dict = {
        "company": filters.company,
        "from_date": filters.from_date,
        "from_account": filters.from_account,
        "to_account": filters.to_account,
    }
    dept_condition = _build_department_condition(filters, params)

    rows = frappe.db.sql(
        """
        SELECT
            a.account_number,
            a.account_name,
            gle.department,
            SUM(gle.debit) AS total_debit,
            SUM(gle.credit) AS total_credit
        FROM `tabGL Entry` gle
        INNER JOIN `tabAccount` a ON a.name = gle.account
        WHERE gle.company = %(company)s
            AND gle.posting_date < %(from_date)s
            AND gle.docstatus = 1
            AND gle.is_cancelled = 0
            AND a.account_number >= %(from_account)s
            AND a.account_number <= %(to_account)s
        """
        + dept_condition
        + """
        GROUP BY a.account_number, a.account_name, gle.department
        ORDER BY a.account_number, gle.department
        """,
        params,
        as_dict=True,
    )

    result: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row.account_number, row.department or "")
        result[key] = {
            "account_number": row.account_number,
            "account_name": row.account_name,
            "department": row.department,
            "opening_debit": flt(row.total_debit),
            "opening_credit": flt(row.total_credit),
        }
    return result


def _get_movement_balances(filters: frappe._dict) -> dict[tuple[str, str], dict]:
    params: dict = {
        "company": filters.company,
        "from_date": filters.from_date,
        "to_date": filters.to_date,
        "from_account": filters.from_account,
        "to_account": filters.to_account,
    }
    dept_condition = _build_department_condition(filters, params)

    rows = frappe.db.sql(
        """
        SELECT
            a.account_number,
            a.account_name,
            gle.department,
            SUM(gle.debit) AS total_debit,
            SUM(gle.credit) AS total_credit
        FROM `tabGL Entry` gle
        INNER JOIN `tabAccount` a ON a.name = gle.account
        WHERE gle.company = %(company)s
            AND gle.posting_date >= %(from_date)s
            AND gle.posting_date <= %(to_date)s
            AND gle.docstatus = 1
            AND gle.is_cancelled = 0
            AND a.account_number >= %(from_account)s
            AND a.account_number <= %(to_account)s
        """
        + dept_condition
        + """
        GROUP BY a.account_number, a.account_name, gle.department
        ORDER BY a.account_number, gle.department
        """,
        params,
        as_dict=True,
    )

    result: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row.account_number, row.department or "")
        result[key] = {
            "account_number": row.account_number,
            "account_name": row.account_name,
            "department": row.department,
            "movement_debit": flt(row.total_debit),
            "movement_credit": flt(row.total_credit),
        }
    return result


def _net_to_debit_credit(net: float) -> tuple[float, float]:
    if net > 0:
        return net, 0.0
    return 0.0, -net


def _get_data(filters: frappe._dict) -> list[dict]:
    opening = _get_opening_balances(filters)
    movement = _get_movement_balances(filters)

    all_keys = sorted(set(opening.keys()) | set(movement.keys()))

    data: list[dict] = []
    total_opening_debit = 0.0
    total_opening_credit = 0.0
    total_movement_debit = 0.0
    total_movement_credit = 0.0
    total_closing_debit = 0.0
    total_closing_credit = 0.0

    for key in all_keys:
        op = opening.get(key, {})
        mv = movement.get(key, {})

        op_debit = flt(op.get("opening_debit"))
        op_credit = flt(op.get("opening_credit"))
        mv_debit = flt(mv.get("movement_debit"))
        mv_credit = flt(mv.get("movement_credit"))

        opening_net = op_debit - op_credit
        opening_debit, opening_credit = _net_to_debit_credit(opening_net)

        movement_net = mv_debit - mv_credit
        movement_debit, movement_credit = _net_to_debit_credit(movement_net)

        closing_net = opening_net + movement_net
        closing_debit, closing_credit = _net_to_debit_credit(closing_net)

        if not filters.get("show_zero_values") and not (opening_net or movement_net):
            continue

        account_number = op.get("account_number") or mv.get("account_number", "")
        account_name = op.get("account_name") or mv.get("account_name", "")
        department = op.get("department") or mv.get("department", "")

        total_opening_debit += opening_debit
        total_opening_credit += opening_credit
        total_movement_debit += movement_debit
        total_movement_credit += movement_credit
        total_closing_debit += closing_debit
        total_closing_credit += closing_credit

        data.append(
            {
                "account_number": account_number,
                "department": department,
                "account_name": account_name,
                "opening_debit": opening_debit,
                "opening_credit": opening_credit,
                "movement_debit": movement_debit,
                "movement_credit": movement_credit,
                "closing_debit": closing_debit,
                "closing_credit": closing_credit,
            }
        )

    data.append(
        {
            "account_number": "",
            "department": "",
            "account_name": _("Total"),
            "opening_debit": total_opening_debit,
            "opening_credit": total_opening_credit,
            "movement_debit": total_movement_debit,
            "movement_credit": total_movement_credit,
            "closing_debit": total_closing_debit,
            "closing_credit": total_closing_credit,
            "bold": 1,
        }
    )

    return data
