// Copyright (c) 2026, Siwat Sroisuwan and contributors

frappe.ui.form.on("Borrowed Item Resolution", {
	setup(frm) {
		frm.set_query("material_request", () => ({
			filters: { company: frm.doc.company, docstatus: 1 },
		}));
		frm.set_query("sales_invoice", () => ({
			filters: { company: frm.doc.company, docstatus: 1, status: "Paid" },
		}));
	},
});
