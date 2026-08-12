// Copyright (c) 2026, Siwat Sroisuwan and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Count", {
	onload: function (frm) {
		frm.set_query("storage_location", function () {
			return { filters: { warehouse: frm.doc.warehouse } };
		});
	},

	refresh: function (frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Fetch Items"), function () {
				frm.events.fetch_items(frm);
			});
		}

		const is_approved = frm.doc.docstatus === 1 && frm.doc.count_state === "Stock Count Approved";
		if (is_approved && frm.doc.count_type === "Cycle Count (Monthly)") {
			frm.add_custom_button(__("Generate Holding Transfer"), function () {
				frm.events.run_generate(frm, "generate_holding_transfer");
			});
		}
		if (is_approved && frm.doc.count_type === "Yearly Count") {
			frm.add_custom_button(__("Generate Stock Adjustment"), function () {
				frm.events.run_generate(frm, "generate_stock_adjustment");
			});
		}
	},

	fetch_items: function (frm) {
		frappe.call({
			method: "connect_diagnostics_core.api.erpnext.stock_count.fetch_items",
			args: { stock_count: frm.doc.name },
			freeze: true,
			freeze_message: __("Fetching count lines..."),
			callback: function (r) {
				if (r.message && r.message.message) {
					frappe.show_alert({ message: r.message.message, indicator: "green" });
				}
				frm.reload_doc();
			},
		});
	},

	run_generate: function (frm, method) {
		frappe.call({
			method: `connect_diagnostics_core.api.erpnext.stock_count.${method}`,
			args: { stock_count: frm.doc.name },
			freeze: true,
			freeze_message: __("Generating..."),
			callback: function (r) {
				if (r.message && r.message.message) {
					frappe.show_alert({ message: r.message.message, indicator: "green" });
				}
				frm.reload_doc();
			},
		});
	},
});
