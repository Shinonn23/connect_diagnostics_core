// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (
			frm.is_new() ||
			frm.doc.customer_channel !== "DKSH" ||
			frm.doc.customer_onboarding_state !== "Customer Active" ||
			!frappe.user_roles.includes("Customer Accounting Reviewer")
		) {
			return;
		}

		frm.add_custom_button(__("Convert DKSH Customer"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Convert DKSH Customer"),
				fields: [
					{
						fieldname: "new_customer_code",
						label: __("New Customer Code"),
						fieldtype: "Data",
						reqd: 1,
					},
					{
						fieldname: "new_customer_channel",
						label: __("New Customer Channel"),
						fieldtype: "Select",
						options: "CD\nCD and DKSH",
						default: "CD and DKSH",
						reqd: 1,
					},
				],
				primary_action_label: __("Convert"),
				primary_action(values) {
					frappe.call({
						method: "connect_diagnostics_core.api.erpnext.customer.convert_dksh_customer",
						args: {
							customer: frm.doc.name,
							new_customer_code: values.new_customer_code,
							new_customer_channel: values.new_customer_channel,
						},
						freeze: true,
						freeze_message: __("Converting DKSH Customer…"),
						callback(response) {
							const customer = response.message?.data?.customer;
							if (!customer) {
								return;
							}
							dialog.hide();
							frappe.set_route("Form", "Customer", customer);
						},
					});
				},
			});
			dialog.show();
		});
	},
});
