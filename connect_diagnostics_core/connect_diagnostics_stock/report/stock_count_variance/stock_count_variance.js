// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.query_reports["Stock Count Variance"] = {
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
			fieldname: "stock_count",
			label: __("Stock Count"),
			fieldtype: "Link",
			options: "Stock Count",
		},
		{
			fieldname: "count_type",
			label: __("Count Type"),
			fieldtype: "Select",
			options: "\nCycle Count (Monthly)\nYearly Count",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "storage_location",
			label: __("Storage Location"),
			fieldtype: "Link",
			options: "Storage Location",
		},
		{
			fieldname: "from_posting_date",
			label: __("From Posting Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_posting_date",
			label: __("To Posting Date"),
			fieldtype: "Date",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "variance_qty" && data?.variance_qty) {
			const cls = data.variance_qty < 0 ? "text-danger" : "text-success";
			return `<span class="${cls}">${value}</span>`;
		}
		return value;
	},
};
