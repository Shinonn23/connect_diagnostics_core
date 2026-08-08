// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("DKSH Customer", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		if (frm.doc.customer) {
			frm.add_custom_button(__("Go to Customer"), () =>
				frappe.set_route("Form", "Customer", frm.doc.customer),
			);
			return;
		}

		frm.add_custom_button(__("Convert to CD Customer"), () =>
			frappe.new_doc("Customer", {
				customer_name: frm.doc.customer_name,
				tax_id: frm.doc.tax_id,
				branch_code: frm.doc.branch_code,
				source_dksh_customer: frm.doc.name,
			}),
		).addClass("btn-primary");
	},
});
