function install_disposal_reasoned_actions(frm) {
	if (frm._disposal_workflow_installed || !frm.states) return;
	frm._disposal_workflow_installed = true;
	const native_action = frm.states.handle_workflow_action.bind(frm.states);
	const reasoned_actions = new Set([
		"Return",
		"Reject",
		"Request Abandonment Reset",
		"Return Abandonment Reset",
	]);
	frm.states.handle_workflow_action = (transition) => {
		if (!reasoned_actions.has(transition.action)) return native_action(transition);
		frappe.prompt(
			[{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
			({ reason }) => {
				frappe.call({
					method: "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.apply_reasoned_action",
					args: { name: frm.doc.name, action: transition.action, reason },
					callback() {
						frm.reload_doc();
					},
				});
			},
			__(transition.action),
			__("Apply"),
		);
	};
}

frappe.ui.form.on("Asset Disposal Request", {
	refresh(frm) {
		install_disposal_reasoned_actions(frm);
		if (frm.is_new() || frm.doc.docstatus !== 1) return;
		if (frm.doc.workflow_state === "Asset Disposal Submitted") {
			if (frm.doc.disposal_status === "Not Executed") {
				frm.add_custom_button(__("Stage Depreciation"), () => {
					frappe.call({
						method: "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.stage_depreciation",
						args: { name: frm.doc.name },
						callback() {
							frm.reload_doc();
						},
					});
				});
			}
			if (frm.doc.disposal_status === "Ready to Dispose") {
				frm.add_custom_button(__("Finalize Disposal"), () => {
					frappe.call({
						method: "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.finalize_disposal",
						args: { name: frm.doc.name },
						callback() {
							frm.reload_doc();
						},
					});
				});
			}
		}
		if (frm.doc.workflow_state === "Asset Disposal Reset Approved") {
			frm.add_custom_button(__("Reset and Abandon"), () => {
				frappe.call({
					method: "connect_diagnostics_core.api.erpnext.asset_disposal_workflow.reset_and_abandon",
					args: { name: frm.doc.name },
					callback() {
						frm.reload_doc();
					},
				});
			});
		}
	},
});
