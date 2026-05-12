// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.query_reports["Trial Balance TH"] = {
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
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "from_account",
			label: __("Account From"),
			fieldtype: "Data",
			default: "1000-00",
		},
		{
			fieldname: "to_account",
			label: __("Account To"),
			fieldtype: "Data",
			default: "9999-99",
		},
		{
			fieldname: "cost_center",
			label: __("Department"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Cost Center", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
			options: "Cost Center",
		},
		{
			fieldname: "show_zero_values",
			label: __("Show Zero Values"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
