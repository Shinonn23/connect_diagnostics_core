// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice", {
	setup(frm) {
		frm.set_query("source_purchase_order", () => ({
			filters: {
				docstatus: 1,
				company: frm.doc.company,
			},
		}));
	},

	refresh(frm) {
		show_customer_requirements(frm);
		add_source_copy_button(frm);
	},

	customer(frm) {
		show_customer_requirements(frm);
	},

	source_purchase_order(frm) {
		show_customer_requirements(frm);
		add_source_copy_button(frm);
	},

	source_purchase_order_file(frm) {
		show_customer_requirements(frm);
		add_source_copy_button(frm);
	},
});

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
			if (gaps.length) {
				frm.dashboard.set_headline(
					__("{0} requires {1}.", [frm.doc.customer_name || frm.doc.customer, gaps.join(", ")]),
					"orange",
				);
			}
		});
}

// Downloading the PDF joins the source copy on automatically. The Print button
// hands HTML to the browser, which cannot join a PDF, so offer the copy as its
// own print here.
function add_source_copy_button(frm) {
	if (frm.doc.source_purchase_order) {
		frm.add_custom_button(
			__("Print Source Purchase Order"),
			() =>
				frappe.set_route("print", "Purchase Order", frm.doc.source_purchase_order, {
					format: "Purchase Order",
				}),
			__("Print"),
		);
	} else if (frm.doc.source_purchase_order_file) {
		frm.add_custom_button(
			__("Open Source Purchase Order File"),
			() => window.open(frm.doc.source_purchase_order_file, "_blank"),
			__("Print"),
		);
	}
}
