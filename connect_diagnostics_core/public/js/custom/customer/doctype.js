// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Customer", {
	refresh(frm) {
		frm.set_df_property(
			"print_documents_section",
			"description",
			frm.doc.print_configuration_template
				? __("Leave empty to follow {0}. Template changes apply immediately.", [
					frm.doc.print_configuration_template,
				])
				: __("Select a Print Configuration Template, or leave empty to use system defaults."),
		);
	},

	print_configuration_template(frm) {
		frm.trigger("refresh");
	},
});
