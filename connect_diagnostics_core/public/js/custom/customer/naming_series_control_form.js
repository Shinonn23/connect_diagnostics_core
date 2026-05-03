// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Customer", {
	refresh(frm) {
		toggle_dksh_code(frm);
	},
	naming_series(frm) {
		toggle_dksh_code(frm);
	},
});

function toggle_dksh_code(frm) {
	const is_dksh_series = frm.doc.naming_series === "DKSH-.{custom_dksh_code}";
	frm.toggle_display("custom_dksh_code", is_dksh_series);
	frm.toggle_reqd("custom_dksh_code", is_dksh_series);
}
