// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.query_reports["Customer Borrow Tracking"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{
			fieldname: "employee",
			label: __("Responsible Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{
			fieldname: "material_request",
			label: __("Material Request"),
			fieldtype: "Link",
			options: "Material Request",
			get_query: () => ({ filters: { material_request_type: "Customer Borrow", docstatus: 1 } }),
		},
		{ fieldname: "warehouse", label: __("Borrow Warehouse"), fieldtype: "Link", options: "Warehouse" },
	],
};
