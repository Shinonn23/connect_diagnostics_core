// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Company", {
	onload(frm) {
		frm.set_query("employee", "quotation_authorized_signatories", () => ({
			query: "connect_diagnostics_core.api.erpnext.company.authorized_signatory_employee_query",
			filters: { company: frm.doc.name },
		}));
	},
});
