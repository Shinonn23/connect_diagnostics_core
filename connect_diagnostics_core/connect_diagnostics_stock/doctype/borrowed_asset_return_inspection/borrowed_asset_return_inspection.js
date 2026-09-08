// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Borrowed Asset Return Inspection", {
	setup(frm) {
		frm.set_query("return_dispatch", () => ({
			filters: {
				dispatch_type: "Return",
				delivery_status: "Delivered",
				docstatus: 1,
			},
		}));
		frm.set_query("return_dispatch_transfer", () => ({
			filters: {
				parent: frm.doc.return_dispatch,
				reference_doctype: "Asset Movement",
				asset: ["is", "set"],
			},
		}));
	},
});
