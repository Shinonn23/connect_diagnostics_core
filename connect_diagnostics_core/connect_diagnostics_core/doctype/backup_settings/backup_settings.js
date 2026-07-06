// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Backup Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frm.call({ method: "test_connection", doc: frm.doc, freeze: true }).then((r) => {
				frappe.msgprint({
					title: __("Bucket Access"),
					message: r.message.message,
					indicator: r.message.data ? "blue" : "orange",
				});
			});
		});

		frm.add_custom_button(__("Run Backup Now"), () => {
			frappe.confirm(__("Back up the database to the frequent bucket now?"), () => {
				// The server streams a progress bar via frappe.publish_progress.
				frappe.show_progress(__("Backing up"), 1, 100, __("Starting…"));
				frm.call({
					method: "run_backup_now",
					doc: frm.doc,
					callback: (r) => {
						frappe.hide_progress();
						if (r.message) {
							frappe.show_alert({ message: r.message.message, indicator: "green" });
							frm.reload_doc();
						}
					},
					error: () => frappe.hide_progress(),
				});
			});
		});

		frm.add_custom_button(__("Backup Files"), () => {
			frappe.confirm(
				__("Force-mirror every file to the mirror bucket (overwrites, never deletes)?"),
				() => {
					frm.call({ method: "backup_files_now", doc: frm.doc, freeze: true }).then((r) => {
						frappe.show_alert({ message: r.message.message, indicator: "blue" });
					});
				},
			);
		});
	},
});
