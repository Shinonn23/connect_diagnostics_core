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
            "fieldname": "posting_date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 100,
            "align": "left",
        },
        {
            "fieldname": "voucher_type",
            "label": _("Book"),
            "fieldtype": "Data",
            "width": 100,
            "align": "left",
        },
        {
            "fieldname": "voucher_no",
            "label": _("Voucher No"),
            "fieldtype": "Dynamic Link",
            "options": "voucher_type",
            "width": 180,
            "align": "left",
        },
        {
            "fieldname": "description",
            "label": _("Description"),
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "fieldname": "debit",
            "label": _("Debit"),
            "fieldtype": "Currency",
            "width": 150,
            "align": "right",
        },
        {
            "fieldname": "credit",
            "label": _("Credit"),
            "fieldtype": "Currency",
            "width": 150,
            "align": "left",
        },
        {
            "fieldname": "balance",
            "label": _("Balance"),
            "fieldtype": "Currency",
            "width": 160,
            "align": "left",
        },
    ]


def _build_department_condition(filters: frappe._dict, params: dict) -> str:
    departments = filters.get("department") or []
    if isinstance(departments, str):
        departments = [d.strip() for d in departments.split(",") if d.strip()]

    if departments:
        params["accounting_departments"] = tuple(departments)
        return " AND gle.department IN %(accounting_departments)s"
    return ""


def _get_accounts_in_range(filters: frappe._dict) -> list[dict]:
    """Get all accounts within the specified account number range."""
    params: dict = {
        "company": filters.company,
        "from_account": filters.from_account,
        "to_account": filters.to_account,
    }
    dept_condition = _build_department_condition(filters, params)

    # Get accounts that have any GL Entry (either before or within the period)
    rows = frappe.db.sql(
        """
        SELECT DISTINCT
            a.account_number,
            a.account_name
        FROM `tabGL Entry` gle
        INNER JOIN `tabAccount` a ON a.name = gle.account
        WHERE gle.company = %(company)s
            AND gle.docstatus = 1
            AND gle.is_cancelled = 0
            AND a.account_number >= %(from_account)s
            AND a.account_number <= %(to_account)s
        """
        + dept_condition
        + """
        ORDER BY a.account_number
        """,
        params,
        as_dict=True,
    )
    return rows


def _get_opening_balance(filters: frappe._dict, account_number: str) -> float:
    """Get opening balance (sum of debit - credit) for an account before from_date."""
    params: dict = {
        "company": filters.company,
        "from_date": filters.from_date,
        "account_number": account_number,
    }
    dept_condition = _build_department_condition(filters, params)

    result = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(gle.debit) - SUM(gle.credit), 0) AS opening_balance
        FROM `tabGL Entry` gle
        INNER JOIN `tabAccount` a ON a.name = gle.account
        WHERE gle.company = %(company)s
            AND gle.posting_date < %(from_date)s
            AND gle.docstatus = 1
            AND gle.is_cancelled = 0
            AND a.account_number = %(account_number)s
        """
        + dept_condition,
        params,
        as_dict=True,
    )
    return flt(result[0].opening_balance) if result else 0.0


def _get_gl_entries(filters: frappe._dict, account_number: str) -> list[dict]:
    """Get GL entries for a specific account within the date range."""
    params: dict = {
        "company": filters.company,
        "from_date": filters.from_date,
        "to_date": filters.to_date,
        "account_number": account_number,
    }
    dept_condition = _build_department_condition(filters, params)

    rows = frappe.db.sql(
        """
        SELECT
            gle.posting_date,
            gle.voucher_type,
            gle.voucher_no,
            gle.against,
            gle.remarks,
            gle.debit,
            gle.credit
        FROM `tabGL Entry` gle
        INNER JOIN `tabAccount` a ON a.name = gle.account
        WHERE gle.company = %(company)s
            AND gle.posting_date >= %(from_date)s
            AND gle.posting_date <= %(to_date)s
            AND gle.docstatus = 1
            AND gle.is_cancelled = 0
            AND a.account_number = %(account_number)s
        """
        + dept_condition
        + """
        ORDER BY gle.posting_date, gle.creation
        """,
        params,
        as_dict=True,
    )
    return rows


def _get_voucher_type_abbr(voucher_type: str) -> str:
    """Convert voucher type to Thai accounting book abbreviation."""
    abbr_map = {
        "Journal Entry": "JV",
        "Sales Invoice": "SI",
        "Purchase Invoice": "PI",
        "Payment Entry": "PE",
        "Stock Entry": "SE",
        "Delivery Note": "DN",
        "Purchase Receipt": "PR",
    }
    return abbr_map.get(voucher_type, voucher_type[:2].upper() if voucher_type else "")


def _get_data(filters: frappe._dict) -> list[dict]:
    accounts = _get_accounts_in_range(filters)
    data: list[dict] = []

    for account in accounts:
        acct_num = account["account_number"]
        acct_name = account["account_name"]

        opening_balance = _get_opening_balance(filters, acct_num)
        gl_entries = _get_gl_entries(filters, acct_num)

        # Skip account if no opening balance and no movement
        if not opening_balance and not gl_entries:
            continue

        # Account header row - shows account number, name, and opening balance
        data.append(
            {
                "posting_date": None,
                "voucher_type": "",
                "voucher_no": "",
                "description": f"{acct_num}\t\t{acct_name}",
                "debit": None,
                "credit": None,
                "balance": flt(opening_balance, 2),
                "bold": 1,
                "indent": 0,
            }
        )

        running_balance = opening_balance

        for gle in gl_entries:
            debit = flt(gle.get("debit"))
            credit = flt(gle.get("credit"))
            running_balance += debit - credit

            # Build description from against + remarks
            desc_parts = []
            if gle.get("against"):
                desc_parts.append(gle["against"])
            if gle.get("remarks"):
                desc_parts.append(gle["remarks"])
            description = " | ".join(desc_parts) if desc_parts else ""

            data.append(
                {
                    "posting_date": gle["posting_date"],
                    "voucher_type": gle["voucher_type"],
                    "voucher_no": gle["voucher_no"],
                    "description": description,
                    "debit": debit if debit else None,
                    "credit": credit if credit else None,
                    "balance": flt(running_balance, 2),
                    "indent": 1,
                }
            )

        # Account total row (movement totals for this account)
        total_debit = sum(flt(e.get("debit")) for e in gl_entries)
        total_credit = sum(flt(e.get("credit")) for e in gl_entries)

        if gl_entries:
            data.append(
                {
                    "posting_date": None,
                    "voucher_type": "",
                    "voucher_no": "",
                    "description": _("Total {0}").format(acct_num),
                    "debit": total_debit if total_debit else None,
                    "credit": total_credit if total_credit else None,
                    "balance": flt(running_balance, 2),
                    "bold": 1,
                    "indent": 0,
                }
            )

    return data
