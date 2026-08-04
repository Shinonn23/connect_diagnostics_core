// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

async function fetch_print_configuration_template(frm) {
	if (!frm.doc.print_configuration_template) {
		return;
	}
	const response = await frappe.call({
		method: "connect_diagnostics_core.api.erpnext.print_configuration.get_template_defaults",
		args: { template: frm.doc.print_configuration_template },
	});
	if (!response.message?.data) {
		return;
	}
	await frm.set_value(response.message.data);
	frappe.show_alert({
		message: response.message.message,
		indicator: "green",
	});
}

frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.print_configuration_template) {
			return;
		}

		frm.add_custom_button(
			__("Fetch Configuration"),
			() => fetch_print_configuration_template(frm),
			__("Print Configuration"),
		);
	},

	print_configuration_template(frm) {
		return fetch_print_configuration_template(frm);
	},
});
