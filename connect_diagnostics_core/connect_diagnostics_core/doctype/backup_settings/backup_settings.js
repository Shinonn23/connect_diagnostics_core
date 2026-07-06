// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Backup Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frm.call("test_connection").then((r) => {
				frappe.msgprint({
					title: __("Bucket Access"),
					message: r.message.message,
					indicator: r.message.data ? "blue" : "orange",
				});
			});
		});

		frm.add_custom_button(__("Run Backup Now"), () => {
			frappe.confirm(__("Generate a backup and upload it to the due buckets now?"), () => {
				frappe.dom.freeze(__("Running backup…"));
				frm.call("run_backup_now")
					.then((r) => {
						frappe.show_alert({ message: r.message.message, indicator: "green" });
						frm.reload_doc();
					})
					.finally(() => frappe.dom.unfreeze());
			});
		});

		frm.add_custom_button(__("Backup Files"), () => {
			frappe.confirm(
				__("Force-mirror every file to the mirror bucket (overwrites, never deletes)?"),
				() => {
					frm.call("backup_files_now").then((r) => {
						frappe.show_alert({ message: r.message.message, indicator: "blue" });
					});
				},
			);
		});
	},
});
