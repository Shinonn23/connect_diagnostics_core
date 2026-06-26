// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitHub Integration Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method: "connect_diagnostics_core.connect_diagnostics_core.doctype.github_integration_settings.github_integration_settings.test_connection",
				freeze: true,
				freeze_message: __("Contacting GitHub..."),
				callback: (r) => {
					frm.reload_doc();
					if (r.message && r.message.ok) {
						frappe.show_alert({
							message: __("Connection OK"),
							indicator: "green",
						});
					} else {
						frappe.msgprint({
							title: __("Connection failed"),
							message: (r.message || {}).error,
							indicator: "red",
						});
					}
				},
			});
		});

		frm.add_custom_button(__("Fetch Board Metadata"), () => {
			frappe.call({
				method: "connect_diagnostics_core.connect_diagnostics_core.doctype.github_integration_settings.github_integration_settings.fetch_board_metadata",
				freeze: true,
				freeze_message: __("Reading project board..."),
				callback: (r) => {
					frm.reload_doc();
					frappe.show_alert({
						message: __("Loaded {0} board columns", [(r.message || {}).options || 0]),
						indicator: "green",
					});
				},
			});
		});

		frm.add_custom_button(__("Sync Now"), () => {
			frappe.call({
				method: "connect_diagnostics_core.connect_diagnostics_core.doctype.github_integration_settings.github_integration_settings.sync_now",
				freeze: true,
				freeze_message: __("Pulling from GitHub..."),
				callback: (r) => {
					frm.reload_doc();
					const m = r.message || {};
					frappe.msgprint({
						title: __("Sync complete"),
						message: __("Changed issues: {0}, board items: {1}", [
							m.changed_issues || 0,
							m.board_items || 0,
						]),
						indicator: "green",
					});
				},
			});
		}).addClass("btn-primary");
	},
});
