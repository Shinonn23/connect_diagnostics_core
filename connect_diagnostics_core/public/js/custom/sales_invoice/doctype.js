// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice", {
	setup(frm) {
		frm.set_query("purchase_order", "source_purchase_orders", () => ({
			filters: {
				docstatus: 1,
				company: frm.doc.company,
			},
		}));
	},

	refresh(frm) {
		show_customer_requirements(frm);
		add_source_copy_buttons(frm);
	},

	customer(frm) {
		show_customer_requirements(frm);
	},

	// A new source row starts on the Customer's default copy count, so a Customer
	// that always wants the same number need not retype it per row.
	source_purchase_orders_add(frm, cdt, cdn) {
		if (!frm.doc.customer) {
			return;
		}
		frappe.db.get_value("Customer", frm.doc.customer, "purchase_order_copy_count").then((r) => {
			const count = r?.message?.purchase_order_copy_count;
			if (count) {
				frappe.model.set_value(cdt, cdn, "copies", count);
			}
		});
	},

	source_purchase_orders_remove(frm) {
		show_customer_requirements(frm);
		add_source_copy_buttons(frm);
	},
});

frappe.ui.form.on("Sales Invoice Source Purchase Order", {
	purchase_order(frm) {
		show_customer_requirements(frm);
		add_source_copy_buttons(frm);
	},

	purchase_order_file(frm) {
		show_customer_requirements(frm);
		add_source_copy_buttons(frm);
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

// Downloading the PDF joins the source copies on automatically. The Print button
// hands HTML to the browser, which cannot join a PDF, so offer each row's copy as
// its own print here.
function add_source_copy_buttons(frm) {
	frm.remove_custom_button(__("Source Purchase Orders"), __("Print"));

	(frm.doc.source_purchase_orders || []).forEach((row, index) => {
		if (row.purchase_order) {
			frm.add_custom_button(
				__("Print {0}", [row.purchase_order]),
				() =>
					frappe.set_route("print", "Purchase Order", row.purchase_order, {
						format: "Purchase Order",
					}),
				__("Source Purchase Orders"),
			);
		} else if (row.purchase_order_file) {
			frm.add_custom_button(
				__("Open file {0}", [index + 1]),
				() => window.open(row.purchase_order_file, "_blank"),
				__("Source Purchase Orders"),
			);
		}
	});
}
