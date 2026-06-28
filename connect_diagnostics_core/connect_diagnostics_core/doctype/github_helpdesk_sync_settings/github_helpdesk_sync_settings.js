// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitHub Helpdesk Sync Settings", {
	refresh(frm) {
		const show_log_link = (message) => {
			if (!message || !message.log_name) {
				return "";
			}
			const url = frappe.utils.get_form_link("GitHub Helpdesk Sync Log", message.log_name);
			return `<br><a href="${url}">${__("Open sync log")}</a>`;
		};

		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method: "connect_diagnostics_core.connect_diagnostics_core.doctype.github_helpdesk_sync_settings.github_helpdesk_sync_settings.test_connection",
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
				method: "connect_diagnostics_core.connect_diagnostics_core.doctype.github_helpdesk_sync_settings.github_helpdesk_sync_settings.fetch_board_metadata",
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

		frm.add_custom_button(__("Preflight Check"), () => {
			frappe.call({
				method: "connect_diagnostics_core.connect_diagnostics_core.doctype.github_helpdesk_sync_settings.github_helpdesk_sync_settings.preflight_check",
				freeze: true,
				freeze_message: __("Checking GitHub sync setup..."),
				callback: (r) => {
					const m = r.message || {};
					const failed = (m.checks || []).filter((check) => check.status === "fail");
					const rows = (m.checks || [])
						.map(
							(check) =>
								`<li><b>${frappe.utils.escape_html(check.name)}</b>: ${frappe.utils.escape_html(
									check.message || "",
								)}</li>`,
						)
						.join("");
					frappe.msgprint({
						title: m.ok ? __("Preflight passed") : __("Preflight found issues"),
						message: `<ul>${rows}</ul>${show_log_link(m)}`,
						indicator: failed.length ? "red" : "green",
					});
				},
			});
		});

		frm.add_custom_button(__("Repair Setup"), () => {
			frappe.call({
				method: "connect_diagnostics_core.connect_diagnostics_core.doctype.github_helpdesk_sync_settings.github_helpdesk_sync_settings.repair_setup",
				freeze: true,
				freeze_message: __("Repairing GitHub sync setup..."),
				callback: (r) => {
					frm.reload_doc();
					const m = r.message || {};
					frappe.msgprint({
						title: m.ok ? __("Repair complete") : __("Repair incomplete"),
						message: `${__("Created custom fields: {0}", [
							((m.custom_fields || {}).created || []).length,
						])}<br>${__("Added ticket UI fields: {0}", [
							((m.template_fields || {}).created || []).length,
						])}${show_log_link(m)}`,
						indicator: m.ok ? "green" : "orange",
					});
				},
			});
		});

		frm.add_custom_button(__("Retry Issue"), () => {
			frappe.prompt(
				[
					{
						fieldname: "issue_number",
						fieldtype: "Int",
						label: __("GitHub Issue #"),
						reqd: 1,
					},
				],
				(values) => {
					frappe.call({
						method: "connect_diagnostics_core.connect_diagnostics_core.doctype.github_helpdesk_sync_settings.github_helpdesk_sync_settings.retry_issue",
						args: { issue_number: values.issue_number },
						freeze: true,
						freeze_message: __("Retrying GitHub issue..."),
						callback: (r) => {
							const m = r.message || {};
							frappe.msgprint({
								title: __("Retry complete"),
								message: __("Status: {0}", [m.status || __("Unknown")]) + show_log_link(m),
								indicator: m.status === "Failed" ? "red" : "green",
							});
						},
					});
				},
				__("Retry GitHub Issue"),
				__("Retry"),
			);
		});

		frm.add_custom_button(__("Import Backlog from GitHub"), () => {
			const method =
				"connect_diagnostics_core.connect_diagnostics_core.doctype.github_helpdesk_sync_settings.github_helpdesk_sync_settings.import_backlog";
			// 1) dry-run preview
			frappe.call({
				method,
				args: { commit: 0 },
				freeze: true,
				freeze_message: __("Scanning GitHub issues..."),
				callback: (r) => {
					const m = r.message || {};
					if (m.error) {
						frappe.msgprint({
							title: __("Cannot import"),
							message: m.error,
							indicator: "red",
						});
						return;
					}
					if (!m.created) {
						frappe.msgprint({
							title: __("Nothing to import"),
							message: __("All {0} GitHub issue(s) already have a ticket.", [m.skipped]),
							indicator: "green",
						});
						return;
					}
					// 2) confirm, then commit
					frappe.confirm(
						__("Create {0} new ticket(s) from GitHub? ({1} already exist and will be skipped.)", [
							m.created,
							m.skipped,
						]),
						() => {
							frappe.call({
								method,
								args: { commit: 1 },
								freeze: true,
								freeze_message: __("Importing backlog from GitHub..."),
								callback: (r2) => {
									const m2 = r2.message || {};
									frappe.msgprint({
										title: __("Import complete"),
										message: __("Created {0}, skipped {1}, errors {2}.", [
											m2.created,
											m2.skipped,
											m2.errors,
										]),
										indicator: m2.errors ? "orange" : "green",
									});
								},
							});
						},
					);
				},
			});
		});

		frm.add_custom_button(__("Sync Now"), () => {
			frappe.call({
				method: "connect_diagnostics_core.connect_diagnostics_core.doctype.github_helpdesk_sync_settings.github_helpdesk_sync_settings.sync_now",
				freeze: true,
				freeze_message: __("Pulling from GitHub..."),
				callback: (r) => {
					frm.reload_doc();
					const m = r.message || {};
					frappe.msgprint({
						title: __("Sync complete"),
						message:
							__("Changed issues: {0}, board items: {1}, errors: {2}", [
								m.changed_issues || 0,
								m.board_items || 0,
								m.error_count || 0,
							]) + show_log_link(m),
						indicator:
							m.status === "Failed" || m.status === "Partial Failure" ? "orange" : "green",
					});
				},
			});
		}).addClass("btn-primary");
	},
});
