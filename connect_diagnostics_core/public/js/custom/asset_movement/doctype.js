/* global frappe, __ */

frappe.ui.form.on("Asset Movement", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.workflow_state !== "Asset Movement Submitted") return;
		const pending = (frm.doc.assets || []).filter(
			(row) => row.receiver_user === frappe.session.user && !row.accepted_by,
		);
		if (!pending.length) return;
		frm.add_custom_button(__("Confirm Receipt"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Confirm Asset Receipt"),
				fields: [
					{
						fieldname: "row_name",
						label: __("Asset"),
						fieldtype: "Select",
						options: pending.map((row) => ({ value: row.name, label: row.asset })),
						reqd: 1,
					},
				],
				primary_action_label: __("Confirm Receipt"),
				async primary_action(values) {
					await frappe.call({
						method: "connect_diagnostics_core.api.erpnext.asset_movement_acceptance.confirm_receipt",
						args: { movement: frm.doc.name, row_name: values.row_name },
						freeze: true,
					});
					dialog.hide();
					await frm.reload_doc();
				},
			});
			dialog.show();
		});
	},
});
