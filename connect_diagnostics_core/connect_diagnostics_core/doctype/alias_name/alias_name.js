// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Alias Name", {
	refresh(frm) {
		frm.set_query("documents", function () {
			return {
				query: "connect_diagnostics_core.api.connect_diagnostics_core.alias_name.get_supported_doctypes",
			};
		});
		if (frm.doc.primary_name && frm.doc.documents) {
			frm.trigger("primary_name");
		}
	},

	documents(frm) {
		frm.set_value("primary_name", "");
		frm.set_value("original_display_name", "");
	},

	primary_name(frm) {
		if (!frm.doc.primary_name || !frm.doc.documents) {
			frm.set_value("original_display_name", "");
			return;
		}
		frappe.call({
			method: "connect_diagnostics_core.api.connect_diagnostics_core.alias_name.get_original_display_name",
			args: {
				reference_doctype: frm.doc.documents,
				primary_name: frm.doc.primary_name,
			},
			callback(r) {
				frm.set_value("original_display_name", r.message?.data || "");
			},
		});
	},
});
