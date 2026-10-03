// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

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

function set_sales_representative_query(frm) {
	frm.set_query("sales_representative_employee", () => ({
		query: "connect_diagnostics_core.api.erpnext.quotation.signatory_employee_query",
		filters: {
			quotation_signatory_type: frm.doc.quotation_signatory_type,
			company: frm.doc.company,
		},
	}));
}

async function set_delivery_terms_from_template(frm) {
	if (!frm.doc.delivery_terms_template) {
		return;
	}
	const template = await frappe.db.get_value(
		"Delivery Terms Template",
		frm.doc.delivery_terms_template,
		"delivery_terms_text",
	);
	if (template?.message?.delivery_terms_text) {
		frm.set_value("quotation_delivery_terms", template.message.delivery_terms_text);
	}
}

// Thai-only preview of what _validity_text() would compute from Valid Till at
// print time. Print rendering stays multi-language (language is a print-sidebar
// choice, not stored on the document), so this is a Desk-side convenience only,
// not the source of truth for what gets printed.
function set_validity_text_preview(frm) {
	if (frm.doc.edit_validity_text) {
		return;
	}
	if (!frm.doc.valid_till || !frm.doc.transaction_date) {
		frm.set_value("validity_text", "");
		return;
	}
	const days = frappe.datetime.get_diff(frm.doc.valid_till, frm.doc.transaction_date);
	frm.set_value("validity_text", `${days} วัน นับถัดจากวันที่เสนอราคา`);
}

frappe.ui.form.on("Quotation", {
	onload(frm) {
		set_sales_representative_default(frm);
		set_sales_representative_query(frm);
		set_validity_text_preview(frm);
	},

	quotation_signatory_type(frm) {
		set_sales_representative_query(frm);
	},

	delivery_terms_template(frm) {
		set_delivery_terms_from_template(frm);
	},

	transaction_date(frm) {
		set_validity_text_preview(frm);
	},

	valid_till(frm) {
		set_validity_text_preview(frm);
	},

	edit_validity_text(frm) {
		set_validity_text_preview(frm);
	},
});
