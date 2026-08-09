// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

async function set_customer_quotation_defaults(frm) {
	if (frm.doc.quotation_to !== "Customer" || !frm.doc.party_name) {
		return;
	}
	const customer = await frappe.db.get_value("Customer", frm.doc.party_name, "quotation_signatory_type");
	frm.set_value(
		"quotation_signatory_type",
		customer?.message?.quotation_signatory_type || "Sales Representative",
	);
}

async function set_sales_representative_default(frm) {
	if (!frm.is_new() || frm.doc.sales_representative_employee) {
		return;
	}
	const employee = await frappe.db.get_value(
		"Employee",
		{ user_id: frappe.session.user, status: "Active" },
		"name",
	);
	if (employee?.message?.name) {
		frm.set_value("sales_representative_employee", employee.message.name);
	}
}

frappe.ui.form.on("Quotation", {
	onload(frm) {
		set_sales_representative_default(frm);
	},

	party_name(frm) {
		set_customer_quotation_defaults(frm);
	},
});
