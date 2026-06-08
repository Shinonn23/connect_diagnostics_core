// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.query_reports["General Ledger TH"] = {
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
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
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
			fieldname: "accounting_department",
			label: __("Accounting Department"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options(
					"Accounting Department",
					txt,
					{
						company:
							frappe.query_report.get_filter_value("company"),
					},
				);
			},
			options: "Accounting Department",
		},
	],
};
