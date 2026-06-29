frappe.ui.form.on("HD Ticket", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.__islocal) {
			return;
		}

		if (frm.doc.github_issue_number) {
			if (frm.doc.github_url) {
				frm.add_custom_button(
					__("Open GitHub Issue"),
					() => window.open(frm.doc.github_url, "_blank"),
					__("GitHub"),
				);
			}
			return;
		}

		frm.add_custom_button(
			__("Escalate to GitHub"),
			() => {
				frappe.confirm(
					__("Create a GitHub issue for this ticket and hand it to the dev team?"),
					() => {
						frappe.call({
							method: "connect_diagnostics_core.github_sync.escalate_to_github",
							args: { ticket: frm.doc.name },
							freeze: true,
							freeze_message: __("Creating GitHub issue..."),
							callback: (r) => {
								const m = r.message || {};
								if (m.message) {
									frappe.show_alert({ message: m.message, indicator: "green" });
								}
								frm.reload_doc();
							},
						});
					},
				);
			},
			__("GitHub"),
		);
	},
});
