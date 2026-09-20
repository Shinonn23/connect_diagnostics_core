// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.query_reports["Outstanding Borrowed Items"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "as_of_date",
			label: __("As of Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "request_usage",
			label: __("Request Usage"),
			fieldtype: "Select",
			options: "\nEmployee Borrow\nCustomer Demo\nCustomer Loan",
		},
		{
			fieldname: "responsible_employee",
			label: __("Responsible Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "material_request",
			label: __("Material Request"),
			fieldtype: "Link",
			options: "Material Request",
		},
		{
			fieldname: "overdue_only",
			label: __("Overdue Only"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
