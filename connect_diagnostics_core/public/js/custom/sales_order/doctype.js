// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		show_customer_requirements(frm);
	},

	customer(frm) {
		show_customer_requirements(frm);
	},
});

frappe.ui.form.on("Sales Order Item", {
	prevdoc_docname(frm) {
		show_customer_requirements(frm);
	},

	items_remove(frm) {
		show_customer_requirements(frm);
	},
});

// Say what the Customer still needs while it can still be met, rather than
// letting the server gate deliver the news as a save error.
function show_customer_requirements(frm) {
	frm.dashboard.clear_headline();
	if (!frm.doc.customer || frm.doc.docstatus !== 0) {
		return;
	}

	frappe
		.xcall("connect_diagnostics_core.api.erpnext.sales_requirements.get_transaction_requirements", {
			doc: frm.doc,
		})
		.then((response) => {
			const gaps = response?.data?.gaps || [];
			if (!gaps.length) {
				return;
			}
			frm.dashboard.set_headline(
				__("{0} requires {1}.", [frm.doc.customer_name || frm.doc.customer, gaps.join(", ")]),
				"orange",
			);
			frm.add_custom_button(__("Create Quotation"), () =>
				frappe.new_doc("Quotation", {
					quotation_to: "Customer",
					party_name: frm.doc.customer,
					company: frm.doc.company,
				}),
			);
		});
}
