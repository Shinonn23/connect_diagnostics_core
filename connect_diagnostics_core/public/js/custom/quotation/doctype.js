// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

async function set_customer_signatory_default(frm) {
	if (frm.doc.quotation_to !== "Customer" || !frm.doc.party_name) {
		return;
	}
	const customer_signatory = await frappe.db.get_value(
		"Customer",
		frm.doc.party_name,
		"quotation_signatory_type",
	);
	const signatory_type = customer_signatory?.message?.quotation_signatory_type || "Sales Representative";
	frm.set_value("quotation_signatory_type", signatory_type);
}

async function set_company_authorized_signatory_default(frm) {
	if (!frm.doc.company) {
		return;
	}
	const company_signatory = await frappe.db.get_value(
		"Company",
		frm.doc.company,
		"quotation_authorized_signatory_employee",
	);
	const employee = company_signatory?.message?.quotation_authorized_signatory_employee || "";
	if (employee) {
		frm.set_value("quotation_authorized_signatory_employee", employee);
	}
}

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			const row = frappe.get_doc(cdt, cdn);
			return {
				query: "connect_diagnostics_core.api.erpnext.item.get_item_with_stock",
				filters: { warehouse: row.warehouse || "" },
			};
		});
	},

	party_name(frm) {
		set_customer_signatory_default(frm);
	},

	quotation_signatory_type(frm) {
		if (
			frm.doc.quotation_signatory_type === "Managing Director" &&
			!frm.doc.quotation_authorized_signatory_employee
		) {
			set_company_authorized_signatory_default(frm);
		}
	},

	company(frm) {
		set_company_authorized_signatory_default(frm);
	},
});
