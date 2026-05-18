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
		{"fieldname": "account_number", "label": _("Account Number"), "fieldtype": "Data", "width": 110},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 130,
		},
		{"fieldname": "account_name", "label": _("Account Name"), "fieldtype": "Data", "width": 260},
		{"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "width": 160},
	]


def _get_data(filters: frappe._dict) -> list[dict]:
	conditions = []
	params = {
		"company": filters.company,
		"to_date": filters.to_date,
		"from_account": filters.from_account,
		"to_account": filters.to_account,
	}

	if filters.get("cost_center"):
		conditions.append("gle.cost_center = %(cost_center)s")
		params["cost_center"] = filters.cost_center

	where_clause = ""
	if conditions:
		where_clause = " AND " + " AND ".join(conditions)

	rows = frappe.db.sql(
		"""
		SELECT
			a.account_number,
			a.account_name,
			gle.cost_center,
			SUM(gle.debit) - SUM(gle.credit) AS net_balance
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` a ON a.name = gle.account
		WHERE gle.company = %(company)s
			AND gle.posting_date <= %(to_date)s
			AND gle.docstatus = 1
			AND gle.is_cancelled = 0
			AND a.account_number >= %(from_account)s
			AND a.account_number <= %(to_account)s
		"""
		+ where_clause
		+ """
		GROUP BY a.account_number, a.account_name, gle.cost_center
		ORDER BY a.account_number, gle.cost_center
		""",
		params,
		as_dict=True,
	)

	data = []
	total_debit = 0.0
	total_credit = 0.0

	for row in rows:
		net = flt(row.net_balance)
		debit = net if net > 0 else 0.0
		credit = -net if net < 0 else 0.0

		if not filters.get("show_zero_values") and not net:
			continue

		total_debit += debit
		total_credit += credit

		data.append(
			{
				"account_number": row.account_number,
				"cost_center": row.cost_center,
				"account_name": row.account_name,
				"debit": debit,
				"credit": credit,
			}
		)

	data.append(
		{
			"account_number": "",
			"cost_center": "",
			"account_name": _("Total"),
			"debit": total_debit,
			"credit": total_credit,
			"bold": 1,
		}
	)

	return data


def _build_params(filters: frappe._dict) -> tuple[str, dict]:
	params: dict = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"from_account": filters.from_account,
		"to_account": filters.to_account,
	}

	cost_centers = filters.get("cost_center") or []
	if isinstance(cost_centers, str):
		cost_centers = [c.strip() for c in cost_centers.split(",") if c.strip()]

	if not cost_centers:
		return "", params

	params["cost_centers"] = tuple(cost_centers)
	return "AND gle.cost_center IN %(cost_centers)s", params
